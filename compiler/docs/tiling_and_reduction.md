# 张量需求传播、切块与规约设计

从算子依赖出发推导区域，再选择资源可执行的分块与归并。公共语义见[张量区域契约](../../docs/interfaces/tensor_regions.md)，参数入口见 [UNITS](../UNITS.md)。本文是编译器设计与校核案例，不代表已有 tiling pass；外部手册的审阅统计见[审阅记录](../../docs/reference/layout_roi_review.md)。

## 1 内容放在哪里

| 内容 | 维护归属 | 边界 |
| --- | --- | --- |
| 模型维度、attention/MoE/训练算子语义 | workloads；trainingArch/inferArch 组织场景 | 不由轴编号常量推断算法 |
| 跨模块 shape、逻辑 ROI、存储视图、partial result | contracts；[区域契约](../../docs/interfaces/tensor_regions.md) | 不放 tiling 策略或硬件动态状态 |
| 算子索引映射与依赖 | compiler/src/ir；本设计文档 | 表达 M/N/K、广播、规约与动态索引 |
| 区域反推、尾块、局部 split-K/context | compiler/src/tiling | 输出精确/保守需求、分块与归并要求 |
| TP/EP/PP 等跨设备分片 | compiler/src/globalsplit 与 globalsolver | 切块不自动等于跨设备并行；通信需显式推导 |
| 驻留/双缓冲、地址、别名、活跃容量 | compiler/src/memplan | ROI 复用不证明实际驻留或合法容量 |
| merge 顺序、同步与目标指令 | compiler/src/sched、lowering | 区间合并、数值规约和完成事件分别表达 |
| 动态路由/请求、提交与规约进度 | runtime | 不维护硬件队列或替硬件免费执行规约 |
| MAC/CIM/缓冲/DMA/链路服务与成本 | chipmodel/systemmodel/clustermodel/costmodel | 只消费明确工作量与请求，不拥有模型图语义 |

保持现有目录，不新增 layout_roi 专用大框架。axis 名、shape、算法迭代角色和存储映射分别表达，不能仅根据 rank=3/4/5 分派语义。

## 2 独立调用的最小设计

逻辑算子 + 输出需求 ROI + 输入 shape/索引关系 → 输入需求、规约范围和前置条件。资源/布局适配、容量/成本筛选另做一步，不必运行整个编译 pipeline。

| 候选操作（尚未实现接口） | 结果与校验 |
| --- | --- |
| 区域校验/分区 | 逐维合法范围、空区、完整覆盖、尾块有效长度；不隐式遗漏元素 |
| 输出需求反推 | 每输入的区域/索引集，标明 exact 或 cover；多消费者需求按张量身份合并 |
| 映射 reshape/transpose/broadcast | 保持坐标身份；无法表示为单矩形时返回若干区域/显式覆盖，或诊断不支持 |
| 规约规划 | 分区身份、输出 ROI、partial dtype、归并拓扑/阶段、最终处理及临时容量 |

需求传播可以从输出向前驱走，但它不是全图调度：分支、共享消费者、副作用、动态索引需要分别处理。重复扫描同一生产者不等于应重复执行或重复搬运。

## 3 常用算子的区域关系

### 3.1 GEMM / Linear

采用 Y[M,N]=X[M,K]W[K,N]。目标输出 [m0,m1)×[n0,n1) 需要 X[m0:m1,0:K] 与 W[0:K,n0:n1]。M 与 N 都可独立切分；选择哪个轴取决于复用、阵列形状、容量与并行机会，不强制只切 N。

若沿 K 分成互不重叠且覆盖 [0,K) 的区间 K_p，则 P_p=X[:,K_p]W[K_p,:]，Y=Σ_p P_p。合并区间 [0,K) 只是证明覆盖；必须另外产生 add/归约操作或声明硬件已覆盖该阶段。

对 Y=alpha·XW+beta·C+bias，不能给每个 partial 都加一次 beta·C 或 bias。激活、舍入/量化、饱和发生的位置也必须与原算子一致；并行 partial 与串行原位累加具有不同临时容量和顺序。

**容量校核例**：X[128,1024]、W[1024,512] 沿 N 切为 256 列；输入和权重 FP16，单个活跃累加 tile FP32。X=256 KiB，W_tile=512 KiB，P_tile=128 KiB，三者同时驻留为 896 KiB，尚未计其他开销。若 W 做双缓冲，增到 1408 KiB。因此“两个 tile 都读取同一 X”不能单独证明 X 可以驻留。

split-K 将 K=1024 切为 4×256，逻辑 MAC 总数仍为 M·N·1024；若存储四个并行输出 partial，临时量为 4·M·N·bytes_acc。仅按最朴素的最终求和，另有 3·M·N 次 add；融合或串行累加要改用其实际工作/存储模型。

### 3.2 Concat、广播与动态索引

Concat 输入 i 的目标轴长度 d_i，累计偏移 o_i=Σ_{j<i}d_j。输出区间 [a,b) 对该输入的本地区间为 [max(a,o_i)−o_i, min(b,o_i+d_i)−o_i)；只在左端<右端时产生需求，否则为空。

例：三个长度 10 的输入 concat，输出 [15,25) → 输入 0 空、输入 1 [5,10)、输入 2 [0,5)，有效长度总和仍为 10。其他轴原样传播。

逐元素广播把源长度 1 的相应轴映射为 [0,1)；transpose 按显式轴置换映射。Gather/embedding/MoE dispatch 的需求由索引决定，不能只用一个输出矩形就知道输入的精确连续范围；允许已知索引的局部分析或显式保守覆盖。

MoE 例：10 个 token、top-k=2、无丢弃 → 总 expert assignment=20，T_e 的分布仍取决于路由。Router logits 为 [10,E]，expert indices 与 gates 各为 [10,2]；索引整数与 gate 浮点分别存储。若使用 [10,4] 打包视图，必须明确 pair 编码和 dtype，不能从“末维=2”推断类型。

### 3.3 Reshape 与 head-group 映射

在均匀 GQA、query heads 按 group 连续排列时，Q[B,S_q,n_q,d] 可重解释为 [B,S_q,n_kv,g,d]，g=n_q/n_kv。K/V 原生是 [B,S_kv,n_kv,d]；显式插入 g 轴时为 1，广播共享不要求复制 g 份。

每个 group/head 的所有内层 feature 均完整时，group 区间 [a,b) 映射到 query head [a·g,b·g)，展平 feature 为 [a·g·d,b·g·d)。形状示例 n_q=32、n_kv=8、g=4、d=128：group [0,4) → heads [0,16) → feature [0,2048)；group [4,6) → heads [16,24)。

这个区间公式要求内层 g、d 全取且排列一致。若只选 group [0,2) 中 feature [0,64)，展平需求是 [0,64)∪[128,192)∪…∪[896,960)，共 512 元素，不能当成连续 [0,512)。用 [0,960) 覆盖则需明确多取 448 元素及访问/存储成本。

逻辑 reshape 可保持元素数而不搬运；它是否能变成零拷贝 view 还受物理 strides/contiguity 限制。非连续输入不能仅由 shape 宣称 flatten 免费。

### 3.4 尾块与对齐

通用分区可用 [a+j·step, min(a+(j+1)·step,b))，step>0，直到覆盖 [a,b)。例如 [0,100) 按 32 分为 [0,32)、[32,64)、[64,96)、[96,100)，不能遗漏末 4 个元素。

硬件或特定 helper 可以要求地址、start/end 或 extent 对齐，但必须分别说明对齐原点/单位及支持的 tail 策略：精确尾块、padding+mask、其他资源回退或显式拒绝。padding 的多余 lane/乘积不能污染规约，且工作量/流量须计入。尚未取得原 `split_range_by_step` 代码，不能确认其异常规则。

## 4 Attention 的三种切分不是同一件事

采用 Q[B,S_q,n_q,d]、K[B,S_kv,n_kv,d]、V[B,S_kv,n_kv,d_v]；均匀 GQA 中 query head h 使用 KV head floor(h/g)。每个 query 的结果由合法 key 范围中的 softmax 权重和 V 加权求和得到。

| 切分位置 | 需要的输入与完成方式 |
| --- | --- |
| query position / S_q | 各 query 输出行独立；K/V 需求覆盖各行可见 key 的并集。非因果全注意力需要全 S_kv；因果/窗口模式按绝对位置与 mask 推导 |
| query heads / KV group | 各 query head 的局部 attention 独立，K/V 可共享；是否能零复制/同时运行取决于布局与资源。下游若混合 heads，仍需继续推导依赖 |
| key/value context / S_kv | 每块只提供一部分 softmax 分母与加权分子；必须采用正确归并状态，不能直接相加局部 attention 输出 |

QKᵀ 的收缩轴是 d，softmax 的归一化轴是 S_kv，概率乘 V 的收缩轴也为 S_kv。S_q 是输出行轴；因此“Attention 的 S 是规约维”不完整，prefill 与 decode 不能用一个 S 取代这些角色。

### 4.1 split-context 的稳定状态

对固定 query 行及 head，有限 logits z_j=q·k_j/√d+mask_bias_j，V 向量 v_j。有效 key 分区 i 保存：

- m_i=max_j z_j，单位与 logit 一致（通常无量纲）。
- l_i=Σ_j exp(z_j−m_i)，无量纲归一化分母。
- u_i=Σ_j exp(z_j−m_i)·v_j，d_v 维未归一化分子，单位与 V 一致。

合并两个非空分区：m=max(m_1,m_2)，a=exp(m_1−m)，b=exp(m_2−m)，l=a·l_1+b·l_2，u=a·u_1+b·u_2。最终 output=u/l。m/l/u 都按 query/head 分别维护；它们不是跨 query 共享的单一标量。

空或全遮蔽分区采用 neutral 状态并在合并时跳过，避免计算 exp(−∞−(−∞))；若整行无有效 key，按 workload 的明确策略处理，不能隐式除零。NaN/+Inf、dropout、量化与近似指数另有数值语义，不能从上述有限 logits 公式推断。

**数值校核例**：z=[0,ln2,ln3,ln4]，V=[1,2,3,4]，完整输出=(1+4+9+16)/(1+2+3+4)=3。切成前后两块，各自归一化输出为 5/3 与 25/7，相加不等于 3。状态分别为 (ln2,1.5,2.5) 与 (ln4,1.75,6.25)，合并后 l=2.5、u=7.5，恢复 output=3。

如果使用跨设备 split-context，除本地计算外还要计 m/l/u 的通信、归并算子、临时存储与完成依赖。FlashAttention 是减少 HBM 访问的算法/实现族，不规定所有硬件接口都必须使用同一种 5D 排列。

## 5 修订后的完整走查：head-group → 输出投影

显式假设：密集输入 X[B=2,S=512,H_model=4096]，n_q=32，n_kv=8，g=4，d=d_v=128，输出宽 H_out=4096；prefill 的 S_q=S_kv=512，非因果全注意力，head 按 group 连续排列，无 dropout。常见 H_model=n_q·d 仅在本例成立。

W_q[4096,4096]、W_k/W_v[4096,1024]，attention 拼接输出 A[2,512,4096]，W_o[4096,4096]。选择两个 KV group 分区 [0,4)、[4,8)，对应 A 的 feature/K 分区 [0,2048)、[2048,4096)。

| 步骤 | 分区 0 的区域/形状 | 分区 1 与最终完成 |
| --- | --- | --- |
| 1. 输出投影规划 | 目标 Y[2,512,4096] 全取；按输入 A 的 K 分区产生 P_0[2,512,4096] | P_1 输出 shape 相同；必须有 P_0+P_1，不是两个独立最终输出 tile |
| 2. W_o 与 A 需求 | W_o[K=0:2048,N=0:4096]；A feature [0,2048) | 另一半 K=[2048,4096)，N 仍全取 |
| 3. head-group 需求 | A → Q heads [0,16)、KV heads [0,4)；所有内层 g/d、query/key 位置按本例全取 | Q heads [16,32)、KV heads [4,8) |
| 4. Q/K/V 投影 | W_q 输入 K 全 4096、输出 N=[0,2048)；W_k/W_v 输入 K 全、输出 N=[0,512) | Q 输出 N=[2048,4096)，K/V 输出 N=[512,1024) |
| 5. 输入与局部 attention | X 的逻辑需求全取；Q_0[2,512,16,128]，K_0/V_0[2,512,4,128] | 共享 X 的实际驻留/读取由 memplan 决定；局部 attention 数值可独立，实际时间仍受共享资源限制 |
| 6. 局部输出投影 | flatten A_0 为 [1024,2048]，乘 W_o 子块 [2048,4096] → P_0[1024,4096] | P_1 同形状；相加后按原语义加入 bias/最终处理，reshape 为 Y[2,512,4096] |

该走查把“上游 head 独立”和“下游 K 收缩”同时保留下来。若改成沿 Y 的 N 切分，则每个 Y 子块需要对应 W_o 列和完整 A；在没有额外 split-K 的情况下，会反推完整 head 范围，不能突然改成只取前几个 head。

同配置 decode 可取 S_q=1、S_kv=512，Q=[2,1,32,128]、K/V=[2,512,8,128]、attention output=[2,1,32,128]。这只规定本次可见上下文长度；KV append 的位置、时刻和 causal mask 另由请求语义给定。

## 6 对训练与 CIM 的影响

训练不能照搬前向的迭代角色：对 Y=XW，dX=dY·Wᵀ 的收缩轴是原 N，dW=Xᵀ·dY 的收缩轴是原 M；沿 token/microbatch 切前向时，权重梯度仍要累加。bias 梯度也沿样本/token 求和；通信规约与本地规约分别计量。

Attention 训练还要保存或重计算反向所需状态；dropout 掩码应绑定逻辑元素/明确随机规则，换 tile 顺序不能悄悄改变任务。浮点重关联允许什么误差由独立参考规定，不能仅凭形状一致验收。

映射 CIM 时，逻辑 split-K/行分块可能增加阵列求值、ADC 转换和跨阵列部分和归并。编码位切片累加、阵列行分组累加、GEMM 分区累加分别记录实际动作；若宏摘要已覆盖其中阶段，则避免再次计费。硬件动作公式仍以 [CIM UNITS](../../chipmodel/compute/cim/UNITS.md) 为准。

## 7 验收与首次实现取舍

验收应覆盖：K 分区不重不漏、尾块/mask、非连续 reshape 的精确像、concat 空区/跨边界、广播别名、动态索引、不同 S_q/S_kv、softmax 状态合并、Linear O 跨 head 累加、bias/量化位置，以及训练梯度方向。

首个实现只需要单位步长 ROI、GEMM 输入区域推导、尾块分区和显式 sum 规约规划；再按需求加入 concat/reshape、GQA 与 context 状态。不先建立通用多面体编译器，也不把文档中的候选操作全部变成类。

## 8 核查依据

- [MLIR Linalg](https://mlir.llvm.org/docs/Dialects/Linalg/)：算子 indexing maps 与 parallel/reduction iterator 角色，本轮核对公开文档；不要求仓库依赖 MLIR。
- [MLIR MemRef](https://mlir.llvm.org/docs/Dialects/MemRef/)：subview/offset/stride 与 view 关系，本轮读取文档；这里只借鉴语义边界。
- [Triton fused attention 教程源码](https://github.com/triton-lang/triton/blob/main/python/tutorials/06-fused-attention.py)：本轮核对 max/分母/分子重缩放；源码使用 exp2，本文使用自然指数，两者需相应 score 缩放。
- [PyTorch SDPA 的接口文档源码](https://github.com/pytorch/pytorch/blob/main/torch/nn/functional.py)：本轮核对独立 source/target sequence length、Q/K 特征维、V 特征维与 GQA 参数。Python 文档页本次未正常返回正文，核查改用项目源码中的接口说明。
- [GQA 原文](https://arxiv.org/html/2305.13245v3)：均匀 query/KV head 分组；参数关系不推广成所有模型的强制形状。

源码分支与网页为 2026-11-06 的核查入口；本项目尚未接入这些编译/attention 实现。外部 `layout_roi.hpp` 缺失的实现证据见审阅记录。

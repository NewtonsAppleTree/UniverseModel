# 张量维度、区域与部分结果契约

本文规定跨模块传递张量需求时应保留的语义，当前为设计提案。基础对象仍见[公共契约](contracts.md)，实际可调用字段见对应模型代码；切块算法和示例由[compiler](../../compiler/docs/tiling_and_reduction.md)维护。

## 1 先区分五个对象

| 对象 | 含义与必要信息 | 归属 |
| --- | --- | --- |
| 逻辑张量 Logical Tensor | 身份/内容版本、shape、dtype、各轴语义；不绑定特定存储副本 | contracts/workload；由 workloads 提供 |
| 逻辑区域 Tensor Region / ROI | 某张量坐标中的元素集合、有效范围；不直接表示地址或传输 | contracts/plan；由 compiler 推导 |
| 存储视图 Storage View | 某物理副本的轴顺序、stride、offset、packing、padding、地址域与别名 | 公共语义在 contracts；compiler/memplan 选择，存储资源拥有实际数据 |
| 硬件请求 Resource Request | 该区域需要哪些读/写/搬运/计算、数量与完成条件 | compiler/lowering 产生静态需求；runtime 提交，硬件模型执行 |
| 部分结果 Partial Result | 尚未完成指定归并的中间值、输出区域、覆盖的规约分区、数值规则 | contracts/plan 描述；compiler 规划，runtime 跟踪完成 |

轴编号只描述一个确定 layout 的位置。例如 axis=2 在某布局里可以是 head，在另一布局里可以是 feature；它不能独立说明维度语义、长度或算法中的规约角色。相同 rank/shape 也不证明数据可以直接互换。

## 2 最小维度词汇与单位

以下为专业语义名，具体实现可使用简短变量，但不继承外部头文件的 `k*` 常量作为公共 API。

| 名称 / 专业术语 | 单位 | 关系与边界 |
| --- | --- | --- |
| batch_size | sample | 本次逻辑批次；不同样本能否独立由算子决定，含批统计/全局 loss 时需额外依赖 |
| query_length / kv_length | token position | 分别为 S_q、S_kv；decode 常见 S_q=1、S_kv 为已有上下文加本次可见 token，不能共用一个 S |
| model_width / query_width | element | H_model 与 n_q·d_q 分别定义；常见配置取二者相等，不是所有 attention 的必然约束 |
| query_head_count / kv_head_count | head | 均匀 GQA 要求 n_q % n_kv=0，group_size g=n_q/n_kv；一个 KV group 的 Q 特征宽为 g·d_q，总 Q 宽为 n_kv·g·d_q |
| query_key_dim / value_dim | element/head | Q·Kᵀ 要求参与点积的 d_q=d_k；d_v 可以另定义，attention 输出每 query head 有 d_v 个元素 |
| gemm_m / gemm_n / gemm_k | element index / extent | Y[M,N]=X[M,K]W[K,N]；M/N 是该操作的输出迭代轴，K 是收缩轴。权重 [K,N] 是本例约定，不是所有库的物理存储顺序 |
| routed_token_count / expert_count / route_top_k | token assignment、expert、route/token | 每 expert 的 T_e 是路由后分配行数；无丢弃且每 token 恰好选 k 个专家时 ΣT_e=N_token·k。它不等于全局唯一 token 数 |

密集张量展平 token 轴时可取 M=B·S_q；变长/压紧 batch 则可能为 M=Σ有效长度，并需要 token 到原样本/位置的索引映射。

## 3 逻辑 ROI 的最小规则

首版只需要逐维单位步长的半开区间：ROI=Π_i[start_i,end_i)。每维满足 0≤start_i≤end_i≤shape_i，extent_i=end_i−start_i，逻辑元素数为 Π_i extent_i。任一 extent=0 表示空区域；空区域不生成数据动作，但不能删除仍存在的控制依赖。

| 操作 | 必须保留的语义 |
| --- | --- |
| 分区 Partition | 分块覆盖完整目标范围；用于独立输出的块互不重叠，规约分块各自记录所覆盖的收缩范围 |
| 并集 Union | 多消费者需求可能是不连续区域；精确并集与覆盖包围盒必须区分 |
| 保守覆盖 Cover | 可用较大区域供数，但额外元素、padding/过滤、容量和访问量须计入；不能把覆盖盒当成精确需求 |
| 广播 Broadcast | 源 extent=1 的轴映射到 [0,1)，多个逻辑位置可别名到同一存储元素；写入/规约语义另定 |
| 变形 Reshape / Transpose | 通过显式坐标映射保持元素身份；单个矩形 ROI 的像不一定还是一个矩形，物理重排也不一定免费 |
| Gather / Scatter | 数据相关索引需要索引集或运行时绑定；无法静态获知时声明保守范围/条件需求，不伪造连续精确 ROI |

零长度维度、标量、负轴、负 stride、越界 padding 等是否支持，由具体操作/适配器能力定义。当前 `TensorLayout` 只接受非空 rank、非负 byte stride；提案不能自动扩大其实现范围。

## 4 从坐标到存储与流量

对 byte-addressable 的 strided view：addr(index)=base+Σ_i index_i·stride_bytes_i。逻辑 ROI 的形状只决定元素数，只有结合该副本的 stride/packing 才能生成地址、DMA 段和存储 transaction。

当前可复用 [TensorLayout](../../chipmodel/control/data_movement.py)：`logical_bytes` 计逻辑元素引用，`span_bytes` 计从起点到末元素的覆盖跨度，二者都不等于唯一物理字节或实际 DMA 流量。INT4 等打包需额外 bit/word 地址映射，不能强行设 `element_bytes=0.5`。

仍须分别统计[逻辑、分配、访问与线路字节](../methods/workload_and_numeric_semantics.md)。例如零 stride 广播不是复制所有数据，非连续 ROI 也不等于搬运整个地址包围区间。

## 5 部分结果与完成条件

一个部分结果最少明确：属于哪个逻辑输出及内容版本、输出 ROI、规约种类、覆盖的输入分区、存储/累加 dtype、归并顺序与最终处理。普通 shape/dtype 相同不足以允许归并。

| 场景 | 归并对象与完成要求 |
| --- | --- |
| 非规约轴切分 | 各 tile 已完成对应输出子区域，按坐标组装；不是数值 reduce |
| split-K GEMM | 同一输出 ROI 上的部分乘积和相加，K 分区不重不漏；bias、beta·C、activation/最终量化按语义在适当完成点执行 |
| Attention split-context | 合并逐 query 的 max、归一化分母、未归一化加权分子状态，再得到输出；不能直接相加各块已归一化输出 |
| MoE scatter-add / 梯度 | 重复目标的贡献按明确权重与规约规则归并；简单覆盖写入会丢贡献 |

规约对浮点累加顺序、整数溢出和量化位置敏感；数学可结合不代表 bitwise 相等。所有必要分区均完成且结果可见，输出才满足完整操作的完成条件；请求接受、源缓冲释放和目标可见仍遵守[生命周期](resource_lifecycle.md)。

## 6 接入方式

workloads 给出 shape/算子/数值语义 → compiler 推导需求与分区/规约计划 → memplan/lowering 绑定存储视图及资源动作 → runtime 按依赖提交 → 模型返回局部结果/完成 → evaluation 按相同边界计量。

独立入口可以只接收一个已知张量区域和算子，不要求完整图。暂时用现有值对象/显式函数参数表达所需信息；真正出现跨模块交换需求时再冻结最小 schema，不提前建设任意区域集合框架。

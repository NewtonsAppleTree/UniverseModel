# workloads 开发任务与验收计划

2026-11-23。依据[项目使命](../../PROJECT_MISSION.md)、[参数清单](../../ARCHITECTURE_PARAMETERS.md)和[工程接口](../../ENGINEERING_FRAMEWORK.md)，先提供独立于硬件的任务、数据、状态与正确性基准，再接入映射和研究比较。当前已有GEMM/MatVec、稳定测试输入、整数/有理数参考，以及Linear/ReLU/mean-MSE/plain-SGD训练短链，首包复用这些能力。

## 任务划分

| 包 | 研究什么 | 怎样建模与交付 | 如何证明 / 状态 |
| --- | --- | --- | --- |
| W0 盘点与边界 | 哪些已有语义可复用，哪些目标尚未覆盖 | 明确workloads只依赖contracts；实际访存归映射，目标时间归硬件/执行，研究比较归evaluation | 核对源码、UNITS与历史测试；已完成盘点 |
| W1 Attention任务与参考 | query长度、KV长度、GQA/MQA、因果可见性怎样改变输出和工作量 | contracts/workload的专用Spec/Input；kernels生成/计数；reference提供高精度稳定softmax与Attention；d_qk和d_v独立 | 小例手算、60组独立float算法、GQA显式复制等价、掩码反例、极值与宿主预算；已完成 |
| W2 KV逻辑状态 | prefill、分块追加和decode是否引用正确历史，KV共享是否正确计量 | graphs下不可变KV快照；逻辑容量、版本、源身份及head-major追加；不包含物理page分配/调度 | 整段因果Attention与逐token/分块追加等价；跨状态、超容量、布局和旧快照不变反例；已完成 |
| W3 profiles与输入来源 | 哪些形状/数据构成可复现的有限案例，合成输入能支持什么结论 | profiles保存固定案例及假设；datasets用相对路径/原始SHA256/来源/用途绑定Attention数据；真实trace和公开数据集按课题补 | 原始字节篡改、路径/大小/语义绑定拒绝；同seed确定性；不把合成数据标为真实模型质量；已完成 |
| W4 映射接入 | 同任务下切块/融合/KV布局如何影响硬件工作 | 完整query-block计划，QK/softmax/AV解释，shared/expanded KV与fused/spill，格式匹配MAC/DMA服务 | 已完成：区域/工作守恒、18组随机×4策略、手算搬运、5方案含容量失败；真实整任务时间仍未知 |
| W5 任务质量与代表性 | 数值方法在选定真实任务和输入下是否满足质量 | UCI原始Iris+标准化RBF Attention分类，90/30/30划分、validation选参、数值变体、实际NumPy版本 | 已完成限定真实任务：3个split×4变体，独立matmul/直接距离对照、质量门槛和负对照；不外推LLM/服务代表性 |
| W6 实验与工程验收 | 是否可独立调用、保留所有输入/失败并回读 | 专业接口+严格配置+RunRecord/bundle；原始代码/数据身份、示例、UNITS、STATUS、CI与wheel | 已接通完整27例统一验收；最终全回归、安装包及来源证据见[完成报告](completion.md) |

## 首包范围与参数

W1–W3及对应W6构成首个完整交付。Attention为给定Q/K/V后的缩放点积与softmax，不包含投影、位置编码、dropout、反向、量化或整个Transformer。参数为B、Hq、Hkv、Sq、Skv、Dqk、Dv、显式scale及因果query起点；Hq必须被Hkv整除。布局分别为[B,Hq,Sq,Dqk]、[B,Hkv,Skv,Dqk/Dv]；连续逻辑数组不代表物理地址或搬运路径。

完整矩形计算需求和因果有效配对分别列出；KV唯一容量按Hkv计，不按Hq复制。未屏蔽元素参与稳定softmax，全屏蔽行在本版语义中不可构造。参考中的Decimal精度和max_elements/max_score_pairs/max_macs是宿主验证预算，不是硬件精度或容量。参考输出不与自身比较后生成质量通过结论。

KV快照只维护一个逻辑流的均匀批次、固定head/维度和连续token追加；版本与内容身份用于拒绝错误源引用，纯函数允许显式分支，不能代替全局并发提交协议。page padding、prefix物理共享、淘汰和运行时调度属于后续映射/执行层。

profiles首包为明确标记的合成案例，覆盖prefill/decode、上下文长度与head共享；datasets首包提供本地确定性夹具读取和可追溯输入边界。真实服务分布、准确率/困惑度/收敛结论需要W5证据。

## 首包验收与下一步

W0–W3及对应W6已完成。独立接口、公式、误差/预算、10案例和执行命令见[用法](foundation_usage.md)。新增27项测试，全回归395项中393通过、2项可选PyTorch跳过；规则/结构通过，86份wheel源码逐字节核对，隔离安装包复现实验与KV追加。完整本地证据在`.build/workloads-foundation-20261123`，来源及限制由[STATUS](../../docs/STATUS.md)记录。

本轮后续已完成W4与限定真实课题的W5，详见[映射与质量指南](mapping_and_quality.md)。W4按query分块、score驻留和KV副本实现实际功能/搬运，不提前承诺online-softmax或context partition；W5选择有明确来源、可在本轮完整复现的RBF分类任务，建立可替换的来源/分割/拟合/选参/质量接口，并用NumPy实际交叉验证。它证明所选任务的数值和质量行为，不代表语言模型质量或服务分布。

## 本轮规划关闭条件

W0–W6都有独立接口、实际执行及对应证据，不再保留本轮未执行的开发包。统一验收覆盖27例：4个预期执行失败、3个运行成功但质量不合格的负对照；后者必须按真实结果保留。来源、测试、wheel及全部能力边界统一见[完成报告](completion.md)。

完成审计另外修复分类概率端点舍入的误拒绝，并加强保存结果的数值重分析、计划/容量/流量守恒及质量证据检查；新增记录保留参考与外部输出，旧记录按原证据深度读取。范围与验收见[收尾审计](completion_audit.md)。

后续按研究主张新增课题：上下文切块与online softmax、真正低精度打包/转换和量化误差、模型投影/位置编码/Attention反向、真实LLM/请求trace、通用图/autograd、目标标量/访存时序及器件成本。这些有明确触发条件，未计入已完成能力；本轮关闭既定任务规划，不表示实现所有可能的工作负载。

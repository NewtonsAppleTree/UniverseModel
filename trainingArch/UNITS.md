# trainingArch：训练参数与候选分析单元

当前是场景设计文档，未定义 Python 类、可执行 schema 或参数默认值。通用术语/单位/公式以[顶层参数清单](../ARCHITECTURE_PARAMETERS.md#81-训练)为查阅入口；实际硬件字段见 [chipmodel/UNITS.md](../chipmodel/UNITS.md)。

| 候选分析职责（非已实现 Unit） | 输入参数与单位 | 输出与关键关系 |
| --- | --- | --- |
| 训练工作量 | 各算子 shape [element]、dtype [bit/element]、microbatch [sample]、累积次数 [次] | forward/backward/update 的 FLOP/op 与 B/step；不使用一个固定倍数替代所有算子 |
| 显存账本 | 参数 [个]、各对象精度 [bit]、分片/复制、生命周期 [s/阶段]、分配粒度 [B] | 每 rank 的 live/allocated B 与峰值；峰值为同一时刻活跃对象之和的最大值 |
| 并行与通信 | DP/TP/PP/EP/CP group [rank]、tensor bytes [B]、拓扑、调度依赖 | 每 rank 和每链路的 B/collective、通信步骤、受依赖与共享资源约束的重叠 |
| 训练指标 | 有用模型 FLOPs、执行窗口 [s]、精度对应峰值 [FLOP/s]、能量 [J] | MFU=有用模型 FLOPs/(时间×峰值)；重计算 FLOPs 另记；step/s、有效 token/s、J/step |

最关心：完整 step 工作量、每 rank 峰值容量、跨设备通信、重计算与流水 bubble。分片必须逐对象定义，不能把所有显存统一除以设备总数。

独立使用时，可只做某个 GEMM、某层激活容量或某次 collective 的估算。输入记录模型/形状/精度/并行条件，输出记录单位、范围和假设；无须先运行完整训练流程。训练场景特有公式今后在本目录实现，硬件服务规则继续复用基础模块。

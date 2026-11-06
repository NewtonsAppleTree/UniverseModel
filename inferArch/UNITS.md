# inferArch：推理参数与候选分析单元

当前是场景设计文档，未定义 Python 类、可执行 schema 或参数默认值。通用术语/单位/公式以[顶层参数清单](../ARCHITECTURE_PARAMETERS.md#82-推理)为查阅入口；实际硬件字段见 [chipmodel/UNITS.md](../chipmodel/UNITS.md)。

| 候选分析职责（非已实现 Unit） | 输入参数与单位 | 输出与关键关系 |
| --- | --- | --- |
| 阶段工作量 | prompt/context/output [token]、batch [request]、各算子 shape/dtype | prefill/decode 的 FLOP/op、各存储与链路边界 B；不能仅由阶段名断定瓶颈 |
| KV 容量与流量 | 各层 KV heads [个]、K/V 维度 [element]、精度 [bit]、有效长度 [token]、布局 | 有效 B、分配 B、read/write/transfer B；按 KV heads 统计，分页/元数据/复制分别计算 |
| 请求与指标窗口 | 到达、首/后续/末 token 时间戳 [s]、输出数 [token]、质量/SLO | TTFT、ITL；N_out>1 时 TPOT=(t_last−t_first)/(N_out−1)；单 token 输出不定义 TPOT |
| 推理效率 | 完成输出 token、时间 [s]、能量 [J]、成本 [货币] | token/s、满足 SLO 的 goodput、J/output-token、成本/10⁶ token；明确 prefill、空闲、主机和网络边界 |

最关心：请求长度与并发、KV 的真实物理布局、权重/上下文读取流量、阶段依赖和服务指标。MHA/GQA/MQA、TP 分片、前缀共享分别建账，不能通过一个 batch 或 GPU 数统一缩放。

独立使用时，可只估算某层 KV 容量、一个 decode GEMM 或一次 KV 传输。输入带明确阶段/形状/精度/布局条件，输出带单位和假设；不需要完整模型部署或服务请求链。推理场景特有公式今后在本目录实现，公共硬件服务不重复定义。

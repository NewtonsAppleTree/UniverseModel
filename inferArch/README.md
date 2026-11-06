# 推理场景架构

本目录整理 AI 推理的阶段、资源需求与设计权衡，是复用仓库基础模块的场景入口。当前仅有文档，尚无独立推理分析器、请求调度器或服务模拟器；状态以 [STATUS](../docs/STATUS.md) 为准。

## 设计对象

| 对象 | 要回答的问题 |
| --- | --- |
| 请求与阶段 | prompt/output/context 长度、到达分布与并发；prefill、decode 各做多少工作 |
| 数据驻留 | 权重、KV、workspace、量化元数据的有效与物理容量；分页、共享、交换和淘汰 |
| 映射与服务 | batching、TP/PP/EP、prefill/decode 分离怎样改变工作、流量与依赖 |
| 数值与策略 | 量化、稀疏、融合、投机解码的质量目标与额外工作是否纳入 |
| 结果 | TTFT、TPOT/ITL、延迟分布、有效吞吐、J/token，以及容量/功率/SLO 约束 |

参数及公式查 [UNITS.md](UNITS.md) 和[顶层清单的推理部分](../ARCHITECTURE_PARAMETERS.md#82-推理)。计算、存储和链路仍复用公共模型，不按“推理专用”再建立另一套硬件峰值/成本定义。

## 与基础模块的边界

- workloads 提供请求、模型和数值语义；compiler 提供布局、量化与算子映射；runtime 负责 batching、派发等动态策略。
- chipmodel/systemmodel/clustermodel 提供硬件服务和连接；simulator 负责时间推进，evaluation 组织实验。
- 本目录组织推理场景的假设、资源账本与指标解释；先分析局部阶段，再按研究需要组合。

使用顺序：明确请求与质量/SLO → 分开 prefill/decode → 计算权重/KV/工作量 → 映射数据路径 → 对照资源约束 → 报告窗口一致的指标。P99 需要请求/运行分布；单个理想公式不能给出尾延迟。

规则继承根目录 [AGENTS.md](../AGENTS.md)。只在需求明确时增加公式函数或有状态模型，不预建通用服务框架。

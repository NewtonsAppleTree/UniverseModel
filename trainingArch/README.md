# 训练场景架构

本目录整理 AI 训练的阶段、资源需求与设计权衡，是复用仓库基础模块的场景入口。当前仅有文档，尚无独立训练分析器或执行器；状态以 [STATUS](../docs/STATUS.md) 为准。

## 设计对象

| 对象 | 要回答的问题 |
| --- | --- |
| 任务与数值 | 训练什么模型、什么形状/精度；forward、backward、optimizer 各有多少工作 |
| 数据驻留 | 权重、梯度、master weights、optimizer states、激活、workspace 何时存在，放在哪里 |
| 并行与映射 | DP/TP/PP/EP/CP 怎样分组；每个对象是分片、复制还是独占；microbatch 与梯度累积如何组织 |
| 通信与重叠 | collective 的参与组、输入输出字节、实际路径；哪些依赖与共享资源限制重叠 |
| 结果 | step time、有效 token/s、每 rank 峰值容量、MFU、J/step，以及功率/热约束 |

参数及公式查 [UNITS.md](UNITS.md) 和[顶层清单的训练部分](../ARCHITECTURE_PARAMETERS.md#81-训练)。相同硬件用于训练或推理时，复用同一套资源定义，不复制 CPU/GPU/CIM/存储模型。

## 与基础模块的边界

- workloads 提供模型、算子、数据和数值语义；compiler 提供切块、分片、放置及静态依赖。
- runtime 负责动态调度策略；chipmodel/systemmodel/clustermodel 提供硬件服务与物理连接。
- simulator 负责执行时间推进；evaluation 组织实验与比较。本目录组织训练场景的输入假设、资源账本和指标解释。

使用顺序：明确一次 step → 逐对象计算容量与生命周期 → 逐阶段展开操作/流量 → 选择映射与资源 → 计算有适用条件的估计或运行已有模型 → 比较指标。当前只有公共基础模型可调用，不能把这条设计流程当作已有训练仿真命令。

新增实现前先确定输入/输出与独立验证案例；公式优先用纯函数，只在有独立状态时建类。规则继承根目录 [AGENTS.md](../AGENTS.md)。

# 工作负载与参考

工作语义和代表性输入定义需要完成什么，并提供独立正确性基准。

实现进度统一见[实现状态](../docs/STATUS.md)；本页说明职责与目录。

## 阅读入口

- [W0–W6 完成范围、统一验收与后续研究条件](docs/completion.md)
- [收尾审计：概率舍入与保存证据重分析](docs/completion_audit.md)
- [Attention 映射与真实任务质量](docs/mapping_and_quality.md)
- [开发任务 W0–W6 与验收计划](docs/development_plan.md)
- [Attention、逻辑 KV、数据来源与独立调用](docs/foundation_usage.md)
- [Linear 训练短链、梯度/更新和外部参考](../evaluation/docs/training_step.md)

- [当前任务、数据、状态与参考接口](UNITS.md)
- [GEMM/MatVec 实验、独立调用与数值限制](../evaluation/docs/linear_mapping.md)
- [模块设计](docs/design.md)
- [顶层架构](../docs/architecture/design.md)
- [公共契约](../docs/interfaces/contracts.md)
- [参数与数学方法](../docs/methods/parameters_and_math.md)
- [第一性原理](../docs/architecture/first_principles.md)

## 子目录

```text
kernels
graphs
reference
profiles
datasets
```

依赖约束：contracts。依赖指公开接口；具体状态归属和运行时调用见模块设计。

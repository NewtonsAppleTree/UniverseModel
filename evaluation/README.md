# 实验与优化

在约束和不确定性下比较可复现的端到端结果。

当前状态：已建立目录和设计契约；执行模型尚未实现。

## 阅读入口

- [模块设计](docs/design.md)
- [顶层架构](../docs/architecture/design.md)
- [公共契约](../docs/interfaces/contracts.md)
- [参数与数学方法](../docs/methods/parameters_and_math.md)
- [第一性原理](../docs/architecture/first_principles.md)

## 子目录

```text
experiments/runner
experiments/sweeps
analysis
optimization
calibration
```

依赖约束：contracts、configuration、costmodel、chipmodel、systemmodel、clustermodel、workloads、compiler、runtime、simulator、artifacts。依赖指公开接口；具体状态归属和运行时调用见模块设计。

# 工作负载与参考

工作语义和代表性输入定义需要完成什么，并提供独立正确性基准。

当前状态：已建立目录和设计契约；执行模型尚未实现。

## 阅读入口

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

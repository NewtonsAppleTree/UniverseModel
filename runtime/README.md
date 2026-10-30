# 运行时策略

策略只能基于已发生的信息发出合法操作，提交与完成必须分开。

当前状态：已建立目录和设计契约；执行模型尚未实现。

## 阅读入口

- [模块设计](docs/design.md)
- [顶层架构](../docs/architecture/design.md)
- [公共契约](../docs/interfaces/contracts.md)
- [参数与数学方法](../docs/methods/parameters_and_math.md)
- [第一性原理](../docs/architecture/first_principles.md)

## 子目录

```text
dispatch
streams
communication/p2p
communication/collectives
policies
```

依赖约束：contracts。依赖指公开接口；具体状态归属和运行时调用见模块设计。

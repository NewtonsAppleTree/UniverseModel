# 参数与结果界面

让用户准确理解并修改同一份模型定义，不产生另一套参数真相。

当前状态：已建立目录和设计契约；执行模型尚未实现。

## 阅读入口

- [模块设计](docs/design.md)
- [顶层架构](../docs/architecture/design.md)
- [公共契约](../docs/interfaces/contracts.md)
- [参数与数学方法](../docs/methods/parameters_and_math.md)
- [第一性原理](../docs/architecture/first_principles.md)

## 子目录

```text
forms
views/topology
views/package
views/mapping
views/timeline
services
```

依赖约束：contracts、configuration、evaluation。依赖指公开接口；具体状态归属和运行时调用见模块设计。

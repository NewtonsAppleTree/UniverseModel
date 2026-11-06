# 集群与网络

集群扩展受通信割集、注入能力和共享路径限制。

实现进度统一见[实现状态](../docs/STATUS.md)；本页说明职责与目录。

## 阅读入口

- [模块设计](docs/design.md)
- [顶层架构](../docs/architecture/design.md)
- [公共契约](../docs/interfaces/contracts.md)
- [参数与数学方法](../docs/methods/parameters_and_math.md)
- [第一性原理](../docs/architecture/first_principles.md)

## 子目录

```text
composition/cluster
composition/groups
fabric/links
fabric/switches
fabric/routing
topology
```

依赖约束：contracts、systemmodel、costmodel。依赖指公开接口；具体状态归属和运行时调用见模块设计。

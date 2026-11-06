# 公共契约

语义与单位必须一致，版本变化必须可识别。

实现进度统一见[实现状态](../docs/STATUS.md)；本页说明职责与目录。

公共实验记录、规范化与指标单位的代码入口见 [UNITS.md](UNITS.md)；通用接入见[工程框架](../ENGINEERING_FRAMEWORK.md)。

## 阅读入口

- [模块设计](docs/design.md)
- [顶层架构](../docs/architecture/design.md)
- [公共契约](../docs/interfaces/contracts.md)
- [参数与数学方法](../docs/methods/parameters_and_math.md)
- [第一性原理](../docs/architecture/first_principles.md)

## 子目录

```text
hardware
workload
plan
events
results
units
versions
```

依赖约束：不依赖其他业务模块。依赖指公开接口；具体状态归属和运行时调用见模块设计。

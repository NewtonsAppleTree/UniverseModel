# 板卡与节点

设备性能必须经过真实主机、地址空间和共享 I/O 路径才能形成系统性能。

实现进度统一见[实现状态](../docs/STATUS.md)；本页说明职责与目录。

## 阅读入口

- [S0–S7任务规划与当前范围](docs/development_plan.md)
- [S0/S1独立调用、七例与验证边界](docs/foundation_usage.md)
- [已实现Unit与参数导航](UNITS.md)
- [模块设计](docs/design.md)
- [顶层架构](../docs/architecture/design.md)
- [公共契约](../docs/interfaces/contracts.md)
- [参数与数学方法](../docs/methods/parameters_and_math.md)
- [第一性原理](../docs/architecture/first_principles.md)

## 子目录

```text
composition/board
composition/node
io/pcie
io/cxl
io/dma
io/nic
memory
topology
```

依赖约束：contracts、chipmodel、costmodel。依赖指公开接口；具体状态归属和运行时调用见模块设计。

当前S0/S1已实现板卡/节点归属、地址域/端口、显式转发、共享资源引用和权限路径查询。设计文档中的内存/NUMA、PCIe/DMA/CXL/NIC服务、队列与实际时序仍按后续任务推进。

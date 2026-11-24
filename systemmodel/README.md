# 板卡与节点

设备性能必须经过真实主机、地址空间和共享 I/O 路径才能形成系统性能。

实现进度统一见[实现状态](../docs/STATUS.md)；本页说明职责与目录。

## 阅读入口

- [S0–S7任务规划与当前范围](docs/development_plan.md)
- [S0/S1独立调用、七例与验证边界](docs/foundation_usage.md)
- [S2内存/NUMA、十五例与静态证据](docs/memory_usage.md)
- [S3 PCIe/DMA直传、中转与十四例](docs/transfer_usage.md)
- [S4 CXL能力、分层驻留与显式迁移十五例](docs/tiering_usage.md)
- [S5 NIC供数、RDMA条件与集群边界十二例](docs/network_usage.md)
- [S6 AI数值、节点驻留与搬运比较十八例](docs/ai_usage.md)
- [S0–S7 整体验收报告](docs/acceptance.md)
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

当前S0–S7基础计划已接通：节点/内存/PCIe/DMA/CXL静态边界、显式缓冲NIC与cluster计量、三类AI任务独立数值及节点方案比较。统一验收入口为`python tools/validate_systemmodel.py --output .build/systemmodel-acceptance`，随后`--read`回读六组81例。完整协议、动态队列/可见性、端到端性能和能耗仍按具体研究证据需求深化，实际测试见STATUS。

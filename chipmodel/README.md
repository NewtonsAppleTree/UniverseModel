# 芯片与封装

有限资源上的状态变化决定可实现的计算和数据移动。

实现进度统一见[实现状态](../docs/STATUS.md)；本页说明职责与目录。

## 阅读入口

- [顶层参数清单](../ARCHITECTURE_PARAMETERS.md)：按研究路径选参数，查单位、公式、适用条件与来源
- [系统级设计](docs/system_model_design.md)：第一性原理、训练/推理需求、资源关系与分析边界
- [所有子模块的 Unit 与参数](UNITS.md)：逐目录专业术语、单位、关系、关键参数和独立接口
- [本模块开发规则](AGENTS.md)：继承全仓库规则，保持模型与实现简洁
- [模块设计](docs/design.md)
- [Unit 类与参数设计](docs/unit_model_design.md)：Python/C++ 分工、类和状态、公式、单位、接口与调用顺序
- [ADC 模型与用法](docs/adc_model.md)：独立输入电压量化、参数推导、理想批次时间与运行示例
- [子系统与单元覆盖清单](docs/component_inventory.md)：按八个子目录展开 CPU/GPU 内部、DDR/PHY、控制、互连、物理与管理单元
- [硬件组件目录](../docs/reference/hardware_component_catalog.md)：输入输出、技术指标和存储子系统参数
- [顶层架构](../docs/architecture/design.md)
- [公共契约](../docs/interfaces/contracts.md)
- [参数与数学方法](../docs/methods/parameters_and_math.md)
- [第一性原理](../docs/architecture/first_principles.md)

## 子目录

下面列出现有目录。候选单元与建议新增子目录见覆盖清单；目录不是单元已实现的证明。

| 入口 | 负责的内容 |
| --- | --- |
| compute | CPU/GPU/NPU/CIM 及可复用执行原语 |
| memory | 存储、cache、地址/一致性、DDR 等介质与控制器/PHY |
| interconnect | 总线、NoC、D2D、协议桥、跨时钟与物理链路适配 |
| control | 命令、搬运、发射同步、时钟电源控制、观测与管理 |
| composition | Core/Tile/Die/Package 等实例组合及外部视图 |
| packaging | 几何、热、供电与制造/可靠性条件 |
| registry | 类型、版本、能力、校验和模型工厂 |
| docs | 模块设计、单元说明、接口与验证入口 |

```text
compute/cpu
compute/gpu
compute/npu
compute/cim/arrays
compute/cim/encoding
compute/cim/periphery
memory/sram
memory/dram
memory/flash
memory/controllers
interconnect/noc
interconnect/d2d
control
composition/tile
composition/die
composition/package
packaging/geometry
packaging/thermal
registry
```

依赖约束：contracts、costmodel。依赖指公开接口；具体状态归属和运行时调用见模块设计。

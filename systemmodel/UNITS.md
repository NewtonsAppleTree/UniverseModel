# systemmodel：板卡与节点资源边界

本模块拥有节点内资源的放置/归属、地址域、端口与连接声明，引用芯片模型身份和共享容量；不复制芯片状态。S0/S1实现静态能力与路径判断，目标执行、实际容量预留、访存、时延与能量尚未覆盖。

| Unit与子模块 | 当前行为与边界 |
| --- | --- |
| [composition](composition/UNITS.md) | BoardSpec/NodeSpec引用同一清单，校验独立板卡、节点与设备归属 |
| [topology](topology/UNITS.md) | 显式有向连接/转发、权限、地址域、共享引用、最少跳数或指定路径 |
| [公共契约](../contracts/hardware/UNITS.md) | AddressDomainSpec/SystemPortSpec；标准库值对象，不拥有硬件状态 |
| io/pcie、io/dma、memory、io/cxl、io/nic | 后续S2–S5按研究问题实现；当前仅有连接/引用声明，不代表协议服务已实现 |

顺序为资源/域/端口 → SystemTopology校验 → BoardSpec独立校验或NodeSpec组合 → PathRequest → find_path/validate_path。配置与运行记录由configuration/evaluation/artifacts接入，独立调用不依赖它们。

敏感条件是有向连接、逐段访问权限、显式转发、scope/owner与共享ID。address_bits只约束整数地址范围，不是物理容量；capacity_Bps保留声明口径和来源，首包不计算路径带宽、时间下界或执行时间。容器不收费、重复引用不增容、访问可达不证明数据可见。

验证含独立小图穷举、非法引用/权限/归属、共享上行、7例成功失败记录及回放。研究问题、参数筛选、独立用法与证据边界见[首包指南](docs/foundation_usage.md)；进度见[开发计划](docs/development_plan.md)与[STATUS](../docs/STATUS.md)。

<!-- model-fields:start -->



<!-- model-fields:end -->

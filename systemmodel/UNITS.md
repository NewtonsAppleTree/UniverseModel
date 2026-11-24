# systemmodel：板卡与节点资源边界

本模块拥有节点内资源的放置/归属、地址域、端口与连接声明，引用芯片模型身份和共享容量；不复制芯片状态。S0/S1实现静态能力与路径判断，S2实现物理预留/地址/NUMA，S3增加PCIe/DMA工作和条件下界，S4增加CXL能力/平坦decoder与分层迁移静态证据；目标执行、真实访存、完整时延与能量尚未覆盖。

| Unit与子模块 | 当前行为与边界 |
| --- | --- |
| [composition](composition/UNITS.md) | BoardSpec/NodeSpec引用同一清单，校验独立板卡、节点与设备归属 |
| [topology](topology/UNITS.md) | 显式有向连接/转发、权限、地址域、共享引用、最少跳数或指定路径 |
| [公共契约](../contracts/hardware/UNITS.md) | AddressDomainSpec/SystemPortSpec；标准库值对象，不拥有硬件状态 |
| [memory](memory/UNITS.md) | 有限backing、对象/物理副本/地址别名、区间复用与NUMA精确成员；独立容量/地址/可达分析 |
| [io](io/UNITS.md) | S3 conventional PCIe posted-write帧计量、DMA启动/突发与整缓冲copy链、共享工作和必要时间界 |
| [io/cxl](io/cxl/UNITS.md) | 显式模式、平坦decoder与内存行工作；组合memory验证迁移瞬时预留，原生服务时间未知 |
| [io/nic](io/nic/UNITS.md) | S5显式buffer/DMA供数与接收、RDMA条件、唯一NIC方向预算导出；不执行真实网络服务 |

顺序为资源/域/端口 → SystemTopology校验 → BoardSpec独立校验或NodeSpec组合 → PathRequest → find_path/validate_path。配置与运行记录由configuration/evaluation/artifacts接入，独立调用不依赖它们。

S2继续 NodeSpec → MemorySystem → MemoryPlan → analyze_placement → resolve_span/analyze_access。物理预留按粒度取整，地址别名只引用同一副本，生命周期以逻辑phase声明；来源、假设和未知目标成本见[内存指南](docs/memory_usage.md)。

S3继续 MemorySystem + PcieProfile/PcieService/DmaEngine → DmaSystem + CopyBatch → analyze_transfers。源读、目标写、DMA cycle、frame及shared payload工作分项，显式整copy依赖与唯一预算形成条件下界，实际执行/能量仍未知；见[搬运指南](docs/transfer_usage.md)。

S4继续 MemorySystem → TieredMemorySystem/CxlMemorySystem → 同phase的MemoryPlan或TierMigration → analyze_residency/analyze_cxl_access/analyze_cxl_migration；兼容的非CXL.mem路径可用analyze_dma_migration。三个迁移快照均为静态候选，after不代表执行完成，见[分层指南](docs/tiering_usage.md)。

S5继续 DmaSystem + NicPort/NetworkEndpointSpec/方向预算 → NicSystem + NicBatch → analyze_nic；evaluation组合cluster的固定路径和local-only CopyBatch，见[NIC指南](docs/network_usage.md)。S6由evaluation/workloads/compiler保留专业数值实现并绑定实际输入字节、保守workspace和节点策略，见[AI指南](docs/ai_usage.md)。S7统一验收六组81例与来源/回读，完整数值和下界不等于目标执行/数据发布。

S0–S7已完成[整体验收](docs/acceptance.md)：成功/失败案例名单固定，保存源码清单的聚合哈希及每条RunRecord的来源交叉核对，历史回读不依赖当前源码身份。全仓测试、独立数值参考和wheel组合证据分别保存。

敏感条件是有向连接、逐段访问权限、显式转发、scope/owner与共享ID。address_bits只约束整数地址范围，不是物理容量；capacity_Bps保留声明口径和来源，首包不计算路径带宽、时间下界或执行时间。容器不收费、重复引用不增容、访问可达不证明数据可见。

验证含独立小图穷举、非法引用/权限/归属、共享上行、7例成功失败记录及回放。研究问题、参数筛选、独立用法与证据边界见[首包指南](docs/foundation_usage.md)；进度见[开发计划](docs/development_plan.md)与[STATUS](../docs/STATUS.md)。

<!-- model-fields:start -->



<!-- model-fields:end -->

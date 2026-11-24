# io：节点内搬运与硬件服务

本目录研究芯片接入节点之后的数据供给、共享瓶颈与中转代价。引用已有节点归属、地址域、物理预留与路径，不拥有芯片内部状态。S3实现静态posted-write搬运分析；独立功能/事件执行、队列接纳、数据可见性与物理能耗不由分析结果推断。

| 子模块 / Unit | 行为与边界 |
| --- | --- |
| [pcie](pcie/UNITS.md) | conventional TLP写事务的MPS、4 KiB边界、DWORD字节使能、协议开销与NRZ编码容量 |
| [dma](dma/UNITS.md) | 引用已有DmaParams/ClockDomain；显式本地源、完整copy chain、整缓冲staging、共享工作和条件时间下界 |
| [cxl](cxl/UNITS.md) | S4显式type/启用模式、平坦decoder与原生内存行数据；不借用PCIe帧或推定一致性 |
| [nic](nic/UNITS.md) | S5显式buffer与DMA供数/接收、注册/权限/阶段校验、标准库端点导出；cluster按唯一NIC预算计量 |

调用：MemorySystem → PcieProfile/PcieService/DmaEngine → DmaSystem → CopyBatch → analyze_transfers。专业接口只依赖contracts/chipmodel及systemmodel内部模块；configuration/evaluation/artifacts在上层提供实验组织。资源实例唯一归属，时钟cycle先换为second，各链路的完整包时间不直接逐跳相加。

S4另可独立调用 MemorySystem → CxlMemorySystem → analyze_cxl_access；经memory/migration组合分层三状态预留与明确传输方式。来源、未知成本与15例见[S4指南](../docs/tiering_usage.md)。

S5另接 DmaSystem → NicSystem/NicBatch → analyze_nic；共享本地CopyBatch避免漏算多个流的工作/hazard，方向能力和数据绑定与fabric在evaluation组合，见[NIC指南](../docs/network_usage.md)。

敏感量是payload大小、源/目的布局、MPS、4 KiB位置、DMA启动/突发、共享容量与链依赖。具体参数/公式以各子目录代码与UNITS维护。本容器无独立物理计量。验证、来源和未覆盖项见[S3指南](../docs/transfer_usage.md)及[STATUS](../../docs/STATUS.md)。

<!-- model-fields:start -->



<!-- model-fields:end -->

# S5：节点供数、NIC 与集群边界

本包检验：多个设备共享网卡时，限制来自节点内供数还是NIC/fabric；注册内存是否真的能通过声明的路径访问；同节点消息怎样使用已有本地服务。依照[使命](../../PROJECT_MISSION.md)，节点资源仍由systemmodel拥有，网络路径由clustermodel拥有，组合由evaluation负责，端点通过标准库公共契约交换。

## 独立模型与组合

```python
from systemmodel.io.nic.model import analyze_nic
from evaluation.experiments.runner.system_network import analyze_network

local = analyze_nic(nic_system, nic_batch)
combined = analyze_network(study, case)
```

NicSystem/NicBatch的来源、参数、单位、buffer归属、RDMA权限和独立调用顺序见[NIC UNITS](../io/nic/UNITS.md)。本版明确采用完整缓冲：应用内存→NIC buffer→网络→远端NIC buffer→应用内存。PCIe供数/接收由S3 CopyBatch分析，buffer在S2中显式预留；不把真实NIC读请求、零拷贝或RDMA原生协议实现混入本版。

NetworkStudy固定全部node和ClusterSpec。cluster端点与node导出的endpoint必须完全相同，NIC容量必须逐项相同；node-local摘要不能额外叠加到cluster。node资源全局唯一。每个NodeWork将该node全部同时流量放进一个batch；每条MessageBinding唯一关联TX/RX flow，或同节点的一条CopyChain，完整名单、方向、rank/endpoint、object/version/offset/bytes都校验。

同节点消息不进入fabric分析，local CopyChain提供服务；跨节点消息使用显式fabric route。当前不混合一个node上的local-only batch与NIC batch，以免漏算共享工作或hazard；此组合需要新增统一调度/账本接口，不能分别估计后直接相加。

`known_service_lower_bound_s = max(各node的DMA必要界, fabric通信必要界)`。fabric中的NIC约束只计一次；local与fabric资源ID必须互斥。该式允许数据均已ready的放宽条件，是实际完整执行的条件必要界；不求实际排队、重叠或端到端完成时间，也不把各hop整copy时间逐段加起来。

## 十二例与验收

```powershell
python -m example.system_network_demo --output .build/system-network
python -m example.system_network_demo --read .build/system-network
```

| 候选 | 预期与可检验观察 |
| --- | --- |
| single | 512 B；每node local下界512 ns，NIC256 ns，fabric128 ns，合成512 ns |
| shared_nic | 两路host/device各512 B共享同一NIC；local1024 ns，NIC512 ns，fabric256 ns，合成1024 ns |
| rdma_write | 显式启用并具有源read/目标write注册；仍只给静态可行性 |
| same_node | 512 B由本地DMA完成必要工作；fabric和NIC流量为0，local下界512 ns |
| missing_registration / wrong_permission | 缺少注册或访问方向授权，失败 |
| expired_registration / short_registration | phase不活跃或注册范围不足，失败 |
| wrong_data_version / missing_flow_binding | 数据版本或完整名单不一致，失败 |
| buffer_capacity / wrong_direction | 缓冲容量不足或TX/RX端点倒置，失败 |

每例都保留相同完整硬件预算及所有候选；参数是具名人工台架，没有实机校准。测试另将NIC上限降至0.25 GB/s，1024 B共享需求的必要界变为4096 ns，说明可通过单参数干预区分root与NIC瓶颈。

回读使用保存的本地SystemPath与输入中固定的fabric route，不执行producer或重新寻路；核对所有局部工作、端点绑定、网络收费、下界、未知成本与完整来源。原始失败诊断只保留不重跑。当前不涉及远端认证/QP/ordering、真实buffer内容、coherence/publication、队列/网络拥塞执行或总能耗。后续研究按这些证据缺口增加机制，不能把本包下界视为实际吞吐或完成时间。

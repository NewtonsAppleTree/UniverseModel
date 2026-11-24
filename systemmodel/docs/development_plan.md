# systemmodel 开发任务与验收计划

2026-11-24。遵循[项目使命](../../PROJECT_MISSION.md)、[参数清单](../../ARCHITECTURE_PARAMETERS.md)和[工程接口](../../ENGINEERING_FRAMEWORK.md)，研究设备经过主机、地址域和共享I/O路径后如何形成节点能力。先建立可独立验证的静态边界，再按AI问题接入真实服务、调度或成本证据。

| 包 | 研究什么 | 怎样建模与交付 | 如何证明 / 状态 |
| --- | --- | --- | --- |
| S0 边界与契约 | 资源、域、权限和成本属于谁 | 复用ResourceNode/BandwidthConstraint；新增标准库AddressDomainSpec/SystemPortSpec | 已完成：精确整数、不可变来源、唯一归属和重复计费反例 |
| S1 板卡、节点、拓扑 | 同节点设备是否可达、共享哪些资源 | 独立BoardSpec/NodeSpec，显式link/crossing，权限与确定性路径 | 已完成：双卡共享上行、方向不对称、30组独立穷举、成功失败回读；见[指南](foundation_usage.md) |
| S2 内存与NUMA | 放置如何影响容量和可访问性 | 内存对象/副本/视图、backing容量、半开生命周期、NUMA位置及请求路径 | 已完成：手算、200组独立字节/阶段oracle、15例完整记录/回读；见[指南](memory_usage.md) |
| S3 PCIe与DMA | 直传、中转、共享路径付出什么代价 | conventional posted-write profile、启动/突发、完整copy链、staging预留与共享工作账本 | 已完成：160组分包参考、手算/守恒/敏感性、14例保存回读；见[指南](transfer_usage.md)，仅条件服务下界 |
| S4 CXL与分层内存 | 扩容/卸载在什么条件下可行 | 显式模式、层级/访问能力、迁移路径，缓存/一致性按实际机制声明 | 已完成：显式模式/平坦decoder、同phase驻留、三状态完整对象迁移；15例/反例/回读，见[指南](tiering_usage.md) |
| S5 NIC与集群边界 | 节点内供数如何限制注入/接收 | 内存到NIC路径、共享资源、显式RDMA条件；向cluster导出唯一端点/容量引用 | 已完成：显式buffer/DMA供数与接收、RDMA注册/权限、唯一NIC导出、local适配，12例见[指南](network_usage.md) |
| S6 AI研究实验 | 节点组织怎样影响已有AI任务 | evaluation组合Linear/训练/Attention，比较驻留、P2P、staging或offload | 已完成：Linear/训练/Attention三类任务、独立参考、同预算策略/明确干预、18例含容量失败，见[指南](ai_usage.md) |
| S7 工程与完整验收 | 各包是否独立、可组合和可复现 | 参数/配置/来源、全部失败、bundle回读、UNITS、STATUS、CI与wheel | 已完成：六组81例、全名单与逐条来源绑定、全仓测试与隔离wheel；见[整体验收报告](acceptance.md)及[STATUS](../../docs/STATUS.md) |

## 首包范围

输入是静态资源清单、端口/域、权限和来源。输出是板卡/节点合法性与显式路径/共享引用。model_id为声明的模型身份，不自动加载模型或证明设备行为；地址宽度不当作容量；协议标签不授予P2P、RDMA或一致性。首包路径允许物理图有环，但指定结果为简单路径；路径查询最少link跳数，不优化时延。

memory与io/pcie、io/dma、io/cxl、io/nic已有独立静态行为；继续按研究需要深化，不为技术型号或目录生成空类。systemmodel只依赖contracts/chipmodel/costmodel，任务与比较由evaluation接入。NIC等现有cluster摘要接入真实节点资源时须替换同范围计量，不能叠加两份容量/服务。

## 基础计划完成后的研究深化

S0–S7的本轮基础范围已接通。S5以显式缓冲/DMA供数和接收连接真实node与cluster端点，NIC预算只由cluster计一次，local消息使用本地链路。S6为三个可替换AI任务给出独立数值验证、实际输入字节/预留/搬运绑定和瓶颈干预；S7通过tools/validate_systemmodel.py统一执行六组81例及回读。具体通过数量、源码与wheel证据以[STATUS](../../docs/STATUS.md)为准。

后续任务按具体研究主张选择：需要排队/重叠/数据可见性时，结合runtime/simulator冻结接纳、源消费、完成与发布协议；需要真实性能/能效结论时接设备测量和成本标定；需要AI任务质量结论时接实际模型/数据集及质量门槛。当前基础计划不要求完整PCIe/CXL/RDMA协议、动态一致性、分块迁移或完整LLM服务仿真。

S3提供posted-write与完整copy条件下界；S4原生CXL保持未知服务时间；S5只覆盖显式buffer模式且不混合一个node的local-only/NIC batch；S6提供合成任务算子/梯度正确性和部分MAC/准备服务界，未推导端到端性能、数据集accuracy或总能耗。系统层拥有硬件服务，软件launch与动态策略仍归runtime，不能重复收费。

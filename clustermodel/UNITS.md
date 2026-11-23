# clustermodel Unit 与参数入口

本目录负责跨节点网络、节点/端点引用与通信资源组。依据[项目使命](../PROJECT_MISSION.md)和[参数清单](../ARCHITECTURE_PARAMETERS.md)第 6、8 节设计；当前没有 Python Unit，以下均为候选能力。实现与证据见 [STATUS](../docs/STATUS.md)，完整边界见[设计](docs/design.md)，次序见[开发计划](docs/development_plan.md)。

## 目录导航

| 子目录 | 职责与计量 |
| --- | --- |
| [fabric](fabric/UNITS.md) | 链路、交换容量、固定路由；拥有跨节点网络资源 |
| [topology](topology/UNITS.md) | 有向端口图、连通与指定割；图本身不产生物理成本 |
| [composition](composition/UNITS.md) | 节点/网络装配、rank/group、逐资源需求与下界 |
| [docs](docs/UNITS.md) | 设计、阶段门槛与验证协议；无物理计量 |

## 公共端点边界（拟放 contracts/hardware）

| 字段或对象 | 角色/单位 | 含义和约束 |
| --- | --- | --- |
| NetworkEndpointSpec | 输入；无单位 | 只读 NIC 边界快照；不拥有 NIC 队列或节点内存状态 |
| node_id / endpoint_id / port_id | 输入；标识 | 所属节点、端点、物理端口唯一身份，引用必须存在 |
| tx_constraint_ids / rx_constraint_ids | 输入；标识 tuple | 引用注入/接收及多端口共享容量；相同 ID 只能有一份定义 |
| BandwidthConstraint.resource_id / owner_id | 输入；标识 | 唯一服务资源和所有者；重复引用不增容量 |
| capacity_Bps / byte_basis | 输入；B/s、枚举 | 正有限服务率；字节基准为 payload 或指定链路帧表示，使用相同基准累计需求 |
| source_ref / coverage | 输入；来源与边界 | 手工假设或 profile 身份、版本、适用条件和摘要覆盖；缺失不伪装成实测 |

以上仅定义本模块需要的最小边界；代码实现后，公共字段在 contracts/hardware 的代码及 UNITS 唯一维护，本页只保留引用。节点模型未实现时可传显式快照；以后由 systemmodel 导出同一边界。

## 系统约束与调用顺序

端点/链路参数 → 图与唯一资源校验 → 放置/组校验 → 固定路由 → 按基准累计服务需求 → 条件下界 → 可选运行记录。各步都可独立调用；analysis 不更新动态状态。

输入参数、派生量、C4 执行状态和结果分开。时间用 s，速率区分 bit/s 与 B/s，容量/流量用 B；cycle 必须带时钟域。最敏感量是消息/路径、NIC 共享、上行与交换容量、包开销；是否产生性能收益取决于它们是否成为瓶颈。

NIC/节点内路径归 systemmodel，collective 算法归 runtime，时间/事件归 simulator，网络局部资源归 fabric。未知物理成本保留 None 和原因。首批只验证结构、流量和分析下界，不覆盖真实传输、AI 数值质量或物理校准；验证依据为独立手算、守恒和边界反例。

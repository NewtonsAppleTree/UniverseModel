# switches：交换端口与共享内部能力

候选实现 `model.py`；未实现，见 [STATUS](../../../docs/STATUS.md)。Switch 拥有端口及交换内部服务资源，外部物理链路由 links 拥有。首批做容量约束分析，不拥有包队列，不自动规约张量。

| 字段/量 | 角色/单位 | 约束与关系 |
| --- | --- | --- |
| switch_id / port_ids | 输入；标识 tuple | 唯一实例及端口；端口归属明确 |
| ingress/egress_constraint_ids | 输入；标识 | 指向端口方向服务约束，与外链路相关但不额外复制其物理传输 |
| fabric_constraint_id / fabric_capacity_Bps | 输入；标识、B/s | 内部共享服务容量C>0；默认每次转发按该路径 payload 计一次 |
| byte_basis / counting_scope | 输入；枚举/范围 | payload 或明确帧表示；说明一次转发计一次还是入口/出口分别计数，禁止直接搬用含双向汇总的厂商数值 |
| forwarding_latency_s | 输入；s | 必要处理延迟≥0；是否包含在路径/外部摘要中显式声明 |
| source_ref / coverage | 输入；来源/条件 | 规格、校准或手工假设；不能把端口速率之和当无条件内部能力 |
| forwarded_service_bytes | 派生；B | Q=所有路径在该内部资源的实际经过服务量之和 |
| resource_time_lower_bound_s | 结果；s | Q/C；不提供队列长度、包丢失或完成时间 |

先验证端口/共享引用，再为路由的每次交换经过生成约束需求。多流汇聚时除出口链路外还需检查内部 C；同一消息在端口和内部约束上的需求不能再计入全网额外链路字节。

关键敏感参数是内部容量与各方向供给的比例、incast 目的端口和共享分组。未来有限 buffer、credit、仲裁策略会改变排队，需在 C4 显式状态模型中加入；首次不预建无行为字段。

验收：单次/双次转发计数、多入口共享内部瓶颈、独立全双工口径、无效端口，以及已包含交换内部成本的摘要替换。依据为[模型设计](../../docs/design.md)、M06 守恒与[开发夹具](../../docs/development_plan.md)，尚无交换芯片实测校准。

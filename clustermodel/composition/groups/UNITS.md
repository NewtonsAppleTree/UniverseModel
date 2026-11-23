# groups：rank 放置与通信组

候选实现 `model.py`；未实现，见 [STATUS](../../../docs/STATUS.md)。本目录维护逻辑映射，引用实际端点；不拥有设备、NIC、网络状态或 collective 执行。

| 字段/量 | 角色/单位 | 含义与约束 |
| --- | --- | --- |
| rank_id | 输入；标识 | 实验内唯一 rank；不假定与 node_id 一一对应 |
| node_id / endpoint_id | 输入；标识 | 映射到已有节点与端点，两者归属一致 |
| device_ref | 可选输入；标识 | 跨节点通信首版可不含设备细节；给出时必须能解析来源和范围 |
| group_id / member_rank_ids | 输入；标识、有序 tuple | group 非空且组内唯一；不同 group 可重叠；顺序保留 |
| group_kind | 可选输入；说明标签 | DP/TP/PP/EP/CP 等不触发隐式算法或字节量 |
| participant_endpoints | 派生；引用 | 根据成员解析，允许多个 rank 共享同一 NIC/节点 |

`validate_groups(placements, groups, endpoints)`：校验 rank/端点 → 校验 group → 返回只读映射。共享端点必须保持相同容量约束 ID；不能按成员创建物理副本。一次消息若声明 group，src/dst 均须在组内；group 标签本身不引入额外传输。

参数主要影响放置和共享路径，无独立物理量。通信算法、sequence/dtype/reduction 一致性及 collective 缺参与者诊断由 runtime 处理；首批只检查静态引用，不把“组合法”当作“规约已完成”。

验证空组、重复/缺失 rank、端点归属冲突、组间重叠、共享 NIC 和有序成员；p=1 组合法，是否有工作由显式消息/算法决定。依据[模块边界](../../docs/design.md)与[开发计划](../../docs/development_plan.md)。

# composition：集群与逻辑资源组

当前未实现，状态见 [STATUS](../../docs/STATUS.md)。组合层引用节点、端点和网络实例，保持资源唯一所有权；不复制设备/NIC，不产生额外物理能力。

| 子目录 | 候选行为 | 关键关系 |
| --- | --- | --- |
| [groups](groups/UNITS.md) | rank 放置与通信组校验 | 逻辑成员 → 节点/设备/端点引用；组间允许重叠 |
| [cluster](cluster/UNITS.md) | 装配、路径账本和下界 | 引用资源 → 每路径服务量 → 共享需求聚合 |

组合参数为身份、引用和覆盖，无独立物理单位；数量由实际集合推导，不另设可冲突的 node_count×card_count 输入。消息 B、资源 B/s、时间 s 的具体定义由下层维护。

顺序：资源定义/图校验 → placement/group 校验 → 消息与路由 → 需求累计 → 下界。查询不修改状态；动态执行归 fabric/systemmodel 与 simulator，软件通信策略归 runtime。

关键敏感因素是 rank 放置、消息矩阵和共享端点，不能把 group 数作为带宽倍数。验证身份/引用、共享资源、同预算放置对照和摘要替换；依据[开发计划](../docs/development_plan.md)。

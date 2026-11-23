# fabric：跨节点网络资源

拥有跨节点链路与交换转发能力，引用节点 NIC 端口；C1–C2 基础已实现，见 [STATUS](../../docs/STATUS.md)。

| 子目录 | Unit / 行为 | 输入 → 输出 |
| --- | --- | --- |
| [links](links/UNITS.md) | LinkParams、LinkEstimate / estimate_link | 方向/profile、长度 → 服务量与孤立时间 |
| [switches](switches/UNITS.md) | SwitchParams、SwitchConnection | 端口/内部连接 → 转发与共享约束引用 |
| [routing](routing/UNITS.md) | Route / resolve_route、validate_route | 图、端点、显式边或策略 → 固定路径 |

单位 B、B/s、s；父目录无额外物理带宽或成本。顺序：参数 → 图 → 路由 → 消息账本。每次交换 crossing 按 payload 或出口帧计一次内部服务，方向只有显式共享 ID 才合计需求。

小消息对分包/孤立启动敏感，大消息对链路/交换共享率敏感。没有队列、仲裁、窗口、规约或动态公平性状态。验证字节基准、尾包、显式转发、确定性路径和共享需求；依据[设计](../docs/design.md)及[基础验收](../docs/foundation_usage.md)。

路径广度现覆盖最短路径总数与有界候选枚举；动态分流未实现。候选共享的NIC、接入和交换约束继续按原资源身份计量，详见[routing](routing/UNITS.md)。

<!-- model-fields:start -->



<!-- model-fields:end -->

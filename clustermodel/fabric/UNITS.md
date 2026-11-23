# fabric：跨节点网络资源

当前为设计入口，无已实现 Unit；状态见 [STATUS](../../docs/STATUS.md)。fabric 拥有链路和交换内部资源，引用节点的 NIC 端口，不拥有 collective 策略或全局事件队列。

| 子目录 | 候选 Unit / 行为 | 独立输入 → 输出 |
| --- | --- | --- |
| [links](links/UNITS.md) | LinkParams、LinkEstimate / estimate_link | 方向与速率 profile、长度 → 服务量和孤立时间 |
| [switches](switches/UNITS.md) | SwitchParams / 共享容量查询 | 端口、内部资源、经过量 → 带宽约束需求 |
| [routing](routing/UNITS.md) | Route / 路径选择和验证 | 图、源/目标或显式边序列 → 固定路径 |

参数以子目录为维护源：链路 B/s、延迟 s、消息 B、共享容量 B/s；fabric 层只组合引用，没有额外面积/能量/带宽。多个路径引用同一资源 ID 时累计需求，不能增添容量。

调用顺序为资源定义 → 端口图 → 路由 → 服务量；动态流速/仲裁在 C4 按需求加入，局部状态与纯分析分开。关键敏感量是速率基准、共享上行、交换内部容量、分包与路由热点。验证使用单链路、双流共享、双工和 incast；首批无包级拥塞、重传或硬件规约。依据见[模块设计](../docs/design.md)及 M04/M06 [数学方法](../../docs/methods/parameters_and_math.md)。

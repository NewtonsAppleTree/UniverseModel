# routing：固定有向路径

实现 [paths.py](paths.py)：Route、validate_route、resolve_route、get_crossing。路径保存端点、顺序物理 link_ids 与版本化 policy；相邻链路端口决定显式内部 crossing，不额外视作物理链路。

shortest-hop-lex/v1 选择物理 hop 最少路径，等长时按完整 link ID 序列字典序选择，与容量和输入资源顺序无关。explicit/v1 必须提供非空边序列，允许有限路径重复 fabric crossing，账本逐次计费。两种入口互斥，无 ECMP/动态分流。

校验源/目标方向与每个内部连接；NIC 接收端不能中转。缺端点、错向、断路、缺连接均失败。同节点请求 unsupported_local_path，不以外绕替代节点内部服务。reachable_endpoints 查询物理可达性，业务本地范围由 resolve_route 检查。

顺序：合法 NetworkGraph → resolve_route，或手建 Route 后 validate_route → analyze_traffic。Route 无队列/时间状态、能量或面积。敏感量为连接、放置、规范化 link ID；按ID破平局只保证确定性，不优化带宽。

[集群测试](../../../tests/clustermodel/test_cluster.py)覆盖菱形等长路径、乱序一致性、显式环和重复过割、错向/断路/NIC中转与连接删除。依据[设计](../../docs/design.md)，无死锁证明或动态路由执行。

## 最短路径候选

shortest_route_choices(graph,src,dst,max_paths=8)给出最少物理hop、精确total_shortest_paths及至多max_paths条字典序候选。先BFS构造最短路径DAG并累计路径数，再有界枚举；truncated表示仍有未列出的候选。max_paths是正整数，bool不接受。

候选Route使用explicit/v1，上层可明确固定其中之一；所有候选仍需同一共享NIC/链路/交换容量，候选总数不是独立带宽倍数。不可达、本地未覆盖路径和缺端点保持诊断。验证多spine、12条候选只返回1条、与默认最少hop选择一致及停用后的候选变化，见[横向测试](../../../tests/clustermodel/test_breadth.py)。

批量分析使用当前图的内部索引，独立resolve_route/validate_route/shortest_route_choices保持原签名。默认策略仍按完整link ID序列比较，不因索引或复用改变路径。路由复用键包含源、目标、显式边序列和策略；缓存只存在于一次analyze_traffic，静态停用视图或相同ID的新图会重新建立。独立原始图遍历参考覆盖稀疏crossing、有环和单向停用，见[收尾测试](../../../tests/clustermodel/test_closeout.py)。

<!-- model-fields:start -->

### [paths.py](paths.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `Route` | `src_endpoint_id` | `str` | 1（标识/枚举） | Source external NIC boundary. |
| `Route` | `dst_endpoint_id` | `str` | 1（标识/枚举） | Destination external NIC boundary on another node. |
| `Route` | `link_ids` | `tuple[str, ...]` | 1（标识/枚举） | Ordered nonempty physical hops; finite explicit walks may revisit fabric links. |
| `Route` | `policy` | `Literal['explicit/v1', 'shortest-hop-lex/v1']` | —（结构/对象） | Selection provenance; no dynamic balancing. |
| `RouteChoices` | `src_endpoint_id` | `str` | 1（标识/枚举） | Queried external source NIC. |
| `RouteChoices` | `dst_endpoint_id` | `str` | 1（标识/枚举） | Queried external destination on another node. |
| `RouteChoices` | `minimum_hops` | `int` | hop | Fewest directed physical link traversals [hop]. |
| `RouteChoices` | `total_shortest_paths` | `int` | —（结构/对象） | Exact count of shortest link sequences; shared links/resources may overlap. |
| `RouteChoices` | `routes` | `tuple[Route, ...]` | —（结构/对象） | At most max_paths lexicographic candidates, ready for explicit/v1 selection. |
| `RouteChoices` | `truncated` | `bool` | 1（布尔） | True iff valid shortest paths remain beyond the returned prefix. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `Route` | A route records physical hops only; switch crossings are derived and validated between adjacent links. |
| `get_crossing(graph: NetworkGraph, ingress: str, egress: str)` | Find an explicit forwarding relation; a shared owner alone does not permit traffic to cross ports. |
| `validate_route(graph: NetworkGraph, route: Route)` | Check source/destination directions and every intermediate crossing, without requiring shortest paths. |
| `resolve_route(graph: NetworkGraph, src_endpoint_id: str, dst_endpoint_id: str, *, explicit_link_ids: tuple[str, ...] \| None=None, policy: str='shortest-hop-lex/v1')` | Choose the fewest physical links, breaking ties by the entire lexicographic link-ID sequence. |
| `RouteChoices` | Report structural route diversity separately from bandwidth or an actual multipath scheduling policy. |
| `shortest_route_choices(graph: NetworkGraph, src_endpoint_id: str, dst_endpoint_id: str, *, max_paths: int=8)` | Count the shortest-path DAG without enumerating all paths, then materialize only the requested prefix. |

<!-- model-fields:end -->

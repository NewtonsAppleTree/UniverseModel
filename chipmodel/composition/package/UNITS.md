# package：多个 Die、存储与封装路径

Package 复用 [ResourceNode](../UNITS.md) 管理唯一实例，引用 Die、HBM 等存储与 D2D 路径。Board/DIMM/Node 继续由 systemmodel 组合，不因代码复用搬入处理器 Die。

关键量包括封装 footprint [mm²]、总硅面积 [mm²]、堆叠层位置、连接带宽 [B/s]、功率 [W] 和热条件 [K/W]；它们分别来自几何、路径和物理模型，不能用一个 layers 倍率统一计算。

最关心跨 Die 必须传输的字节、共享端点、距离与散热。数组内部层、Die stack depth 与 compute die count 是不同概念。3D 投影面积缩小不表示功耗或总硅面积下降。

先建立资源归属和 D2D 端口，再做路径/工作分析；geometry 的每次 floorplan 校验只对应同一层。当前没有 TSV/键合密度、封装供电或多节点热网络的自动可行性判断。

## CH8可运行局部组合

[assembly.py](assembly.py)提供ChipAssembly/AssemblyJob、analyze_assembly及project_scopes。一个资源清单供多个Tile/job引用，scope可直接为单Die。绑定→Die/domain/clock校验→job DAG与预留检查→独立Tile边界验证→全局搬运/local/MAC汇总→必要时间界→同指标摘要投影，是完整独立调用顺序。

每个共享bank/MAC/DMA/link只保留一份budget与初始credit，真实工作按次数累计。job完整前驱由开始/完成屏障表达；其独立下界只作并行约束，不重复加demands。SRAM服务汇总全部local与DMA事务，MAC服务汇总同engine的执行项，整体界取它们与全局资源/依赖界的最大值。execution_time_s和energy_j为未知。

多个未排序job的同backing预留不得重叠，完整传递依赖允许区间复用；不推断动态释放或数据值正确性。max_jobs/max_accesses是宿主展开上限，非目标队列/容量预算。D2D的payload/protocol/wire量按每有向link累计，双向通道分别计费；NoC混合串行bridge路径仍需明确模型，当前拒绝。

project_scopes保留固定resource-envelope-lower-bound/v1指标和原贡献，完整覆盖且无祖先/后代重叠；容量按唯一backing求和，时间按max汇总。它是同一分析的视图，不能充当可与内部成本相加的provider，不能跨scope把必要界求和当执行时间。关键敏感量是计算位置、共享端口、各域频率、D2D实际线路量与显式依赖；[CH8指南](../../docs/assembly.md)给出手算、来源与研究边界。

<!-- model-fields:start -->

### [assembly.py](assembly.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `ChipAssembly` | `scope_id` | `str` | 1（标识/枚举） | 本次独立分析的根节点，可为Die、Package或局部bench。 |
| `ChipAssembly` | `die_ids` | `tuple[str, ...]` | 1（标识/枚举） | 不互相嵌套的物理Die节点，scope本身也可为Die。 |
| `ChipAssembly` | `resources` | `TransferResources` | —（结构/对象） | 全组合唯一memory/DMA/link与归属图。 |
| `ChipAssembly` | `domains` | `tuple[DomainPlacement, ...]` | —（结构/对象） | 所有memory/route域的显式Die或外部归属。 |
| `ChipAssembly` | `tiles` | `tuple[TileBinding, ...]` | —（结构/对象） | 数字计算与scratch引用；共享backing不复制容量。 |
| `ChipAssembly` | `profile_source` | `str` | 1（标识/枚举） | 组合与连接范围的来源/实验假设。 |
| `AssemblyJob` | `job_id` | `str` | 1（标识/枚举） | 组合内唯一任务身份；内部请求ID在本job内解释。 |
| `AssemblyJob` | `tile_id` | `str` | 1（标识/枚举） | ChipAssembly.tiles中的计算位置。 |
| `AssemblyJob` | `work` | `TileWork` | —（结构/对象） | 独立Tile任务、显式访问/搬运/预留与MAC工作。 |
| `AssemblyJob` | `dependencies` | `tuple[str, ...]` | 1（标识/枚举） | 完整前驱job IDs，不推断流式部分可见性。 |
| `JobService` | `job_id` | `str` | 1（标识/枚举） | 对应job身份。 |
| `JobService` | `tile_id` | `str` | 1（标识/枚举） | 对应Tile位置。 |
| `JobService` | `isolated_lower_bound_s` | `float` | s | 独立analyze_tile的条件界 [s]。 |
| `JobService` | `executed_macs` | `int` | MAC | 本job实际MAC数量 [MAC]。 |
| `JobService` | `logical_macs` | `int \| None` | MAC | 显式格式任务的有效MAC数 [MAC]；旧无签名输入为None。 |
| `BoundaryTraffic` | `link_id` | `str` | 1（标识/枚举） | 唯一跨界串行资源身份。 |
| `BoundaryTraffic` | `source_die` | `str \| None` | 1（标识/枚举） | 出发Die；None为明确外部边界。 |
| `BoundaryTraffic` | `target_die` | `str \| None` | 1（标识/枚举） | 到达Die；None为明确外部边界。 |
| `BoundaryTraffic` | `payload_bytes` | `int` | B | 穿过该方向边界的逻辑byte总和 [B]。 |
| `BoundaryTraffic` | `protocol_bytes` | `int` | B | 所有packet编码前协议开销 [B]。 |
| `BoundaryTraffic` | `wire_bits` | `int` | bit | 逐包编码/并行尾拍后的真实线路量 [bit]。 |
| `BoundaryTraffic` | `packet_count` | `int` | packet | 按实际请求分包的累计packet数 [packet]。 |
| `AssemblyAnalysis` | `assembly` | `ChipAssembly` | —（结构/对象） | 本结果所用的冻结清单，摘要投影不能误套另一配置。 |
| `AssemblyAnalysis` | `jobs` | `tuple[JobService, ...]` | —（结构/对象） | 各job的独立约束，不作为独立硬件预算相加。 |
| `AssemblyAnalysis` | `actions` | `tuple[ActionEstimate, ...]` | —（结构/对象） | 全局唯一命名的操作和显式job开始/完成屏障。 |
| `AssemblyAnalysis` | `budgets` | `tuple[ResourceBudget, ...]` | —（结构/对象） | 每个物理bank、MAC、DMA、link只有一份供给包络。 |
| `AssemblyAnalysis` | `contributions` | `tuple[ResourceContribution, ...]` | —（结构/对象） | 同物理资源累计后的工作与包络界。 |
| `AssemblyAnalysis` | `transfer` | `TransferAnalysis` | —（结构/对象） | 全局搬运一次计量，保留DRAM条件和未知目标写。 |
| `AssemblyAnalysis` | `memory_services` | `tuple[tuple[str, SramService], ...]` | 1（标识/枚举） | 所有local+DMA请求在每个SRAM backing上合并。 |
| `AssemblyAnalysis` | `boundary_traffic` | `tuple[BoundaryTraffic, ...]` | —（结构/对象） | 按有向跨界link保留实际payload/protocol/wire量。 |
| `AssemblyAnalysis` | `memory_capacities` | `tuple[tuple[str, int], ...]` | B | 唯一backing的声明可寻址容量 [B]；不是逐Tile复制容量。 |
| `AssemblyAnalysis` | `clocks` | `tuple[ClockDomain, ...]` | —（结构/对象） | 去重且一致的时钟域；CDC成本仍未建模。 |
| `AssemblyAnalysis` | `bounds` | `TimeBounds` | s | 全局依赖和供给包络界 [s]。 |
| `AssemblyAnalysis` | `service_bounds` | `tuple[tuple[str, float], ...]` | s | 全局memory/MAC隔离服务及搬运界 [s]。 |
| `AssemblyAnalysis` | `lower_bound_s` | `float` | s | max(bounds,service_bounds) [s]，不是可行调度时间。 |
| `AssemblyAnalysis` | `bottlenecks` | `tuple[str, ...]` | 1（标识/枚举） | 达到整体必要时间界的资源/依赖约束。 |
| `AssemblyAnalysis` | `execution_time_s` | `None` | —（结构/对象） | 未实现可见性、排队和可行调度，执行时间未知。 |
| `AssemblyAnalysis` | `energy_j` | `None` | —（结构/对象） | 没有校准动态/静态物理成本，能量未知。 |
| `AssemblyAnalysis` | `unknown_costs` | `tuple[str, ...]` | 1（标识/枚举） | 触及但未量化的外存/CDC/执行/物理成本。 |
| `ScopeReport` | `scope_id` | `str` | 1（标识/枚举） | 选中的祖先或叶子节点身份。 |
| `ScopeReport` | `metric_id` | `str` | 1（标识/枚举） | 固定resource-envelope-lower-bound/v1；不混入能耗或整体执行时间。 |
| `ScopeReport` | `memory_capacity_bytes` | `int` | B | 此scope覆盖的唯一backing声明容量之和 [B]。 |
| `ScopeReport` | `contributions` | `tuple[ResourceContribution, ...]` | —（结构/对象） | 此scope下原始物理资源贡献，单位各自保留。 |
| `ScopeReport` | `resource_lower_bound_s` | `float` | s | max(所含资源包络界) [s]，不能与其他scope直接求和当执行时间。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `ChipAssembly` | 一个局部组合共享一份资源清单；scope可直接是Die，无需构造完整封装系统。 |
| `AssemblyJob` | 一个已映射Tile任务；依赖表示整个前驱任务完成后才开始本任务。 |
| `JobService` | 隔离job的必要时间仅是额外约束，不重复贡献共享资源工作量。 |
| `BoundaryTraffic` | 一个有向物理边界的实际工作；payload与编码线路位不可混加。 |
| `AssemblyAnalysis` | 全局账本与配置绑定；完整时间、能量和同步成本不由静态下界补零。 |
| `analyze_assembly(assembly: ChipAssembly, jobs: tuple[AssemblyJob, ...], *, max_jobs: int=512, max_accesses: int=200000)` | 一份清单汇总全部真实工作；job独立界只作并行约束，shared资源的工作量与初始credit只计一次。 |
| `ScopeReport` | 摘要是同一资源包络指标的投影，保留叶子贡献而不新建硬件成本provider。 |
| `project_scopes(analysis: AssemblyAnalysis, selected_ids: tuple[str, ...])` | 选中节点必须无祖先重叠且完整覆盖实际资源；expanded和summary视图共享原账本与同一指标。 |

<!-- model-fields:end -->

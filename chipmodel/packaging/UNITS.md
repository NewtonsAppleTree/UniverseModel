# packaging：几何与能量平衡的物理约束

本模块保存/分析物理条件，不重复创建或执行计算/存储单元。当前提供 [geometry](geometry/UNITS.md) 的矩形 floorplan 校验和 [thermal](thermal/UNITS.md) 的一阶热 RC。

最关心面积范围、同层重叠、功率来源、热路径及温度适用域。面积从几何 A=W*H 得到；温度从热能量平衡得到，不能由芯片模块数量直接推断。

供电 PDN、IR drop、PVT反馈、制造良率、KGD、bonding/TSV、老化尚未实现；相应关键量是电压/电阻/电流、热/机械条件、条件概率和校准来源。未知能量/面积/可靠性不能填零进入总成本。

使用顺序：关联实例的几何/工作条件 → 校验物理边界 → 输入有来源的功率/特征值 → 查询结果。动态功率反馈到 DVFS 或 ADC 误差需要后续显式耦合，不在纯静态参数公式里造环。

CH9新增[evidence.py](evidence.py)的PhysicalModel/PhysicalWork与analyze_physical，绑定唯一资源、完整结构/PVT、静态计量选择和分层Placement。costmodel只查询专业成本；几何footprint、分层放置面积与特征化面积分别解释。动态ΣnE与背景P*T分开，缺观测窗口/条件点/动作覆盖时总量未知。

[assembly.py](assembly.py)复用CH8实际工作，SRAM共享RW仍分读写动作，DMA cycle、DRAM burst byte和D2D wire bit保留粒度；结构参数哈希不按通用名称猜器件。独立接口→覆盖检查→几何/成本分析→带来源结果，见[CH9指南](../docs/physical_evidence.md)。时长/功率及PVT/动作粒度最敏感；没有自动时长推断或联合物理可行性证明。

<!-- model-fields:start -->

### [assembly.py](assembly.py)

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `assembly_physical_model(analysis: AssemblyAnalysis, operating_point: OperatingPoint, *, boundary: Rectangle, placements: tuple[Placement, ...], geometry_source: CostSource)` | 保留全部物理实例并以完整参数哈希构造结构身份；实际器件profile不能仅凭通用名称替换。 |
| `assembly_physical_work(analysis: AssemblyAnalysis)` | 服务量只提供已声明动作子集；DRAM行命令和无服务模型的存储成本另记未知。 |

### [evidence.py](evidence.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `ResourceStructure` | `resource_id` | `str` | 1（标识/枚举） | 归属图中的实例或显式摘要节点。 |
| `ResourceStructure` | `structure_id` | `str` | 1（标识/枚举） | 结构版本/参数哈希，与成本表精确匹配。 |
| `ResourceStructure` | `operating_point` | `OperatingPoint` | —（结构/对象） | 成本查询工作点，不由热结果自动改写。 |
| `Placement` | `resource_id` | `str` | 1（标识/枚举） | 已选实例/子树的几何边界。 |
| `Placement` | `rectangle` | `Rectangle` | mm | 在scope坐标系中的投影矩形 [mm]。 |
| `Placement` | `layer` | `int` | —（结构/对象） | 离散放置层；只校验同层重叠，不推断层间热/连线。 |
| `PhysicalModel` | `scope_id` | `str` | 1（标识/枚举） | 局部分析根，可独立于完整芯片调用。 |
| `PhysicalModel` | `nodes` | `tuple[ResourceNode, ...]` | —（结构/对象） | 唯一所有权图。 |
| `PhysicalModel` | `physical_ids` | `tuple[str, ...]` | 1（标识/枚举） | 实际物理资源清单，无祖先/后代双计。 |
| `PhysicalModel` | `structures` | `tuple[ResourceStructure, ...]` | —（结构/对象） | 叶子及可选摘要的结构/PVT身份。 |
| `PhysicalModel` | `static_selection` | `tuple[str, ...]` | 1（标识/枚举） | 面积与背景功率计量粒度；动态动作仍引用叶子。 |
| `PhysicalModel` | `boundary` | `Rectangle` | —（结构/对象） | 本次scope投影边界；不加入特征化面积总和。 |
| `PhysicalModel` | `placements` | `tuple[Placement, ...]` | —（结构/对象） | 完整、无重计的几何视图，可不同于成本粒度。 |
| `PhysicalModel` | `geometry_source` | `CostSource` | —（结构/对象） | 几何参数来源/假设及校准缺口。 |
| `CostActivity` | `activity_id` | `str` | 1（标识/枚举） | 账本唯一行ID，多次真实动作可以累计，但不重复提交同一行。 |
| `CostActivity` | `resource_id` | `str` | 1（标识/枚举） | 唯一物理叶子资源。 |
| `CostActivity` | `action` | `str` | 1（标识/枚举） | 动作语义，如read_word、MAC、wire_bit。 |
| `CostActivity` | `work_unit` | `str` | 1（标识/枚举） | 动作计量单位，word/byte/bit/MAC等不可混用。 |
| `CostActivity` | `amount` | `int` | work_unit | 实际动作量 [work_unit]，非负整数。 |
| `ObservationWindow` | `duration_s` | `float` | s | 背景积分时长 [s]；非负，且不是必要时间下界。 |
| `ObservationWindow` | `basis` | `Literal['measured', 'simulated', 'assumed']` | —（结构/对象） | 实测、事件仿真或显式情景假设。 |
| `ObservationWindow` | `source` | `CostSource` | —（结构/对象） | 时长方法、版本、输入边界与限制。 |
| `PhysicalWork` | `activities` | `tuple[CostActivity, ...]` | —（结构/对象） | 实际动作账本，冻结且ID唯一。 |
| `PhysicalWork` | `activity_source` | `str` | 1（标识/枚举） | 账本生产者/输入身份/假设，CH8适配记录原分析哈希。 |
| `PhysicalWork` | `unknown_activity` | `tuple[str, ...]` | 1（标识/枚举） | 未表达的命令/内容/状态成本；非空时动态总量未知。 |
| `PhysicalWork` | `observation` | `ObservationWindow \| None` | —（结构/对象） | None表示背景能量积分时长未知。 |
| `CostLine` | `resource_id` | `str` | 1（标识/枚举） | 被收费实例，area/leakage为所选摘要或叶子。 |
| `CostLine` | `activity_id` | `str \| None` | 1（标识/枚举） | 动态动作行；静态项为None。 |
| `CostLine` | `amount` | `int` | —（结构/对象） | 动作数量，静态实体只计1。 |
| `CostLine` | `estimate` | `CostEstimate` | —（结构/对象） | 每单位成本及来源；不确定性不会自动视为0。 |
| `CostLine` | `subtotal` | `float \| None` | mm²/W/J | amount*value [mm²/W/J]；缺项为None。 |
| `PhysicalAnalysis` | `lines` | `tuple[CostLine, ...]` | —（结构/对象） | 唯一实体静态项与实际动态动作账本。 |
| `PhysicalAnalysis` | `footprint_mm2` | `float` | —（结构/对象） | 外边界投影面积，独立于特征化面积。 |
| `PhysicalAnalysis` | `placed_area_by_layer_mm2` | `tuple[tuple[int, float], ...]` | —（结构/对象） | 同层放置面积之和；不再加到成本表面积。 |
| `PhysicalAnalysis` | `characterized_area_mm2` | `float \| None` | —（结构/对象） | 所选实体成本面积总和；缺一个点即未知。 |
| `PhysicalAnalysis` | `known_area_mm2` | `float` | —（结构/对象） | 已知面积子集，不能标为完整芯片面积。 |
| `PhysicalAnalysis` | `leakage_power_w` | `float \| None` | —（结构/对象） | 所选实体背景功率和，保持固定查询PVT。 |
| `PhysicalAnalysis` | `dynamic_energy_j` | `float \| None` | —（结构/对象） | 已表达动作总能量，缺来源/动作覆盖时未知。 |
| `PhysicalAnalysis` | `known_dynamic_energy_j` | `float` | —（结构/对象） | 已知动态子集，不包含未知项。 |
| `PhysicalAnalysis` | `leakage_energy_j` | `float \| None` | —（结构/对象） | P_background*T_observation，缺时长或功率时未知。 |
| `PhysicalAnalysis` | `modeled_energy_j` | `float \| None` | —（结构/对象） | 动态+背景，两者完整时才给值，仅覆盖声明模型范围。 |
| `PhysicalAnalysis` | `area_fits_placement` | `bool \| None` | —（结构/对象） | 成本面积不超过对应几何边界是必要条件；不等同可布通。 |
| `PhysicalAnalysis` | `unknown_costs` | `tuple[str, ...]` | 1（标识/枚举） | 缺点、动作覆盖及观测窗口未知原因。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `ResourceStructure` | 物理实例关联完整结构身份/PVT；共享资源不按任务或动作复制。 |
| `Placement` | 放置是几何约束视图，不再作为额外硅面积成本相加。 |
| `resource_cover(nodes: tuple[ResourceNode, ...], physical_ids: tuple[str, ...], selected: tuple[str, ...])` | 一个选择必须恰好覆盖全部物理资源且无祖先/后代重叠。 |
| `PhysicalModel` | 同一局部资源图上的成本/几何条件；两种视图分别覆盖，不互相重复收费。 |
| `CostActivity` | 一个明确动作计数；语义和单位必须与J/action来源一致。 |
| `ObservationWindow` | 外部声明的观测窗口，不接受资源/依赖下界或宿主分析耗时作为积分时长。 |
| `PhysicalWork` | 调用输入与模型参数分离；unknown_activity覆盖动作账本尚未表达的成本。 |
| `CostLine` | 每个条件查询都保留原始请求/来源和已知或未知值，便于解释部分成本。 |
| `PhysicalAnalysis` | 结果按成本类别保留已知子集；任何缺项都不能形成完整能量/面积。 |
| `analyze_physical(model: PhysicalModel, work: PhysicalWork, table: CostTable)` | 唯一静态资源收费；dynamic不含背景，E_background只能由显式观测窗口积分。 |

<!-- model-fields:end -->

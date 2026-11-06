# composition：组合关系与可证明的时间界

本模块不新增硬件服务能力。它连接计算、存储、搬运、通信和物理条件，并检查它们是否以一致的身份和单位描述同一条路径。

| 结构 | 责任 | 子层说明 |
| --- | --- | --- |
| ResourceNode/Port/Connection | 唯一实例、无环归属、静态协议/单位检查 | [Tile](tile/UNITS.md)、[Die](die/UNITS.md)、[Package](package/UNITS.md) |
| validate_model_selection | 同一计量口径选择摘要或内部资源，避免重叠计费 | 容器 model_id=None；资源可被多个真实操作使用 |
| ActionEstimate/ResourceDemand | 任务的完成后依赖与实际工作量 | 操作 DAG 与物理拓扑分开 |
| ResourceBudget/TimeBounds | 供给包络与完成时间下界 | 不运行调度器，不输出实际完成时间 |

## 系统公式与关键参数

对资源 r，必须有依据地声明任意长度 T 的统计窗口最多供给 `b_r + rate_r*T` 工作。b 是首批/突发供给 credit，单位与工作量相同。于是 `T≥max(0,(ΣW_r−b_r)/rate_r)`；依赖路径另给 `T≥max_path Σlatency_i`。最终取两类下界最大值。

如果每 P 个 lane 在周期零能发起一批、每 II cycles 再发起一批，发起包络可以用 b=P、rate=P*f/II；不能一律设 b=0 并将短批次 W/r 当作严格下界。传输按连续流体服务且没有初始 credit 时才可用 b=0。输出完成与发起速率还需相应 latency 约束。

最关心依赖、共享资源、实际工作量、单位、统计窗口和供给模型。ResourceDemand 必须有对应 budget 且单位一致。仅已声明的资源进入分析；漏掉存储、同步或热限制只会使这个下界偏乐观，不能将其命名为系统预测时间。

## 使用顺序与边界

定义资源/端口 → validate_graph → 选择当前指标的计量资源并 validate_model_selection → 组装操作与显式资源工作 → estimate_time_bounds。任务前驱表示整体完成后才能启动；分块可见/流式重叠需要拆分操作或后续事件模型。

协议字符串应标明双方约定的编码/shape 版本；当前检查相等，不推导任意 shape 兼容或模拟电气负载。连接可有环，归属与操作依赖不允许有环。Port 完整闭合、共享仲裁、死锁、取消和可见性生命周期仍属后续台架。

<!-- model-fields:start -->

### [bounds.py](bounds.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `ResourceBudget` | `resource_id` | `str` | 1（标识/枚举） | 唯一资源身份，与 demand 引用一致。 |
| `ResourceBudget` | `work_unit` | `str` | 1（标识/枚举） | 资源工作单位，如 MAC、B、conversion。 |
| `ResourceBudget` | `rate_per_s` | `float` | work_unit/s | 可证明的供给速率上界 r [work_unit/s]。 |
| `ResourceBudget` | `initial_credit` | `float` | work_unit | 时间零可用的额外供给上界 b [work_unit]；流体模型可取 0。 |
| `ResourceDemand` | `resource_id` | `str` | 1（标识/枚举） | 承担此工作量的资源身份。 |
| `ResourceDemand` | `work_unit` | `str` | 1（标识/枚举） | 与 budget 一致的工作单位。 |
| `ResourceDemand` | `amount` | `float` | work_unit | 实际工作量 W [work_unit]；包含映射造成的额外工作。 |
| `ActionEstimate` | `action_id` | `str` | 1（标识/枚举） | 当前任务内唯一的操作身份。 |
| `ActionEstimate` | `latency_s` | `float` | s | 满足输入条件后的最小完成延迟 [s]。 |
| `ActionEstimate` | `dependencies` | `tuple[str, ...]` | 1（标识/枚举） | 必须先完成的操作 ID；不表示全部硬件连接。 |
| `ActionEstimate` | `demands` | `tuple[ResourceDemand, ...]` | —（结构/对象） | 此操作声明的资源工作量。 |
| `TimeBounds` | `critical_path_s` | `float` | s | 操作 DAG 上延迟和的最大值 [s]。 |
| `TimeBounds` | `resource_bound_s` | `float` | s | max_r(max(0,(ΣW_r−b_r)/r_r)) [s]。 |
| `TimeBounds` | `lower_bound_s` | `float` | s | max(critical_path_s,resource_bound_s) [s]。 |
| `TimeBounds` | `serial_latency_sum_s` | `float` | s | 所有操作最小延迟之和 [s]；不是已验证的系统上界。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `ResourceBudget` | 资源供给包络 W(T)≤initial_credit+rate*T；首批/流水线突发能力必须显式给出。 |
| `ResourceDemand` | 一次操作实际消耗的资源工作量；不同单位的 demand 禁止直接累加。 |
| `ActionEstimate` | 操作以完成后依赖表示；latency 是该操作的最小延迟，不是峰值倒数。 |
| `TimeBounds` | 只对已声明的任务/资源给出必要时间界；缺失资源仍可能进一步限制系统。 |
| `estimate_time_bounds(actions: tuple[ActionEstimate, ...], budgets: tuple[ResourceBudget, ...])` | 在依赖 DAG 上动态规划；按唯一资源累加工作，再应用各自的供给包络。 |

### [graph.py](graph.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `Port` | `name` | `str` | 1（标识/枚举） | 节点内唯一端口名；无量纲标识。 |
| `Port` | `direction` | `str` | 1（标识/枚举） | input 或 output；双向接口显式拆为两个端口。 |
| `Port` | `protocol` | `str` | 1（标识/枚举） | 协议/数值格式版本标识，不根据单位自动推断。 |
| `Port` | `unit` | `str` | 1（标识/枚举） | Payload 物理量单位，如 V、A、code、B。 |
| `ResourceNode` | `instance_id` | `str` | 1（标识/枚举） | 整张图唯一的物理实例身份。 |
| `ResourceNode` | `parent_id` | `str \| None` | 1（标识/枚举） | 归属父节点；局部台架根节点为 None。 |
| `ResourceNode` | `model_id` | `str \| None` | 1（标识/枚举） | 可选成本/功能模型身份；None 表示纯容器。 |
| `ResourceNode` | `ports` | `tuple[Port, ...]` | —（结构/对象） | 本节点端口定义；空 tuple 表示没有声明端口。 |
| `Connection` | `source_id` | `str` | 1（标识/枚举） | 源实例身份。 |
| `Connection` | `source_port` | `str` | 1（标识/枚举） | 源 output 端口名。 |
| `Connection` | `target_id` | `str` | 1（标识/枚举） | 目标实例身份。 |
| `Connection` | `target_port` | `str` | 1（标识/枚举） | 目标 input 端口名。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `Port` | 一个静态端口的边界契约；协议身份必须包含双方约定的编码/shape 语义。 |
| `ResourceNode` | Tile/Die/Package 与叶子资源共用归属节点；容器 model_id=None，不额外计费。 |
| `Connection` | 一条有向连接只引用现存端口；协议转换器必须作为显式节点出现。 |
| `validate_graph(nodes: tuple[ResourceNode, ...], connections: tuple[Connection, ...])` | 校验唯一身份、无环包含与端口兼容；允许局部多根资源及 ring 等有环连接。 |
| `validate_model_selection(nodes: tuple[ResourceNode, ...], selected_ids: tuple[str, ...])` | 同一指标口径中选择摘要或内部细模型；祖先和后代不可同时成为收费方。 |

<!-- model-fields:end -->

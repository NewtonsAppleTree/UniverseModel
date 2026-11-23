"""资源绑定的几何与条件成本账本；面积、动态动作和背景积分分别计量。"""

from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from chipmodel.common import count, finite_fraction, identifier, real, typed_tuple
from chipmodel.composition.die.topology import ancestry
from chipmodel.composition.graph import ResourceNode
from chipmodel.packaging.geometry.floorplan import Rectangle, validate_floorplan
from costmodel.interfaces.costs import CostEstimate, CostKey, CostSource, OperatingPoint
from costmodel.providers.tabulated.lookup import CostTable, query_cost


# 物理实例关联完整结构身份/PVT；共享资源不按任务或动作复制。
@dataclass(frozen=True, slots=True, kw_only=True)
class ResourceStructure:
    resource_id: str  # 归属图中的实例或显式摘要节点。
    structure_id: str  # 结构版本/参数哈希，与成本表精确匹配。
    operating_point: OperatingPoint  # 成本查询工作点，不由热结果自动改写。

    # 身份和工作点必须显式；可查询节点存在性由PhysicalModel检查。
    def __post_init__(self) -> None:
        identifier("resource_id", self.resource_id)
        identifier("structure_id", self.structure_id)
        if not isinstance(self.operating_point, OperatingPoint):
            raise TypeError("operating_point must be OperatingPoint")


# 放置是几何约束视图，不再作为额外硅面积成本相加。
@dataclass(frozen=True, slots=True, kw_only=True)
class Placement:
    resource_id: str  # 已选实例/子树的几何边界。
    rectangle: Rectangle  # 在scope坐标系中的投影矩形 [mm]。
    layer: int = 0  # 离散放置层；只校验同层重叠，不推断层间热/连线。

    # 冻结几何和层；层不是自动面积缩放或热耦合参数。
    def __post_init__(self) -> None:
        identifier("resource_id", self.resource_id)
        count("layer", self.layer, 0)
        if not isinstance(self.rectangle, Rectangle):
            raise TypeError("rectangle must be Rectangle")


# 一个选择必须恰好覆盖全部物理资源且无祖先/后代重叠。
def resource_cover(nodes: tuple[ResourceNode, ...], physical_ids: tuple[str, ...], selected: tuple[str, ...]) -> dict[str, str]:
    physical_ids = typed_tuple("physical_ids", physical_ids, str)
    selected = typed_tuple("selected", selected, str)
    paths = ancestry(nodes)
    for keys in (physical_ids, selected):
        if not keys or len(set(keys)) != len(keys) or not set(keys) <= paths.keys():
            raise ValueError("resource cover requires unique existing nonempty IDs")
        if any(set(paths[key][1:]) & set(keys) for key in keys):
            raise ValueError("summary and descendant overlap for the same metric")
    cover = {}
    for key in physical_ids:
        owners = [node for node in selected if node in paths[key]]
        if len(owners) != 1:
            raise ValueError("selection must cover all physical resources exactly once")
        cover[key] = owners[0]
    if set(cover.values()) != set(selected):
        raise ValueError("selection includes an empty resource subtree")
    return cover


# 同一局部资源图上的成本/几何条件；两种视图分别覆盖，不互相重复收费。
@dataclass(frozen=True, slots=True, kw_only=True)
class PhysicalModel:
    scope_id: str  # 局部分析根，可独立于完整芯片调用。
    nodes: tuple[ResourceNode, ...]  # 唯一所有权图。
    physical_ids: tuple[str, ...]  # 实际物理资源清单，无祖先/后代双计。
    structures: tuple[ResourceStructure, ...]  # 叶子及可选摘要的结构/PVT身份。
    static_selection: tuple[str, ...]  # 面积与背景功率计量粒度；动态动作仍引用叶子。
    boundary: Rectangle  # 本次scope投影边界；不加入特征化面积总和。
    placements: tuple[Placement, ...]  # 完整、无重计的几何视图，可不同于成本粒度。
    geometry_source: CostSource  # 几何参数来源/假设及校准缺口。

    # 校验所有权和覆盖；同层包含/重叠在分析时检查，以保留无效几何实验记录。
    def __post_init__(self) -> None:
        for name, kind in (("nodes", ResourceNode), ("physical_ids", str), ("structures", ResourceStructure),
                           ("static_selection", str), ("placements", Placement)):
            object.__setattr__(self, name, typed_tuple(name, getattr(self, name), kind))
        paths = ancestry(self.nodes)
        if self.scope_id not in paths or any(self.scope_id not in p for p in paths.values()):
            raise ValueError("physical nodes must belong to the selected scope")
        static_cover = resource_cover(self.nodes, self.physical_ids, self.static_selection)
        resource_cover(self.nodes, self.physical_ids, tuple(p.resource_id for p in self.placements))
        ids = [s.resource_id for s in self.structures]
        if len(set(ids)) != len(ids) or not set(ids) <= paths.keys() or not set((*self.physical_ids, *self.static_selection)) <= set(ids):
            raise ValueError("structures must uniquely describe all physical and selected cost resources")
        conditions = {s.resource_id: s.operating_point for s in self.structures}
        if any(conditions[leaf] != conditions[owner] for leaf, owner in static_cover.items()):
            raise ValueError("single-PVT summary must match every covered physical resource")
        if not isinstance(self.boundary, Rectangle) or not isinstance(self.geometry_source, CostSource):
            raise TypeError("geometry requires a boundary and source")


# 一个明确动作计数；语义和单位必须与J/action来源一致。
@dataclass(frozen=True, slots=True, kw_only=True)
class CostActivity:
    activity_id: str  # 账本唯一行ID，多次真实动作可以累计，但不重复提交同一行。
    resource_id: str  # 唯一物理叶子资源。
    action: str  # 动作语义，如read_word、MAC、wire_bit。
    work_unit: str  # 动作计量单位，word/byte/bit/MAC等不可混用。
    amount: int  # 实际动作量 [work_unit]，非负整数。

    # 非负整数活动与零工作明确；成本未知不改变原始工作量。
    def __post_init__(self) -> None:
        for name in ("activity_id", "resource_id", "action", "work_unit"):
            identifier(name, getattr(self, name))
        count("amount", self.amount, 0)


# 外部声明的观测窗口，不接受资源/依赖下界或宿主分析耗时作为积分时长。
@dataclass(frozen=True, slots=True, kw_only=True)
class ObservationWindow:
    duration_s: float  # 背景积分时长 [s]；非负，且不是必要时间下界。
    basis: Literal["measured", "simulated", "assumed"]  # 实测、事件仿真或显式情景假设。
    source: CostSource  # 时长方法、版本、输入边界与限制。

    # 时间语义必须显式，实测窗口须有measurement来源。
    def __post_init__(self) -> None:
        object.__setattr__(self, "duration_s", real("duration_s", self.duration_s, minimum=0))
        if self.basis not in ("measured", "simulated", "assumed") or not isinstance(self.source, CostSource):
            raise ValueError("observation window cannot use a lower bound or host time")
        if self.basis == "measured" and self.source.kind != "measurement":
            raise ValueError("measured window requires measurement evidence")


# 调用输入与模型参数分离；unknown_activity覆盖动作账本尚未表达的成本。
@dataclass(frozen=True, slots=True, kw_only=True)
class PhysicalWork:
    activities: tuple[CostActivity, ...]  # 实际动作账本，冻结且ID唯一。
    activity_source: str  # 账本生产者/输入身份/假设，CH8适配记录原分析哈希。
    unknown_activity: tuple[str, ...] = ()  # 未表达的命令/内容/状态成本；非空时动态总量未知。
    observation: ObservationWindow | None = None  # None表示背景能量积分时长未知。

    # 不丢弃失败/缺项，通过输入明确账本覆盖和时间来源。
    def __post_init__(self) -> None:
        object.__setattr__(self, "activities", typed_tuple("activities", self.activities, CostActivity))
        object.__setattr__(self, "unknown_activity", typed_tuple("unknown_activity", self.unknown_activity, str))
        identifier("activity_source", self.activity_source)
        for reason in self.unknown_activity:
            identifier("unknown_activity", reason)
        if len({a.activity_id for a in self.activities}) != len(self.activities):
            raise ValueError("duplicate physical activity_id")
        if self.observation is not None and not isinstance(self.observation, ObservationWindow):
            raise TypeError("observation must be ObservationWindow")


# 每个条件查询都保留原始请求/来源和已知或未知值，便于解释部分成本。
@dataclass(frozen=True, slots=True)
class CostLine:
    resource_id: str  # 被收费实例，area/leakage为所选摘要或叶子。
    activity_id: str | None  # 动态动作行；静态项为None。
    amount: int  # 动作数量，静态实体只计1。
    estimate: CostEstimate  # 每单位成本及来源；不确定性不会自动视为0。
    subtotal: float | None  # amount*value [mm²/W/J]；缺项为None。


# 结果按成本类别保留已知子集；任何缺项都不能形成完整能量/面积。
@dataclass(frozen=True, slots=True)
class PhysicalAnalysis:
    lines: tuple[CostLine, ...]  # 唯一实体静态项与实际动态动作账本。
    footprint_mm2: float  # 外边界投影面积，独立于特征化面积。
    placed_area_by_layer_mm2: tuple[tuple[int, float], ...]  # 同层放置面积之和；不再加到成本表面积。
    characterized_area_mm2: float | None  # 所选实体成本面积总和；缺一个点即未知。
    known_area_mm2: float  # 已知面积子集，不能标为完整芯片面积。
    leakage_power_w: float | None  # 所选实体背景功率和，保持固定查询PVT。
    dynamic_energy_j: float | None  # 已表达动作总能量，缺来源/动作覆盖时未知。
    known_dynamic_energy_j: float  # 已知动态子集，不包含未知项。
    leakage_energy_j: float | None  # P_background*T_observation，缺时长或功率时未知。
    modeled_energy_j: float | None  # 动态+背景，两者完整时才给值，仅覆盖声明模型范围。
    area_fits_placement: bool | None  # 成本面积不超过对应几何边界是必要条件；不等同可布通。
    unknown_costs: tuple[str, ...]  # 缺点、动作覆盖及观测窗口未知原因。


# 精确乘加后转binary64，防止中间计数舍入、正能量下溢或溢出。
def _sum(values: list[float]) -> float:
    return finite_fraction("physical sum", sum((Fraction(v) for v in values), Fraction(0)))


# 唯一静态资源收费；dynamic不含背景，E_background只能由显式观测窗口积分。
def analyze_physical(model: PhysicalModel, work: PhysicalWork, table: CostTable) -> PhysicalAnalysis:
    if not isinstance(model, PhysicalModel) or not isinstance(work, PhysicalWork) or not isinstance(table, CostTable):
        raise TypeError("physical analysis requires professional model, work and table")
    for layer in {p.layer for p in model.placements}:
        validate_floorplan(model.boundary, tuple(p.rectangle for p in model.placements if p.layer == layer))
    if work.observation is not None and work.observation.duration_s == 0 and any(a.amount for a in work.activities):
        raise ValueError("nonzero activity cannot occupy a zero observation window")
    structures = {s.resource_id: s for s in model.structures}
    if any(a.resource_id not in model.physical_ids for a in work.activities):
        raise ValueError("dynamic actions must reference physical leaves, not overlapping summaries")
    lines, unknown = [], list(work.unknown_activity)
    requests = [(key, None, 1, metric, "instance", "instance") for key in model.static_selection for metric in ("area", "leakage")]
    requests += [(a.resource_id, a.activity_id, a.amount, "dynamic", a.action, a.work_unit) for a in work.activities]
    for resource, activity, amount, metric, action, unit in requests:
        structure = structures[resource]
        key = CostKey(structure_id=structure.structure_id, operating_point=structure.operating_point,
                      metric=metric, action=action, work_unit=unit)
        estimate = query_cost(table, key)
        subtotal = 0.0 if amount == 0 else None if estimate.value is None else finite_fraction("cost subtotal", Fraction(amount) * Fraction(estimate.value))
        if subtotal is None:
            unknown.append(f"{resource}/{metric}/{action}: {estimate.unknown_reason}")
        lines.append(CostLine(resource, activity, amount, estimate, subtotal))
    totals, known = {}, {}
    for metric in ("area", "leakage", "dynamic"):
        values = [line.subtotal for line in lines if line.estimate.key.metric == metric]
        known[metric] = _sum([value for value in values if value is not None])
        totals[metric] = None if None in values else known[metric]
    if work.unknown_activity:
        totals["dynamic"] = None
    leakage_energy = None
    if work.observation is None:
        unknown.append("No observation duration: service lower bounds and host wall time cannot integrate background power")
    elif totals["leakage"] is not None:
        leakage_energy = finite_fraction("leakage energy", Fraction(totals["leakage"]) * Fraction(work.observation.duration_s))
    energy = None if totals["dynamic"] is None or leakage_energy is None else _sum([totals["dynamic"], leakage_energy])
    # 面积粒度只有可映射到放置子树时才比较，不能把宏摘要摊分成未经验证的叶子面积。
    paths = ancestry(model.nodes)
    allocated = {p.resource_id: [] for p in model.placements}
    fits = True
    for line in lines:
        if line.estimate.key.metric != "area":
            continue
        owner = [p.resource_id for p in model.placements if p.resource_id in paths[line.resource_id]]
        if line.subtotal is None or len(owner) != 1:
            fits = None
        else:
            allocated[owner[0]].append(line.subtotal)
    if any(_sum(allocated[p.resource_id]) > p.rectangle.area_mm2 for p in model.placements):
        fits = False
    layers = tuple((layer, _sum([p.rectangle.area_mm2 for p in model.placements if p.layer == layer]))
                   for layer in sorted({p.layer for p in model.placements}))
    return PhysicalAnalysis(tuple(lines), model.boundary.area_mm2, layers, totals["area"], known["area"], totals["leakage"],
        totals["dynamic"], known["dynamic"], leakage_energy, energy, fits, tuple(sorted(set(unknown))))

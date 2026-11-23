"""单Die或多Die共享清单上的数字Tile组合；只计算静态容量约束和必要服务界。"""

from dataclasses import dataclass, replace
from fractions import Fraction

from chipmodel.common import ClockDomain, count, finite_fraction, identifier, typed_tuple
from chipmodel.composition.bounds import ActionEstimate, ResourceBudget, ResourceDemand, TimeBounds, estimate_time_bounds
from chipmodel.composition.die.topology import DomainPlacement, ancestry, clock_inventory, validate_placement
from chipmodel.composition.graph import validate_model_selection
from chipmodel.composition.tile.binding import TileBinding
from chipmodel.composition.tile.digital import TileWork, analyze_tile
from chipmodel.composition.transfer import (ResourceContribution, TransferAnalysis, TransferResources, analyze_transfers,
                                           dram_budgets, resource_contributions, sram_budgets, sram_demands)
from chipmodel.memory.sram.access import SramAccess, SramService, analyze_sram


# 一个局部组合共享一份资源清单；scope可直接是Die，无需构造完整封装系统。
@dataclass(frozen=True, slots=True, kw_only=True)
class ChipAssembly:
    scope_id: str  # 本次独立分析的根节点，可为Die、Package或局部bench。
    die_ids: tuple[str, ...]  # 不互相嵌套的物理Die节点，scope本身也可为Die。
    resources: TransferResources  # 全组合唯一memory/DMA/link与归属图。
    domains: tuple[DomainPlacement, ...]  # 所有memory/route域的显式Die或外部归属。
    tiles: tuple[TileBinding, ...]  # 数字计算与scratch引用；共享backing不复制容量。
    profile_source: str  # 组合与连接范围的来源/实验假设。

    # 统一校验所有权、拓扑、计算叶子互斥及全局时钟身份。
    def __post_init__(self) -> None:
        identifier("scope_id", self.scope_id)
        identifier("profile_source", self.profile_source)
        object.__setattr__(self, "die_ids", typed_tuple("die_ids", self.die_ids, str))
        object.__setattr__(self, "domains", typed_tuple("domains", self.domains, DomainPlacement))
        object.__setattr__(self, "tiles", typed_tuple("tiles", self.tiles, TileBinding))
        owners = validate_placement(self.resources, self.scope_id, self.die_ids, self.domains)
        paths = ancestry(self.resources.nodes)
        if len({t.tile_id for t in self.tiles}) != len(self.tiles) or len({t.mac_resource_id for t in self.tiles}) != len(self.tiles):
            raise ValueError("assembly requires unique tile and MAC resource identities")
        physical = tuple(r.resource_id for r in (*self.resources.memories, *self.resources.channels, *self.resources.links))
        validate_model_selection(self.resources.nodes, (*physical, *(t.mac_resource_id for t in self.tiles)))
        for tile in self.tiles:
            tile.bind(self.resources)
            if tile.tile_id not in owners or owners[tile.tile_id] is None:
                raise ValueError("tile must belong to a declared die")
            if tile.tile_id not in paths[tile.mac_resource_id][1:]:
                raise ValueError("MAC must be a descendant of its owning tile")
            if owners[tile.scratch_id] != owners[tile.tile_id]:
                raise ValueError("local scratch must belong to the tile die; remote data requires transfers")
        clock_inventory(self.resources, tuple(t.mac.clock for t in self.tiles))


# 一个已映射Tile任务；依赖表示整个前驱任务完成后才开始本任务。
@dataclass(frozen=True, slots=True, kw_only=True)
class AssemblyJob:
    job_id: str  # 组合内唯一任务身份；内部请求ID在本job内解释。
    tile_id: str  # ChipAssembly.tiles中的计算位置。
    work: TileWork  # 独立Tile任务、显式访问/搬运/预留与MAC工作。
    dependencies: tuple[str, ...] = ()  # 完整前驱job IDs，不推断流式部分可见性。

    # 冻结依赖与专业输入；图存在性/环和预留重叠在组合入口检查。
    def __post_init__(self) -> None:
        identifier("job_id", self.job_id)
        identifier("tile_id", self.tile_id)
        if not isinstance(self.work, TileWork):
            raise TypeError("work must be TileWork")
        object.__setattr__(self, "dependencies", typed_tuple("dependencies", self.dependencies, str))
        for key in self.dependencies:
            identifier("job dependency", key)
        if len(set(self.dependencies)) != len(self.dependencies):
            raise ValueError("duplicate job dependency")


# 隔离job的必要时间仅是额外约束，不重复贡献共享资源工作量。
@dataclass(frozen=True, slots=True)
class JobService:
    job_id: str  # 对应job身份。
    tile_id: str  # 对应Tile位置。
    isolated_lower_bound_s: float  # 独立analyze_tile的条件界 [s]。
    executed_macs: int  # 本job实际MAC数量 [MAC]。
    logical_macs: int | None  # 显式格式任务的有效MAC数 [MAC]；旧无签名输入为None。


# 一个有向物理边界的实际工作；payload与编码线路位不可混加。
@dataclass(frozen=True, slots=True)
class BoundaryTraffic:
    link_id: str  # 唯一跨界串行资源身份。
    source_die: str | None  # 出发Die；None为明确外部边界。
    target_die: str | None  # 到达Die；None为明确外部边界。
    payload_bytes: int  # 穿过该方向边界的逻辑byte总和 [B]。
    protocol_bytes: int  # 所有packet编码前协议开销 [B]。
    wire_bits: int  # 逐包编码/并行尾拍后的真实线路量 [bit]。
    packet_count: int  # 按实际请求分包的累计packet数 [packet]。


# 全局账本与配置绑定；完整时间、能量和同步成本不由静态下界补零。
@dataclass(frozen=True, slots=True)
class AssemblyAnalysis:
    assembly: ChipAssembly  # 本结果所用的冻结清单，摘要投影不能误套另一配置。
    jobs: tuple[JobService, ...]  # 各job的独立约束，不作为独立硬件预算相加。
    actions: tuple[ActionEstimate, ...]  # 全局唯一命名的操作和显式job开始/完成屏障。
    budgets: tuple[ResourceBudget, ...]  # 每个物理bank、MAC、DMA、link只有一份供给包络。
    contributions: tuple[ResourceContribution, ...]  # 同物理资源累计后的工作与包络界。
    transfer: TransferAnalysis  # 全局搬运一次计量，保留DRAM条件和未知目标写。
    memory_services: tuple[tuple[str, SramService], ...]  # 所有local+DMA请求在每个SRAM backing上合并。
    boundary_traffic: tuple[BoundaryTraffic, ...]  # 按有向跨界link保留实际payload/protocol/wire量。
    memory_capacities: tuple[tuple[str, int], ...]  # 唯一backing的声明可寻址容量 [B]；不是逐Tile复制容量。
    clocks: tuple[ClockDomain, ...]  # 去重且一致的时钟域；CDC成本仍未建模。
    bounds: TimeBounds  # 全局依赖和供给包络界 [s]。
    service_bounds: tuple[tuple[str, float], ...]  # 全局memory/MAC隔离服务及搬运界 [s]。
    lower_bound_s: float  # max(bounds,service_bounds) [s]，不是可行调度时间。
    bottlenecks: tuple[str, ...]  # 达到整体必要时间界的资源/依赖约束。
    execution_time_s: None  # 未实现可见性、排队和可行调度，执行时间未知。
    energy_j: None  # 没有校准动态/静态物理成本，能量未知。
    unknown_costs: tuple[str, ...]  # 触及但未量化的外存/CDC/执行/物理成本。


# 长度前缀分隔用户ID与内部动作类型，避免job或request内含斜线时发生拼接碰撞。
def _key(job_id: str, kind: str, local_id: str = "") -> str:
    return f"job/{len(job_id)}:{job_id}/{kind}/{len(local_id)}:{local_id}"


# 返回DAG传递前驱；未知依赖和环在任何物理工作展开前拒绝。
def _predecessors(jobs: tuple[AssemblyJob, ...]) -> dict[str, set[str]]:
    index = {j.job_id: j for j in jobs}
    if len(index) != len(jobs):
        raise ValueError("duplicate assembly job_id")
    remaining = {j.job_id: set(j.dependencies) for j in jobs}
    if any(not deps <= index.keys() for deps in remaining.values()):
        raise ValueError("unknown assembly job dependency")
    predecessors = {}
    while remaining:
        ready = sorted(key for key, deps in remaining.items() if deps <= predecessors.keys())
        if not ready:
            raise ValueError("assembly job dependencies contain a cycle")
        for key in ready:
            predecessors[key] = set().union(*(predecessors[d] | {d} for d in remaining.pop(key)))
    return predecessors


# 未显式排序的job可同时活跃，其scratch预留不能重叠；有完整先后关系才允许复用同一区间。
def _validate_live_regions(jobs: tuple[AssemblyJob, ...], predecessors: dict[str, set[str]]) -> None:
    regions = {}
    for job in jobs:
        for reservation in job.work.reservations:
            regions.setdefault(reservation.backing_id, []).append((reservation.offset_bytes,
                reservation.offset_bytes + reservation.buffer.capacity_bytes, job.job_id))
    for items in regions.values():
        active = []
        for start, end, job_id in sorted(items):
            active = [(a, b, j) for a, b, j in active if b > start]
            for _, _, other in active:
                if other == job_id or (other not in predecessors[job_id] and job_id not in predecessors[other]):
                    raise ValueError("potentially concurrent jobs have overlapping scratch reservations")
            active.append((start, end, job_id))


# 一份清单汇总全部真实工作；job独立界只作并行约束，shared资源的工作量与初始credit只计一次。
def analyze_assembly(assembly: ChipAssembly, jobs: tuple[AssemblyJob, ...], *, max_jobs: int = 512,
                     max_accesses: int = 200_000) -> AssemblyAnalysis:
    if not isinstance(assembly, ChipAssembly):
        raise TypeError("assembly must be ChipAssembly")
    jobs = typed_tuple("jobs", jobs, AssemblyJob)
    count("max_jobs", max_jobs)
    count("max_accesses", max_accesses)
    if len(jobs) > max_jobs or sum(len(j.work.local_accesses) + len(j.work.transfers) for j in jobs) > max_accesses:
        raise ValueError("assembly materialization exceeds host limit")
    predecessors = _predecessors(jobs)
    _validate_live_regions(jobs, predecessors)
    tiles = {t.tile_id: t for t in assembly.tiles}
    if any(j.tile_id not in tiles for j in jobs):
        raise ValueError("job references unknown tile")
    resources = assembly.resources
    memories = {m.resource_id: m for m in resources.memories}
    placement = {d.domain_id: d.die_id for d in assembly.domains}
    requests, local_actions, job_services, request_jobs = [], [], [], {}
    memory_accesses = {m.resource_id: [] for m in resources.memories if m.sram is not None}
    mac_work = {t.mac_resource_id: 0 for t in assembly.tiles}
    for job in jobs:
        tile = tiles[job.tile_id]
        result = analyze_tile(tile.bind(resources), job.work)
        job_services.append(JobService(job.job_id, tile.tile_id, result.lower_bound_s, job.work.executed_macs, job.work.logical_macs))
        start, finish = _key(job.job_id, "start"), _key(job.job_id, "finish")
        local_actions.append(ActionEstimate(action_id=start, latency_s=0,
            dependencies=tuple(_key(d, "finish") for d in job.dependencies), demands=()))
        endpoints = []
        for request in job.work.transfers:
            source, target = memories[request.source_id], memories[request.target_id]
            if placement[source.domain_id] != placement[target.domain_id] and not request.path:
                raise ValueError("cross-die or external transfer requires an explicit boundary path")
            key = _key(job.job_id, "transfer", request.request_id)
            requests.append(replace(request, request_id=key,
                                    dependencies=tuple(_key(job.job_id, "transfer", d) for d in request.dependencies)))
            request_jobs[key] = job.job_id
            endpoints.append(key)
        memory = memories[tile.scratch_id]
        local = analyze_sram(memory.sram, memory.clock, job.work.local_accesses)
        memory_accesses[tile.scratch_id].extend(replace(a, request_id=_key(job.job_id, "local", a.request_id)) for a in job.work.local_accesses)
        mac_work[tile.mac_resource_id] += job.work.executed_macs
        for kind, latency, demands in (
            ("local", local.completion_time_s, sram_demands(memory, local)),
            ("mac", tile.mac.estimate(job.work.executed_macs).completion_time_s,
             (ResourceDemand(resource_id=tile.mac_resource_id, work_unit="MAC", amount=job.work.executed_macs),)),
            ("duration", result.lower_bound_s, ())):
            key = _key(job.job_id, kind)
            local_actions.append(ActionEstimate(action_id=key, latency_s=latency, dependencies=(start,), demands=demands))
            endpoints.append(key)
        local_actions.append(ActionEstimate(action_id=finish, latency_s=0, dependencies=tuple(endpoints), demands=()))
    transfer = analyze_transfers(resources, tuple(requests))
    for request in requests:
        for identity, address, direction, role in ((request.source_id, request.source_address_bytes, "read", "source_read"),
                                                 (request.target_id, request.target_address_bytes, "write", "target_write")):
            if identity in memory_accesses:
                memory_accesses[identity].append(SramAccess(request_id=f"{request.request_id}/{role}",
                    address_bytes=address, length_bytes=request.payload_bytes, direction=direction))
    actions = tuple(local_actions) + tuple(replace(a, dependencies=(*a.dependencies, _key(request_jobs[a.action_id], "start")))
                                           for a in transfer.actions)
    budgets = (*transfer.budgets, *(ResourceBudget(resource_id=t.mac_resource_id, work_unit="MAC",
        rate_per_s=finite_fraction("MAC rate", Fraction(t.mac.params.lane_count) * Fraction(t.mac.clock.frequency_hz)
                                   / t.mac.params.initiation_interval_cycles), initial_credit=t.mac.params.lane_count) for t in assembly.tiles))
    services = tuple((m.resource_id, analyze_sram(m.sram, m.clock, tuple(memory_accesses[m.resource_id])))
                     for m in resources.memories if m.sram is not None)
    service_bounds = (tuple((key, s.completion_time_s) for key, s in services)
                      + tuple((t.mac_resource_id, t.mac.estimate(mac_work[t.mac_resource_id]).completion_time_s) for t in assembly.tiles)
                      + (("transfer", transfer.lower_bound_s),))
    bounds = estimate_time_bounds(actions, budgets)
    contributions = resource_contributions(actions, budgets)
    lower = max(bounds.lower_bound_s, max((value for _, value in service_bounds), default=0))
    constraints = (*service_bounds, ("dependency", bounds.critical_path_s), *((c.resource_id, c.lower_bound_s) for c in contributions))
    traffic = []
    for link in resources.links:
        source, target = placement[link.source_domain], placement[link.target_domain]
        if source == target:
            continue
        legs = [leg for leg in transfer.legs if leg.resource_id == link.resource_id and leg.role == "link"]
        traffic.append(BoundaryTraffic(link.resource_id, source, target, sum(l.logical_bytes for l in legs),
                        sum(l.protocol_bytes for l in legs), sum(l.service_amount for l in legs), sum(l.packet_count for l in legs)))
    unknown = set(transfer.unknown_costs)
    if jobs:
        unknown.add("Static necessary bounds only: queues, visibility, arbitration, CDC synchronization and feasible execution schedule are unknown")
        unknown.add("No calibrated compute/memory/interconnect energy, leakage or physical feasibility profile")
    return AssemblyAnalysis(assembly, tuple(job_services), actions, tuple(budgets), contributions, transfer, services,
        tuple(traffic), tuple((m.resource_id, m.capacity_bytes) for m in resources.memories),
        clock_inventory(resources, tuple(t.mac.clock for t in assembly.tiles)), bounds, service_bounds, lower,
        tuple(sorted({key for key, value in constraints if value == lower and value > 0})), None, None, tuple(sorted(unknown)))


# 摘要是同一资源包络指标的投影，保留叶子贡献而不新建硬件成本provider。
@dataclass(frozen=True, slots=True)
class ScopeReport:
    scope_id: str  # 选中的祖先或叶子节点身份。
    metric_id: str  # 固定resource-envelope-lower-bound/v1；不混入能耗或整体执行时间。
    memory_capacity_bytes: int  # 此scope覆盖的唯一backing声明容量之和 [B]。
    contributions: tuple[ResourceContribution, ...]  # 此scope下原始物理资源贡献，单位各自保留。
    resource_lower_bound_s: float  # max(所含资源包络界) [s]，不能与其他scope直接求和当执行时间。


# 选中节点必须无祖先重叠且完整覆盖实际资源；expanded和summary视图共享原账本与同一指标。
def project_scopes(analysis: AssemblyAnalysis, selected_ids: tuple[str, ...]) -> tuple[ScopeReport, ...]:
    if not isinstance(analysis, AssemblyAnalysis):
        raise TypeError("analysis must be AssemblyAnalysis")
    selected_ids = typed_tuple("selected_ids", selected_ids, str)
    paths = ancestry(analysis.assembly.resources.nodes)
    if len(set(selected_ids)) != len(selected_ids) or not set(selected_ids) <= paths.keys():
        raise ValueError("scope selection requires unique existing nodes")
    if any(set(paths[key][1:]) & set(selected_ids) for key in selected_ids):
        raise ValueError("summary and descendant scopes overlap for the same metric")
    physical = {r.resource_id for r in (*analysis.assembly.resources.memories, *analysis.assembly.resources.channels,
                                       *analysis.assembly.resources.links)} | {t.mac_resource_id for t in analysis.assembly.tiles}
    group = {}
    for key in physical:
        owner = [s for s in selected_ids if s in paths[key]]
        if len(owner) != 1:
            raise ValueError("scope selection must cover every physical resource exactly once")
        group[key] = owner[0]
    # 复用生产预算生成确切bank/channel ID到backing的映射，不从用户ID的字符串前缀猜归属。
    service_owners = {c.resource_id: c.resource_id for c in analysis.contributions if c.resource_id in physical}
    for memory in analysis.assembly.resources.memories:
        for budget in (*sram_budgets(memory), *dram_budgets(memory)):
            service_owners[budget.resource_id] = memory.resource_id
    if set(service_owners) != {c.resource_id for c in analysis.contributions}:
        raise ValueError("analysis contains an unbound service resource")
    rows = []
    for scope in selected_ids:
        contributions = tuple(c for c in analysis.contributions if group[service_owners[c.resource_id]] == scope)
        capacity = sum(amount for key, amount in analysis.memory_capacities if group[key] == scope)
        rows.append(ScopeReport(scope, "resource-envelope-lower-bound/v1", capacity, contributions,
                                max((c.lower_bound_s for c in contributions), default=0)))
    return tuple(rows)

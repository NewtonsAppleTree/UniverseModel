"""显式源读/DMA/有向路径/目标写的静态资源账本；没有可见性事件或队列。"""

from dataclasses import dataclass
from fractions import Fraction

from chipmodel.common import ClockDomain, count, finite_fraction, identifier, typed_tuple
from chipmodel.composition.bounds import ActionEstimate, ResourceBudget, ResourceDemand, TimeBounds, estimate_time_bounds
from chipmodel.composition.graph import ResourceNode, validate_graph, validate_model_selection
from chipmodel.control.data_movement import DmaParams, estimate_dma
from chipmodel.interconnect.d2d.link import SerialLinkParams, estimate_link
from chipmodel.interconnect.noc.path import NoCPathParams, estimate_noc
from chipmodel.memory.access import MemoryAccess
from chipmodel.memory.controllers.dram_read import DramReadProfile, DramSpanEstimate, estimate_dram_span
from chipmodel.memory.sram.access import SramAccess, SramService, analyze_sram
from chipmodel.memory.sram.bank import SramParams


# 地址以资源本地 byte offset 表示；domain_id 明确路由端点，不跨资源推断地址别名。
@dataclass(frozen=True, slots=True, kw_only=True)
class MemoryResource:
    resource_id: str  # 唯一物理 backing 身份；owner 由资源图给出。
    domain_id: str  # 唯一地址域及路由端点身份。
    capacity_bytes: int  # 可寻址容量 [B]。
    sram: SramParams | None = None  # SRAM服务；与dram_read互斥，两者均None时仅声明容量。
    clock: ClockDomain | None = None  # SRAM 时钟；容量边界不能附带虚构服务时钟。
    unknown_reason: str | None = None  # 缺少服务 profile 的原因；已建模 SRAM 为 None。
    dram_read: DramReadProfile | None = None  # DRAM读服务及其自有CK/data clock；写服务始终未知。

    # 容量必须与 SRAM backing 一致；缺失模型不可当作零成本。
    def __post_init__(self) -> None:
        identifier("resource_id", self.resource_id)
        identifier("domain_id", self.domain_id)
        count("capacity_bytes", self.capacity_bytes)
        if self.dram_read is not None:
            if not isinstance(self.dram_read, DramReadProfile):
                raise TypeError("dram_read must be DramReadProfile")
            if self.sram is not None or self.clock is not None or self.unknown_reason is not None:
                raise ValueError("DRAM owns its clocks and cannot also select SRAM/capacity-only service")
            if self.capacity_bytes != self.dram_read.organization.capacity_bytes:
                raise ValueError("DRAM capacity/profile mismatch")
        elif self.sram is None:
            identifier("unknown_reason", self.unknown_reason)
            if self.clock is not None:
                raise ValueError("capacity-only memory has no service clock")
        elif not isinstance(self.sram, SramParams) or not isinstance(self.clock, ClockDomain):
            raise TypeError("modeled memory requires SRAM params and clock")
        elif self.capacity_bytes != self.sram.capacity_bytes or self.unknown_reason is not None:
            raise ValueError("SRAM capacity/profile metadata mismatch")


# 串行请求 DMA 通道；本模型控制和数据通路不覆盖源存储、链路与目标存储。
@dataclass(frozen=True, slots=True, kw_only=True)
class DmaResource:
    resource_id: str  # 物理通道身份，重复请求共享同一预算。
    params: DmaParams  # 每请求启动、burst 与通道占用参数。
    clock: ClockDomain  # 通道时钟 f_dma [Hz]。
    direct_memory_ids: tuple[str, ...]  # 显式直接可达的 memory IDs；两端均在此列才可省略路径。

    # 类型和可达名单冻结；实际资源存在性在装配时校验。
    def __post_init__(self) -> None:
        identifier("resource_id", self.resource_id)
        if not isinstance(self.params, DmaParams) or not isinstance(self.clock, ClockDomain):
            raise TypeError("DMA params and clock required")
        object.__setattr__(self, "direct_memory_ids", typed_tuple("direct_memory_ids", self.direct_memory_ids, str))
        if not self.direct_memory_ids or len(set(self.direct_memory_ids)) != len(self.direct_memory_ids):
            raise ValueError("DMA needs unique directly attached memories")
        for memory_id in self.direct_memory_ids:
            identifier("direct_memory_id", memory_id)


# 一条单向资源；反方向或另一条物理通道必须使用不同 ID。
@dataclass(frozen=True, slots=True, kw_only=True)
class PathLink:
    resource_id: str  # 共享链路的唯一物理身份。
    source_domain: str  # 此方向的源端点/中间路由域。
    target_domain: str  # 此方向的目标端点/中间路由域。
    params: NoCPathParams | SerialLinkParams  # 单 hop NoC 或 D2D 编码 profile。
    clock: ClockDomain | None = None  # NoC 必需；串行链路使用 bit rate，无此时钟。

    # 协议类别明确；不把 flit 和 wire bit 的工作单位混用。
    def __post_init__(self) -> None:
        for name in ("resource_id", "source_domain", "target_domain"):
            identifier(name, getattr(self, name))
        if self.source_domain == self.target_domain:
            raise ValueError("path link must connect distinct domains")
        if isinstance(self.params, NoCPathParams):
            if not isinstance(self.clock, ClockDomain):
                raise TypeError("NoC link requires a clock")
        elif not isinstance(self.params, SerialLinkParams) or self.clock is not None:
            raise TypeError("serial link requires SerialLinkParams without clock")


# 一份共同资源清单决定共享、包含和计量粒度，避免重复的摘要模型收费。
@dataclass(frozen=True, slots=True, kw_only=True)
class TransferResources:
    nodes: tuple[ResourceNode, ...]  # 资源归属图；容器 model_id=None。
    memories: tuple[MemoryResource, ...]  # 唯一地址域和 backing 清单。
    channels: tuple[DmaResource, ...]  # 串行 DMA 通道清单。
    links: tuple[PathLink, ...] = ()  # 固定方向链路清单。

    # 实体有唯一 owner；只选择本账本的叶子模型，禁止同时选择祖先摘要。
    def __post_init__(self) -> None:
        for name, kind in (("nodes", ResourceNode), ("memories", MemoryResource),
                           ("channels", DmaResource), ("links", PathLink)):
            object.__setattr__(self, name, typed_tuple(name, getattr(self, name), kind))
        validate_graph(self.nodes, ())
        index = {node.instance_id: node for node in self.nodes}
        identities = tuple(r.resource_id for r in (*self.memories, *self.channels, *self.links))
        validate_model_selection(self.nodes, identities)
        if any(index[key].parent_id is None for key in identities):
            raise ValueError("accounted resource needs an explicit owner")
        if len({m.domain_id for m in self.memories}) != len(self.memories):
            raise ValueError("memory address domains must be unique")
        memory_ids = {m.resource_id for m in self.memories}
        for channel in self.channels:
            if not set(channel.direct_memory_ids) <= memory_ids:
                raise ValueError("DMA references missing directly attached memory")


# 有限拷贝请求，不承诺数据已写回可见；dependencies 仅表示调用者声明的完成先后。
@dataclass(frozen=True, slots=True, kw_only=True)
class TransferRequest:
    request_id: str  # 批内唯一传输身份。
    source_id: str  # 源 backing ID。
    target_id: str  # 目标 backing ID。
    source_address_bytes: int  # 源资源本地地址 [B]。
    target_address_bytes: int  # 目标资源本地地址 [B]。
    payload_bytes: int  # 保守恒的逻辑字节 D [B]。
    channel_id: str  # 承担本请求的 DMA 通道 ID。
    path: tuple[str, ...] = ()  # 有向 link IDs；空路径须符合直接可达声明。
    dependencies: tuple[str, ...] = ()  # 先完成的传输 request IDs；无隐式全局序列化。
    source_row_state: str | None = None  # DRAM源读的显式hit/closed/conflict条件；非DRAM源须为None。

    # 拒绝无身份/负地址/字符串序列；缺失资源与路由连续性在分析入口检查。
    def __post_init__(self) -> None:
        for name in ("request_id", "source_id", "target_id", "channel_id"):
            identifier(name, getattr(self, name))
        for name in ("source_address_bytes", "target_address_bytes", "payload_bytes"):
            count(name, getattr(self, name), 0)
        if self.source_row_state not in (None, "hit", "closed", "conflict"):
            raise ValueError("source_row_state must be hit, closed or conflict")
        for name in ("path", "dependencies"):
            values = typed_tuple(name, getattr(self, name), str)
            for value in values:
                identifier(name, value)
            if len(set(values)) != len(values):
                raise ValueError(f"duplicate {name} member")
            object.__setattr__(self, name, values)


# 每条请求的一个边界贡献；工作量单位取决于资源，逻辑字节不含协议开销。
@dataclass(frozen=True, slots=True)
class TransferLeg:
    request_id: str  # 来源请求身份。
    resource_id: str  # 实际承载资源 ID。
    role: str  # source_read、dma、link 或 target_write。
    logical_bytes: int  # 此边界的有效载荷 [B]。
    service_unit: str  # word、cycle、flit 或 bit。
    service_amount: int | None  # 对应服务工作量；未知 memory 为 None。
    protocol_bytes: int  # 链路编码前头尾开销 [B]；非链路为零。
    packet_count: int  # 链路 packet 数 [packet]；非链路为零。
    isolated_time_s: float | None  # 空闲服务或DRAM条件span下界 [s]；未知为None。
    unknown_reason: str | None  # 服务未知的明确原因。


# 各资源的包络贡献独立报告，保留实际工作与供给边界以解释瓶颈。
@dataclass(frozen=True, slots=True)
class ResourceContribution:
    resource_id: str  # bank 端口、DMA 或有向链路的服务身份。
    work_unit: str  # 与预算一致的服务单位。
    amount: int | float  # ΣW；整数计数保留精度。
    lower_bound_s: float  # max(0,(ΣW-b)/r) [s]。


# 分析输出保留账本、可组合 actions/budgets 和未建模成本；没有目标完成事件。
@dataclass(frozen=True, slots=True)
class TransferAnalysis:
    legs: tuple[TransferLeg, ...]  # 请求→边界明细。
    actions: tuple[ActionEstimate, ...]  # 每请求 latency=max(已知隔离资源时间)，含显式依赖。
    budgets: tuple[ResourceBudget, ...]  # 唯一资源供给包络。
    contributions: tuple[ResourceContribution, ...]  # 每资源累计必要服务贡献。
    sram_services: tuple[tuple[str, SramService], ...]  # 全批源读/目标写在共同 backing 上合并。
    bounds: TimeBounds  # 依赖和资源包络下界；不会串加流水线各 hop 整包时间。
    lower_bound_s: float  # max(bounds,各 backing 全批隔离服务) [s]。
    unknown_costs: tuple[str, ...]  # 已触及但未建模的 memory 成本原因。
    dram_services: tuple[tuple[str, DramSpanEstimate], ...] = ()  # backing ID及各源读的逐行条件估算。


# 对 bank 创建独立 R/W 或共享 RW 的服务包络；初始 P 项允许起点瞬时发起。
def sram_budgets(memory: MemoryResource) -> tuple[ResourceBudget, ...]:
    if memory.sram is None:
        return ()
    p = memory.sram
    ports = (("rw", p.shared_rw_ports_per_bank),) if p.shared_rw_ports_per_bank else (
        ("read", p.read_ports_per_bank), ("write", p.write_ports_per_bank))
    return tuple(ResourceBudget(resource_id=f"{memory.resource_id}/bank/{bank}/{direction}", work_unit="word",
                                rate_per_s=finite_fraction("SRAM rate", Fraction(number) * Fraction(memory.clock.frequency_hz)
                                                           / p.access_ii_cycles), initial_credit=number)
                 for bank in range(p.bank_count) for direction, number in ports if number)


# 把实际 word 事务绑定到唯一 bank 端口；仅引用 backing 的资源，不按 buffer 再计量。
def sram_demands(memory: MemoryResource, service: SramService) -> tuple[ResourceDemand, ...]:
    shared = memory.sram.shared_rw_ports_per_bank
    return tuple(ResourceDemand(resource_id=f"{memory.resource_id}/bank/{bank}/{direction}",
                                work_unit="word", amount=amount)
                 for bank, (r, w) in enumerate(zip(service.bank_reads, service.bank_writes))
                 for direction, amount in ((("rw", r + w),) if shared else (("read", r), ("write", w))) if amount)


# DRAM所有rank共享每channel的一份数据总线预算；byte为完整burst字节，无起点免费传输。
def dram_budgets(memory: MemoryResource) -> tuple[ResourceBudget, ...]:
    if memory.dram_read is None:
        return ()
    return tuple(ResourceBudget(resource_id=f"{memory.resource_id}/channel/{channel}/read_bus", work_unit="byte",
                                rate_per_s=memory.dram_read.channel_bandwidth_bytes_per_s, initial_credit=0)
                 for channel in range(memory.dram_read.organization.channel_count))


# 累计账本后用精确包络函数生成贡献，不把多个共享请求当作独立硬件。
def resource_contributions(actions: tuple[ActionEstimate, ...], budgets: tuple[ResourceBudget, ...]) -> tuple[ResourceContribution, ...]:
    estimate_time_bounds(actions, budgets)
    totals = {budget.resource_id: Fraction(0) for budget in budgets}
    for action in actions:
        for demand in action.demands:
            totals[demand.resource_id] += Fraction(demand.amount)
    return tuple(ResourceContribution(b.resource_id, b.work_unit,
                 int(totals[b.resource_id]) if totals[b.resource_id].denominator == 1 else
                 finite_fraction("resource work", totals[b.resource_id]),
                 finite_fraction("resource contribution", max(Fraction(0),
                                 (Fraction(totals[b.resource_id]) - Fraction(b.initial_credit)) / Fraction(b.rate_per_s))))
                 for b in budgets)


# 展开存储和路径边界；同构 NoC 用 wormhole 公式，单条 D2D 用编码模型。
def analyze_transfers(resources: TransferResources, requests: tuple[TransferRequest, ...]) -> TransferAnalysis:
    if not isinstance(resources, TransferResources):
        raise TypeError("resources must be TransferResources")
    requests = typed_tuple("requests", requests, TransferRequest)
    if len({r.request_id for r in requests}) != len(requests):
        raise ValueError("duplicate transfer request_id")
    memories = {r.resource_id: r for r in resources.memories}
    channels = {r.resource_id: r for r in resources.channels}
    links = {r.resource_id: r for r in resources.links}
    budgets = [b for memory in resources.memories for b in (*sram_budgets(memory), *dram_budgets(memory))]
    budgets.extend(ResourceBudget(resource_id=c.resource_id, work_unit="cycle", rate_per_s=c.clock.frequency_hz,
                                  initial_credit=0) for c in resources.channels)
    for link in resources.links:
        noc = isinstance(link.params, NoCPathParams)
        rate = (Fraction(link.clock.frequency_hz) / link.params.flit_ii_cycles if noc else
                Fraction(link.params.lane_count) * Fraction(link.params.lane_rate_bps))
        budgets.append(ResourceBudget(resource_id=link.resource_id, work_unit="flit" if noc else "bit",
                                      rate_per_s=finite_fraction("link rate", rate), initial_credit=1 if noc else 0))
    # 派生 bank ID 不得与调用者的资源 ID 冲突。
    if len({b.resource_id for b in budgets}) != len(budgets):
        raise ValueError("derived service resource ID collision")
    derived = {b.resource_id for memory in resources.memories for b in (*sram_budgets(memory), *dram_budgets(memory))}
    if derived & {n.instance_id for n in resources.nodes}:
        raise ValueError("memory service ID collides with physical resource identity")
    all_accesses = {key: [] for key in memories}
    legs, actions, unknown, dram_services = [], [], set(), []
    for request in requests:
        if request.source_id not in memories or request.target_id not in memories or request.channel_id not in channels:
            raise ValueError("transfer references missing memory/channel")
        source, target, channel = memories[request.source_id], memories[request.target_id], channels[request.channel_id]
        if source.dram_read is None and request.source_row_state is not None:
            raise ValueError("row_state requires a DRAM source")
        if source.dram_read is not None and request.payload_bytes and request.source_row_state is None:
            raise ValueError("DRAM source read requires explicit source_row_state")
        route = []
        domain = source.domain_id
        for link_id in request.path:
            if link_id not in links or links[link_id].source_domain != domain:
                raise ValueError("missing or discontinuous directed path")
            route.append(links[link_id])
            domain = links[link_id].target_domain
        if route and domain != target.domain_id:
            raise ValueError("path does not reach target address domain")
        if len(route) > 1 and (not isinstance(route[0].params, NoCPathParams) or any(
                link.params != route[0].params or link.clock != route[0].clock for link in route)):
            raise ValueError("multi-hop path requires homogeneous NoC; an explicit bridge model is needed otherwise")
        attached = set(channel.direct_memory_ids)
        if not {source.resource_id, target.resource_id} & attached:
            raise ValueError("DMA has no attached transfer endpoint")
        if not route and not {source.resource_id, target.resource_id} <= attached:
            raise ValueError("transfer needs an explicit path")
        demands, times = [], []
        for memory, address, direction, role in ((source, request.source_address_bytes, "read", "source_read"),
                                                (target, request.target_address_bytes, "write", "target_write")):
            if address + request.payload_bytes > memory.capacity_bytes:
                raise ValueError("transfer outside memory capacity")
            access = SramAccess(request_id=f"{request.request_id}/{role}", address_bytes=address,
                                length_bytes=request.payload_bytes, direction=direction)
            if memory.dram_read is not None and direction == "read":
                service = estimate_dram_span(memory.dram_read, MemoryAccess(request_id=access.request_id,
                                             address_bytes=address, length_bytes=request.payload_bytes, direction="read"),
                                             row_state=request.source_row_state or "hit")
                dram_services.append((memory.resource_id, service))
                demands.extend(ResourceDemand(resource_id=f"{memory.resource_id}/channel/{i}/read_bus", work_unit="byte",
                                              amount=amount) for i, amount in service.channel_transferred_bytes)
                times.append(service.lower_bound_s)
                reason = f"{memory.resource_id}: {service.unknown_reason}" if request.payload_bytes else None
                if reason:
                    unknown.add(reason)
                legs.append(TransferLeg(request.request_id, memory.resource_id, role, request.payload_bytes, "byte",
                                        sum(amount for _, amount in service.channel_transferred_bytes), 0, 0, service.lower_bound_s, reason))
            elif memory.dram_read is not None:
                reason = f"{memory.resource_id}: DRAM write service is unknown; read profile cannot price writes"
                if request.payload_bytes:
                    unknown.add(reason)
                legs.append(TransferLeg(request.request_id, memory.resource_id, role, request.payload_bytes,
                                        "byte", None if request.payload_bytes else 0, 0, 0,
                                        None if request.payload_bytes else 0.0, reason if request.payload_bytes else None))
            elif memory.sram is None:
                reason = f"{memory.resource_id}: {memory.unknown_reason}"
                if request.payload_bytes:
                    unknown.add(reason)
                legs.append(TransferLeg(request.request_id, memory.resource_id, role, request.payload_bytes,
                                        "word", None, 0, 0, None, reason))
            else:
                all_accesses[memory.resource_id].append(access)
                service = analyze_sram(memory.sram, memory.clock, (access,))
                demands.extend(sram_demands(memory, service))
                times.append(service.completion_time_s)
                legs.append(TransferLeg(request.request_id, memory.resource_id, role, request.payload_bytes,
                                        "word", sum(service.bank_reads) + sum(service.bank_writes), 0, 0,
                                        service.completion_time_s, None))
        dma = estimate_dma(channel.params, channel.clock, request.payload_bytes)
        demands.append(ResourceDemand(resource_id=channel.resource_id, work_unit="cycle", amount=dma.completion_cycles))
        times.append(dma.completion_time_s)
        legs.append(TransferLeg(request.request_id, channel.resource_id, "dma", request.payload_bytes,
                                "cycle", dma.completion_cycles, 0, 0, dma.completion_time_s, None))
        for link in route:
            if isinstance(link.params, NoCPathParams):
                result = estimate_noc(link.params, link.clock, payload_bytes=request.payload_bytes, hops=1)
                unit, amount = "flit", result.flit_count
            else:
                result = estimate_link(link.params, request.payload_bytes)
                unit, amount = "bit", result.wire_bits
            times.append(result.completion_time_s)
            demands.append(ResourceDemand(resource_id=link.resource_id, work_unit=unit, amount=amount))
            legs.append(TransferLeg(request.request_id, link.resource_id, "link", request.payload_bytes,
                                    unit, amount, result.protocol_bytes, result.packet_count, result.completion_time_s, None))
        if route and isinstance(route[0].params, NoCPathParams) and all(
                link.params == route[0].params and link.clock == route[0].clock for link in route):
            times.append(estimate_noc(route[0].params, route[0].clock, payload_bytes=request.payload_bytes,
                                      hops=len(route)).completion_time_s)
        actions.append(ActionEstimate(action_id=request.request_id, latency_s=max(times, default=0),
                                      dependencies=request.dependencies, demands=tuple(demands)))
    actions, budgets = tuple(actions), tuple(budgets)
    services = tuple((memory.resource_id, analyze_sram(memory.sram, memory.clock, tuple(all_accesses[memory.resource_id])))
                     for memory in resources.memories if memory.sram is not None)
    bounds = estimate_time_bounds(actions, budgets)
    lower = max(bounds.lower_bound_s, max((s.completion_time_s for _, s in services), default=0))
    return TransferAnalysis(tuple(legs), actions, budgets, resource_contributions(actions, budgets), services,
                            bounds, lower, tuple(sorted(unknown)), tuple(dram_services))

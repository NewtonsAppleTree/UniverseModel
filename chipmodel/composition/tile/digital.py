"""数字 Tile 的有限工作/资源组合；输入已映射，无编译器依赖或事件引擎。"""

from dataclasses import dataclass
from fractions import Fraction

from chipmodel.common import ClockDomain, PipelineParams, count, estimate_pipeline, finite_fraction, identifier, typed_tuple
from chipmodel.composition.bounds import ActionEstimate, ResourceBudget, ResourceDemand, TimeBounds, estimate_time_bounds
from chipmodel.composition.graph import validate_model_selection
from chipmodel.composition.transfer import (ResourceContribution, TransferAnalysis, TransferRequest, TransferResources,
                                           analyze_transfers, resource_contributions, sram_demands)
from chipmodel.compute.npu.mac import MacAnalysis, MacArithmetic, MacArray, MacWork
from chipmodel.memory.buffer import BufferReservation, validate_reservations
from chipmodel.memory.sram.access import SramAccess, SramService, analyze_sram


# MAC 与一个 SRAM scratch 共享已有资源清单；buffer 只是该 backing 的地址预留。
@dataclass(frozen=True, slots=True, kw_only=True)
class DigitalTile:
    resources: TransferResources  # 真实存储、DMA、链路与 owner 清单。
    scratch_id: str  # 本地操作数/累加器 SRAM 的 backing ID。
    mac_resource_id: str  # MAC 模型叶子身份；不可与搬运资源重叠。
    mac: PipelineParams  # P lanes、L/II [lane, cycle]，格式能力由上层声明。
    compute_clock: ClockDomain  # MAC 时钟 f_compute [Hz]。
    mac_arithmetic: MacArithmetic | None = None  # 可选显式MAC能力；None保留历史只声明工作量的边界。
    mac_profile_source: str = "unrecorded"  # 所选操作/格式对应的服务参数来源。

    # 验证 backing 和计量互斥；保留独立 Tile 调用所需的最小装配。
    def __post_init__(self) -> None:
        if not isinstance(self.resources, TransferResources) or not isinstance(self.mac, PipelineParams):
            raise TypeError("digital tile needs transfer resources and MAC params")
        if not isinstance(self.compute_clock, ClockDomain):
            raise TypeError("compute_clock must be ClockDomain")
        identifier("scratch_id", self.scratch_id)
        identifier("mac_resource_id", self.mac_resource_id)
        identifier("mac_profile_source", self.mac_profile_source)
        if self.mac_arithmetic is not None and not isinstance(self.mac_arithmetic, MacArithmetic):
            raise TypeError("mac_arithmetic must be MacArithmetic or None")
        memories = {m.resource_id: m for m in self.resources.memories}
        if self.scratch_id not in memories or memories[self.scratch_id].sram is None:
            raise ValueError("scratch_id must reference modeled SRAM")
        ids = tuple(r.resource_id for r in (*self.resources.memories, *self.resources.channels, *self.resources.links))
        validate_model_selection(self.resources.nodes, (*ids, self.mac_resource_id))
        node = next(n for n in self.resources.nodes if n.instance_id == self.mac_resource_id)
        if node.parent_id is None:
            raise ValueError("MAC needs an explicit owner")


# 本地访问必须由映射显式提供；MAC 数和外部搬运量不能推导复用策略。
@dataclass(frozen=True, slots=True, kw_only=True)
class TileWork:
    work_id: str  # 已映射任务身份。
    executed_macs: int  # 实际执行含映射额外工作的 MAC 数 [MAC]。
    local_accesses: tuple[SramAccess, ...]  # scratch 上的计算读写；不包含 DMA 源读/目标写。
    transfers: tuple[TransferRequest, ...]  # 独立外部搬运请求。
    reservations: tuple[BufferReservation, ...]  # scratch 中同时预留的地址区域。
    mac_arithmetic: MacArithmetic | None = None  # 调用方的操作/格式请求；显式能力不能接受未声明请求。
    logical_macs: int | None = None  # 可选有效逻辑工作 [MAC]；显式格式请求时必须提供。

    # 冻结输入，所有请求的边界与预留覆盖由分析入口统一验证。
    def __post_init__(self) -> None:
        identifier("work_id", self.work_id)
        count("executed_macs", self.executed_macs, 0)
        if self.mac_arithmetic is not None:
            MacWork(arithmetic=self.mac_arithmetic, logical_macs=self.logical_macs, executed_macs=self.executed_macs)
        elif self.logical_macs is not None:
            raise ValueError("logical_macs requires an explicit MAC arithmetic request")
        for name, kind in (("local_accesses", SramAccess), ("transfers", TransferRequest),
                           ("reservations", BufferReservation)):
            object.__setattr__(self, name, typed_tuple(name, getattr(self, name), kind))


# 功能验证属于任务参考；此结果只报告服务下界和容量/工作量，不输出虚构能耗。
@dataclass(frozen=True, slots=True)
class TileAnalysis:
    transfer: TransferAnalysis  # 源读/通道/链路/目标写明细与未知外存成本。
    scratch_service: SramService  # 本地计算与 DMA 合并后的逐 bank 服务。
    contributions: tuple[ResourceContribution, ...]  # 所有 MAC、bank、DMA、link 的累计包络贡献。
    bounds: TimeBounds  # 已声明依赖与包络下界。
    service_bounds: tuple[tuple[str, float], ...]  # MAC/各 bank/搬运的额外必要服务下界 [s]。
    lower_bound_s: float  # max(bounds,service_bounds) [s]；无可行调度承诺。
    bottlenecks: tuple[str, ...]  # 达到最大必要服务界的约束身份。
    energy_j: None  # 未提供物理 profile 的能耗 [J]，明确未知。
    energy_unknown_reason: str  # 未知成本来源说明。
    mac_analysis: MacAnalysis | None  # 可选格式验证/尾批解释；与已计费MAC服务同源，不再次求和。


# 只验证静态预留覆盖；不由地址覆盖推断数据已就绪、别名安全或双缓冲重叠。
def analyze_tile(tile: DigitalTile, work: TileWork) -> TileAnalysis:
    if not isinstance(tile, DigitalTile) or not isinstance(work, TileWork):
        raise TypeError("analyze_tile requires DigitalTile and TileWork")
    capability = None
    if tile.mac_arithmetic is not None or work.mac_arithmetic is not None:
        if tile.mac_arithmetic is None or work.mac_arithmetic is None:
            raise ValueError("explicit MAC capability and work format must both be supplied")
        capability = MacArray(params=tile.mac, clock=tile.compute_clock, arithmetic=tile.mac_arithmetic,
                              profile_source=tile.mac_profile_source).analyze(
            MacWork(arithmetic=work.mac_arithmetic, logical_macs=work.logical_macs, executed_macs=work.executed_macs))
    memory = next(m for m in tile.resources.memories if m.resource_id == tile.scratch_id)
    validate_reservations(memory.resource_id, memory.capacity_bytes, work.reservations)
    accesses = list(work.local_accesses)
    for request in work.transfers:
        for endpoint, address, direction, role in ((request.source_id, request.source_address_bytes, "read", "source_read"),
                                                   (request.target_id, request.target_address_bytes, "write", "target_write")):
            if endpoint == memory.resource_id:
                accesses.append(SramAccess(request_id=f"{request.request_id}/{role}", address_bytes=address,
                                            length_bytes=request.payload_bytes, direction=direction))
    for access in accesses:
        if access.length_bytes and not any(r.offset_bytes <= access.address_bytes and
                access.address_bytes + access.length_bytes <= r.offset_bytes + r.buffer.capacity_bytes
                for r in work.reservations):
            raise ValueError("scratch request outside reserved regions")
    transfer = analyze_transfers(tile.resources, work.transfers)
    scratch = analyze_sram(memory.sram, memory.clock, tuple(accesses))
    local = analyze_sram(memory.sram, memory.clock, work.local_accesses)
    mac = capability.service if capability else estimate_pipeline(tile.mac, tile.compute_clock, work.executed_macs)
    mac_budget = ResourceBudget(resource_id=tile.mac_resource_id, work_unit="MAC",
                               rate_per_s=finite_fraction("MAC rate", Fraction(tile.mac.lane_count)
                                                          * Fraction(tile.compute_clock.frequency_hz)
                                                          / tile.mac.initiation_interval_cycles),
                               initial_credit=tile.mac.lane_count)
    # 名称独立于用户 work_id，并在合并时检查，禁止覆盖同名搬运 action。
    actions = (*transfer.actions,
               ActionEstimate(action_id="tile/local_access", latency_s=local.completion_time_s, dependencies=(),
                              demands=sram_demands(memory, local)),
               ActionEstimate(action_id="tile/mac", latency_s=mac.completion_time_s, dependencies=(),
                              demands=(ResourceDemand(resource_id=tile.mac_resource_id, work_unit="MAC",
                                                      amount=work.executed_macs),)))
    budgets = (*transfer.budgets, mac_budget)
    bounds = estimate_time_bounds(actions, budgets)
    service_bounds = ((tile.mac_resource_id, mac.completion_time_s), ("transfer", transfer.lower_bound_s),
                      *((f"{memory.resource_id}/bank/{bank}", memory.clock.seconds(
                          memory.sram.access_latency_cycles + (groups - 1) * memory.sram.access_ii_cycles) if groups else 0.0)
                        for bank, groups in enumerate(scratch.bank_issue_groups)))
    lower = max(bounds.lower_bound_s, *(time for _, time in service_bounds))
    contributions = resource_contributions(actions, budgets)
    constraints = (*service_bounds, ("dependency", bounds.critical_path_s),
                   *((c.resource_id, c.lower_bound_s) for c in contributions))
    bottlenecks = tuple(sorted({name for name, time in constraints if time == lower and time > 0}))
    return TileAnalysis(transfer, scratch, contributions, bounds, service_bounds,
                        lower, bottlenecks, None, "No calibrated compute, memory, transfer or leakage energy profile supplied", capability)

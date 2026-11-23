"""隔离 DRAM 读的命令路径估算；前提是 PRE/ACT 在起点合法、无刷新和其他请求。"""

from dataclasses import dataclass
from fractions import Fraction

from chipmodel.common import ClockDomain, ceil_div, count, finite_fraction, identifier
from chipmodel.memory.access import MemoryAccess
from chipmodel.memory.dram.organization import DramAddress, DramOrganization, decode_dram_address, validate_row_order


# 同一 DRAM 时钟域下的读路径特征值；由具体器件/profile 提供。
@dataclass(frozen=True, slots=True, kw_only=True)
class DramReadTiming:
    t_rcd_cycles: int  # tRCD：ACT→RD 最小间隔 [cycle]。
    t_cl_cycles: int  # CL：RD→首个数据传输 [cycle]。
    t_rp_cycles: int  # tRP：PRE→下次 ACT [cycle]。
    t_ccd_cycles: int  # 本次适用 bank/group 关系下的 RD→RD 间隔 [cycle]。
    burst_cycles: int  # 一次 burst 占用数据接口的时间 [cycle]。
    burst_bytes: int  # 一次 burst 的 payload 大小 [B]。

    # 所有时序非零；本模型不检查完整 tRAS/tWR/tFAW/刷新合法性。
    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            count(name, getattr(self, name))


# 单个隔离请求的尾数据到达时间，访问字节按 burst 向上取整。
@dataclass(frozen=True, slots=True)
class DramReadEstimate:
    transferred_bytes: int  # ceil(payload_bytes/burst_bytes)*burst_bytes [B]。
    completion_cycles: int  # PRE/ACT/RD 前缀+(bursts−1)*max(tCCD,tBURST)+tBURST [cycle]。
    completion_time_s: float  # completion_cycles/f_dram [s]。


# row_state=hit/closed/conflict 分别需要 RD、ACT+RD、PRE+ACT+RD；请求必须处于同一行。
def estimate_dram_read(p: DramReadTiming, clock: ClockDomain, *, payload_bytes: int,
                       row_state: str) -> DramReadEstimate:
    if not isinstance(p, DramReadTiming) or not isinstance(clock, ClockDomain):
        raise TypeError("DRAM read requires timing and CK clock")
    count("payload_bytes", payload_bytes, 0)
    prefixes = {"hit": p.t_cl_cycles, "closed": p.t_rcd_cycles + p.t_cl_cycles,
                "conflict": p.t_rp_cycles + p.t_rcd_cycles + p.t_cl_cycles}
    if row_state not in prefixes:
        raise ValueError("row_state must be hit, closed or conflict")
    bursts = ceil_div(payload_bytes, p.burst_bytes)
    cycles = (prefixes[row_state] + (bursts - 1) * max(p.t_ccd_cycles, p.burst_cycles)
              + p.burst_cycles) if bursts else 0
    return DramReadEstimate(bursts * p.burst_bytes, cycles, clock.seconds(cycles))


# 组织、CK命令时序、数据时钟和burst是一份绑定profile；技术名不隐含DDR/WCK比例。
@dataclass(frozen=True, slots=True, kw_only=True)
class DramReadProfile:
    organization: DramOrganization  # 独立channel、共享rank和行/列有效数据组织。
    timing: DramReadTiming  # 全部cycle字段以ck为基准，burst_cycles也是CK周期数。
    ck: ClockDomain  # 命令时序时钟CK [Hz]。
    data_clock: ClockDomain  # 数据时钟 [Hz]；可与CK同频或为显式WCK。
    transfers_per_data_clock: int  # 每数据时钟有效传输次数 [transfer/cycle]，例如DDR为2。
    burst_transfers: int  # 每burst有效数据传输次数 [transfer/burst]。
    profile_source: str  # 模式、时序与关系的来源/假设；不是自动器件校准。
    row_order: tuple[str, ...] = ("bank", "row", "rank", "channel")  # 行块地址低→高的混合进制维度。

    # 严格绑定R=fdata*edges，burst B=BL*width/8，tBURST=BL/R且可表示为整数CK周期。
    def __post_init__(self) -> None:
        for name, kind in (("organization", DramOrganization), ("timing", DramReadTiming),
                           ("ck", ClockDomain), ("data_clock", ClockDomain)):
            if not isinstance(getattr(self, name), kind):
                raise TypeError(f"{name} must be {kind.__name__}")
        count("transfers_per_data_clock", self.transfers_per_data_clock)
        count("burst_transfers", self.burst_transfers)
        identifier("profile_source", self.profile_source)
        object.__setattr__(self, "row_order", validate_row_order(self.row_order))
        if self.ck.domain_id == self.data_clock.domain_id and self.ck.frequency_hz != self.data_clock.frequency_hz:
            raise ValueError("one clock domain identity cannot have two frequencies")
        rate = Fraction(self.data_clock.frequency_hz) * self.transfers_per_data_clock
        if self.organization.data_rate_mt_s != finite_fraction("effective MT/s", rate / 1_000_000):
            raise ValueError("DRAM MT/s disagrees with data clock and transfers/cycle")
        if self.timing.burst_bytes != self.burst_transfers * (self.organization.payload_width_bits // 8):
            raise ValueError("DRAM burst payload disagrees with width and burst transfers")
        if self.timing.burst_cycles * rate != self.burst_transfers * Fraction(self.ck.frequency_hz):
            raise ValueError("DRAM burst duration must match an integer number of CK cycles")
        if self.organization.row_bytes % self.timing.burst_bytes:
            raise ValueError("DRAM row must contain complete aligned bursts")

    # 单channel有效数据速率 [B/s]；rank不乘带宽，数据时钟因子只使用一次。
    @property
    def channel_bandwidth_bytes_per_s(self) -> float:
        return finite_fraction("DRAM channel bandwidth", Fraction(self.data_clock.frequency_hz)
                               * self.transfers_per_data_clock * (self.organization.payload_width_bits // 8))


# 单行范围与真实burst覆盖；row_state为调用方给出的隔离起点条件，不由历史猜测。
@dataclass(frozen=True, slots=True)
class DramAccessEstimate:
    request_id: str  # 当前行片段身份。
    address_bytes: int  # 当前片段的原始地址 [B]。
    logical_bytes: int  # 有效请求数据 [B]。
    location: DramAddress | None  # 非空请求的起点坐标；空请求为None。
    row_state: str  # 声明的hit/closed/conflict隔离条件。
    first_burst_address_bytes: int | None  # 对齐后的首burst地址 [B]。
    burst_count: int  # 覆盖偏移与长度所需完整burst数 [burst]。
    transferred_bytes: int  # burst_count*burst_bytes [B]，包括头尾多传数据。
    completion_cycles: int  # 在PRE/ACT已合法且无其他请求的条件下 [CK cycle]。
    completion_time_s: float  # 上述条件服务时间 [s]，非请求队列完成时间。


# 单行入口明确拒绝越行；未对齐请求覆盖floor(start/burst)到ceil(end/burst)的完整burst。
def estimate_dram_access(profile: DramReadProfile, access: MemoryAccess, *, row_state: str) -> DramAccessEstimate:
    if not isinstance(profile, DramReadProfile) or not isinstance(access, MemoryAccess):
        raise TypeError("expected DramReadProfile and MemoryAccess")
    if access.direction != "read":
        raise ValueError("DRAM write service is not supported by the read profile")
    if access.address_bytes + access.length_bytes > profile.organization.capacity_bytes:
        raise ValueError("DRAM access outside capacity")
    offset = access.address_bytes % profile.organization.row_bytes
    if offset + access.length_bytes > profile.organization.row_bytes:
        raise ValueError("DRAM single-row access crosses a row boundary")
    padding = access.address_bytes % profile.timing.burst_bytes
    service = estimate_dram_read(profile.timing, profile.ck,
                                payload_bytes=padding + access.length_bytes if access.length_bytes else 0, row_state=row_state)
    location = decode_dram_address(profile.organization, access.address_bytes, row_order=profile.row_order) if access.length_bytes else None
    return DramAccessEstimate(access.request_id, access.address_bytes, access.length_bytes, location, row_state,
                              access.address_bytes - padding if access.length_bytes else None,
                              service.transferred_bytes // profile.timing.burst_bytes, service.transferred_bytes,
                              service.completion_cycles, service.completion_time_s)


# 跨行请求拆为独立条件片段；只给必要服务界，不假装已实现连续命令调度。
@dataclass(frozen=True, slots=True)
class DramSpanEstimate:
    fragments: tuple[DramAccessEstimate, ...]  # 行片段，byte范围无重叠且覆盖原请求。
    channel_transferred_bytes: tuple[tuple[int, int], ...]  # 每channel完整burst数据量 [B]。
    interface_lower_bound_s: float  # max(channel_bytes/channel_rate) [s]，数据总线必要条件。
    lower_bound_s: float  # max(接口界,所有隔离片段时间) [s]，依赖声明的行状态条件。
    execution_time_s: None  # 连续命令/队列执行时间 [s]，未知。
    unknown_reason: str  # 缺少调度、刷新及完整时序合法性，不隐含免费状态重置。


# row_state显式适用于每个独立行片段；不从前一个片段的模型返回值更新open-row状态。
def estimate_dram_span(profile: DramReadProfile, access: MemoryAccess, *, row_state: str,
                       max_fragments: int = 100_000) -> DramSpanEstimate:
    if not isinstance(profile, DramReadProfile) or not isinstance(access, MemoryAccess):
        raise TypeError("expected DramReadProfile and MemoryAccess")
    count("max_fragments", max_fragments)
    if access.direction != "read" or row_state not in ("hit", "closed", "conflict"):
        raise ValueError("DRAM span requires read direction and explicit row_state")
    if access.address_bytes + access.length_bytes > profile.organization.capacity_bytes:
        raise ValueError("DRAM span outside capacity")
    row_bytes = profile.organization.row_bytes
    fragments = ceil_div(access.address_bytes % row_bytes + access.length_bytes, row_bytes) if access.length_bytes else 0
    if fragments > max_fragments:
        raise ValueError("DRAM fragment materialization exceeds host limit")
    address, remaining, parts, totals = access.address_bytes, access.length_bytes, [], {}
    while remaining:
        length = min(remaining, row_bytes - address % row_bytes)
        piece = estimate_dram_access(profile, MemoryAccess(request_id=f"{access.request_id}/row/{len(parts)}",
                                     address_bytes=address, length_bytes=length, direction="read"), row_state=row_state)
        parts.append(piece)
        totals[piece.location.channel] = totals.get(piece.location.channel, 0) + piece.transferred_bytes
        address, remaining = address + length, remaining - length
    rate = Fraction(profile.data_clock.frequency_hz) * profile.transfers_per_data_clock * (profile.organization.payload_width_bits // 8)
    interface = finite_fraction("DRAM interface lower bound", Fraction(max(totals.values(), default=0)) / rate)
    return DramSpanEstimate(tuple(parts), tuple(sorted(totals.items())), interface,
                            max(interface, max((p.completion_time_s for p in parts), default=0)), None,
                            "Conditional isolated row states only; no controller schedule, refresh, writes or full command legality")

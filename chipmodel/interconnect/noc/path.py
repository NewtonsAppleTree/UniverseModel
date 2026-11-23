"""专用、无争用 wormhole 路径的尾 flit 到达时间；不运行路由或 credit 状态机。"""

from dataclasses import dataclass

from chipmodel.common import ClockDomain, ceil_div, count


# 每 hop 的固定头部时延与稳态 flit 发起间隔；buffer/VC 竞争未计入。
@dataclass(frozen=True, slots=True, kw_only=True)
class NoCPathParams:
    flit_bytes: int  # Flit 宽度 [B/flit]。
    header_bytes: int  # 每个 packet 的协议头 [B/packet]。
    router_latency_cycles: int  # 每 hop 的头 flit 路由器延迟 [cycle]。
    link_latency_cycles: int  # 每 hop 的头 flit 链路延迟 [cycle]。
    flit_ii_cycles: int  # 每 hop 允许的连续 flit 间隔 [cycle/flit]。

    # 头部开销允许为零；hop 时延和服务间隔必须正。
    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            count(name, getattr(self, name), 0 if name == "header_bytes" else 1)


# 给定 H>0、F=ceil((payload+header)/flit_bytes)，尾 flit 在 H*(Lr+Ll)+(F−1)II 完成。
def estimate_noc(p: NoCPathParams, clock: ClockDomain, *, payload_bytes: int,
                 hops: int) -> "NoCEstimate":
    count("payload_bytes", payload_bytes, 0)
    count("hops", hops)
    if payload_bytes == 0:
        return NoCEstimate(0, 0, 0, 0, 0, 0.0)
    flits = ceil_div(payload_bytes + p.header_bytes, p.flit_bytes)
    cycles = hops * (p.router_latency_cycles + p.link_latency_cycles) + (flits - 1) * p.flit_ii_cycles
    return NoCEstimate(1, p.header_bytes, flits, flits * p.flit_bytes, cycles, clock.seconds(cycles))


# 逐路径 packet/flit 计量；每 hop 都占同样 flit 数，时间不重复序列化整包。
@dataclass(frozen=True, slots=True)
class NoCEstimate:
    packet_count: int  # 非空请求恰为一个 packet [packet]。
    protocol_bytes: int  # 本包头部长度 [B]。
    flit_count: int  # ceil((payload+header)/flit_bytes) [flit]。
    service_bytes: int  # flit_count*flit_bytes [B]；含末 flit padding。
    completion_cycles: int  # H*(Lr+Ll)+(F-1)*II [cycle]。
    completion_time_s: float  # completion_cycles/f_noc [s]。


# 保留原独立时间 API，计量与时间由同一公式维护。
def estimate_noc_time(p: NoCPathParams, clock: ClockDomain, *, payload_bytes: int,
                      hops: int) -> float:
    return estimate_noc(p, clock, payload_bytes=payload_bytes, hops=hops).completion_time_s

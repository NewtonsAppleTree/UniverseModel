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
def estimate_noc_time(p: NoCPathParams, clock: ClockDomain, *, payload_bytes: int,
                      hops: int) -> float:
    count("payload_bytes", payload_bytes, 0)
    count("hops", hops)
    if payload_bytes == 0:
        return 0.0
    flits = ceil_div(payload_bytes + p.header_bytes, p.flit_bytes)
    cycles = hops * (p.router_latency_cycles + p.link_latency_cycles) + (flits - 1) * p.flit_ii_cycles
    return clock.seconds(cycles)

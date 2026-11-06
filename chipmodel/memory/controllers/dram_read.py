"""隔离 DRAM 读的命令路径估算；前提是 PRE/ACT 在起点合法、无刷新和其他请求。"""

from dataclasses import dataclass

from chipmodel.common import ClockDomain, ceil_div, count


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
    count("payload_bytes", payload_bytes, 0)
    prefixes = {"hit": p.t_cl_cycles, "closed": p.t_rcd_cycles + p.t_cl_cycles,
                "conflict": p.t_rp_cycles + p.t_rcd_cycles + p.t_cl_cycles}
    if row_state not in prefixes:
        raise ValueError("row_state must be hit, closed or conflict")
    bursts = ceil_div(payload_bytes, p.burst_bytes)
    cycles = (prefixes[row_state] + (bursts - 1) * max(p.t_ccd_cycles, p.burst_cycles)
              + p.burst_cycles) if bursts else 0
    return DramReadEstimate(bursts * p.burst_bytes, cycles, clock.seconds(cycles))

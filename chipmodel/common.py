"""Chipmodel 内部公共量：固定时钟、整数分组与无争用流水线分析。"""

from dataclasses import dataclass
from fractions import Fraction
from math import isfinite


# 校验离散计数 n∈Z 且 n≥minimum；bool 不作为硬件数量。
def count(name: str, value: int, minimum: int = 1) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be a Python int")
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


# 归一有限实数；不接受单位字符串、bool 或隐式数组标量。
def real(name: str, value: float, *, minimum: float | None = None) -> float:
    if type(value) not in (int, float):
        raise TypeError(f"{name} must be a Python int or float")
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name} exceeds binary64 range") from exc
    if not isfinite(result):
        raise ValueError(f"{name} must be finite")
    if minimum is not None and result < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return result


# 校验严格正的物理量；拒绝零频率、零时间常数和浮点下溢到零。
def positive(name: str, value: float) -> float:
    result = real(name, value, minimum=0)
    if result == 0:
        raise ValueError(f"{name} must be positive")
    return result


# 校验显式身份/协议名称；名称不隐含任何厂商能力。
def identifier(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


# 整数向上取整 ceil(n/d)；n≥0、d>0，避免大整数先转 float。
def ceil_div(n: int, d: int) -> int:
    count("n", n, 0)
    count("d", d)
    return (n + d - 1) // d


# 固定时钟域：Tclk=1/f；不同 domain 的 cycle 数不能直接相加。
@dataclass(frozen=True, slots=True, kw_only=True)
class ClockDomain:
    domain_id: str  # Clock-domain identity；无量纲标识。
    frequency_hz: float  # 固定时钟频率 f [Hz]。

    # 验证 f>0 且周期可表示；冻结规范化频率。
    def __post_init__(self) -> None:
        identifier("domain_id", self.domain_id)
        object.__setattr__(self, "frequency_hz", positive("frequency_hz", self.frequency_hz))
        positive("period_s", 1.0 / self.frequency_hz)

    # 时钟周期 Tclk=1/f [s]。
    @property
    def period_s(self) -> float:
        return 1.0 / self.frequency_hz

    # 本域 cycle→second：T=C/f；C=0 表示无工作。
    def seconds(self, cycles: int) -> float:
        count("cycles", cycles, 0)
        try:
            seconds = float(Fraction(cycles) / Fraction(self.frequency_hz))
        except OverflowError as exc:
            raise ValueError("cycles/frequency_hz exceeds binary64 range") from exc
        return positive("time_s", seconds) if cycles else 0.0


# P 条等价 lane 的服务参数；L 与 II 独立，不描述队列或背压。
@dataclass(frozen=True, slots=True, kw_only=True)
class PipelineParams:
    lane_count: int  # 等价并行服务通道 P [lane]。
    latency_cycles: int  # 单项从发起到完成的延迟 L [cycle]。
    initiation_interval_cycles: int  # 每 lane 发起间隔 II [cycle]。

    # 资源数、延迟与 II 均为正整数；不要求 L=II。
    def __post_init__(self) -> None:
        for name in ("lane_count", "latency_cycles", "initiation_interval_cycles"):
            count(name, getattr(self, name))


# 一批独立工作在空闲流水线上的分析结果；没有跨调用状态。
@dataclass(frozen=True, slots=True)
class PipelineEstimate:
    work_items: int  # 本批实际执行工作 W [item]；item 由具体 Unit 定义。
    issue_groups: int  # 发起组数 G=ceil(W/P) [group]。
    completion_cycles: int  # C=L+(G-1)II [cycle]；W=0 时 C=0。
    completion_time_s: float  # 本域完成时间 C/f [s]。
    peak_items_per_s: float  # 稳态发起上限 P*f/II [item/s]，不等于批次平均速率。


# 从 cycle=0 发起 W 项：最后一组在 (G−1)II 发起，再经过 L 完成。
def estimate_pipeline(p: PipelineParams, clock: ClockDomain, work_items: int) -> PipelineEstimate:
    count("work_items", work_items, 0)
    groups = ceil_div(work_items, p.lane_count)
    cycles = p.latency_cycles + (groups - 1) * p.initiation_interval_cycles if groups else 0
    try:
        peak = positive("peak_items_per_s", float(p.lane_count * Fraction(clock.frequency_hz)
                        / p.initiation_interval_cycles))
    except OverflowError as exc:
        raise ValueError("peak_items_per_s exceeds binary64 range") from exc
    return PipelineEstimate(work_items, groups, cycles, clock.seconds(cycles), peak)

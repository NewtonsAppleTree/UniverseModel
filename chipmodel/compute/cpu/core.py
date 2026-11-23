"""CPU 各阶段能力的上界；不执行 ISA，也不模拟乱序或缓存。"""

from dataclasses import dataclass
from fractions import Fraction

from chipmodel.common import ClockDomain, ceil_div, count, finite_fraction, identifier


# 描述独立、同类 μop 的供给/发射/执行/提交能力，最窄阶段限制稳态吞吐。
@dataclass(frozen=True, slots=True, kw_only=True)
class CpuCoreParams:
    fetch_uops_per_cycle: int  # 已按指令展开比例归一的取指供给 [μop/cycle]。
    decode_uops_per_cycle: int  # 解码带宽 [μop/cycle]。
    issue_uops_per_cycle: int  # 最大总发射宽度 [μop/cycle]。
    retire_uops_per_cycle: int  # 提交宽度 [μop/cycle]；不等同于 ISA IPC。
    execution_lanes: int  # 可执行所选 μop 类型的等价端口数 [lane]。
    execution_ii_cycles: int  # 每执行 lane 的发起间隔 II [cycle]。

    # 所有能力为正整数；此模型只涵盖调用方选定的一类 μop。
    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            count(name, getattr(self, name))


# CPU 峰值计算只表达 min(stage capacities)，不输出无依据的程序运行时间。
@dataclass(frozen=True, slots=True, kw_only=True)
class CpuCore:
    params: CpuCoreParams  # 冻结的阶段能力参数。
    clock: ClockDomain  # Core 固定时钟域。
    uop_class: str = "unspecified"  # 此组等价端口支持的同类μop语义身份；不是ISA指令名。
    profile_source: str = "unrecorded"  # 阶段能力的假设/特征化来源；未记录不等于已校准。

    # 显式校验能力/时钟，操作类名称不会自动推导额外执行端口。
    def __post_init__(self) -> None:
        if not isinstance(self.params, CpuCoreParams) or not isinstance(self.clock, ClockDomain):
            raise TypeError("CpuCore requires CpuCoreParams and ClockDomain")
        identifier("uop_class", self.uop_class)
        identifier("profile_source", self.profile_source)

    # 各阶段速率的最小值 r=min(fetch,decode,issue,retire,lanes/II) [μop/cycle]。
    @property
    def peak_uops_per_cycle(self) -> float:
        return finite_fraction("CPU peak", min(Fraction(width, ii) for _, width, ii in _stages(self.params)))

    # r*f [μop/s]；依赖、分支、端口混合与供数均可能进一步降低实测速率。
    @property
    def peak_uops_per_s(self) -> float:
        rate = min(Fraction(width, ii) for _, width, ii in _stages(self.params))
        return finite_fraction("CPU peak rate", rate * Fraction(self.clock.frequency_hz))


# 映射方提供一种同类μop的实际工作量；不从宏指令数猜测展开比例。
@dataclass(frozen=True, slots=True, kw_only=True)
class CpuWork:
    uop_class: str  # 必须与所选CPU能力的操作语义身份相同。
    executed_uops: int  # 包括显式额外工作在内的μop数 [uop]，可为0。

    # 非负整数工作与非空操作身份，禁止bool计数。
    def __post_init__(self) -> None:
        identifier("uop_class", self.uop_class)
        count("executed_uops", self.executed_uops, 0)


# 稳态瓶颈与有限工作发起跨度分别报告，未建模的程序时间保持未知。
@dataclass(frozen=True, slots=True)
class CpuCapacity:
    stage_rates_uops_per_cycle: tuple[tuple[str, float], ...]  # 每阶段P/II [uop/cycle]。
    peak_uops_per_cycle: float  # min(各阶段速率) [uop/cycle]。
    peak_uops_per_s: float  # 最窄阶段速率*f [uop/s]。
    bottlenecks: tuple[str, ...]  # 精确有理速率相等的全部最窄阶段，与工作数量无关。
    executed_uops: int  # 本次同类实际工作 [uop]。
    stage_issue_spans_cycles: tuple[tuple[str, int], ...]  # 每阶段(max(ceil(W/P)-1,0))*II [cycle]。
    issue_span_lower_bound_cycles: int  # 各阶段跨度取max，不包含阶段延迟/依赖 [cycle]。
    issue_span_lower_bound_s: float  # 跨度下界/f [s]；不是程序完成时间。
    span_bottlenecks: tuple[str, ...]  # 本批非零跨度达到最大值的阶段，可能与稳态瓶颈不同。
    execution_time_s: None  # 程序执行时间 [s]，缺少指令/依赖/缓存/阶段延迟。
    unknown_reason: str  # 时间证据缺口，不把吞吐上界冒充IPC或执行性能。
    profile_source: str  # 当前能力参数来源。


# 阶段以(P,II)统一表示；前端/提交每cycle提供一次宽度，执行端口间隔独立。
def _stages(p: CpuCoreParams) -> tuple[tuple[str, int, int], ...]:
    return (("fetch", p.fetch_uops_per_cycle, 1), ("decode", p.decode_uops_per_cycle, 1),
            ("issue", p.issue_uops_per_cycle, 1), ("execute", p.execution_lanes, p.execution_ii_cycles),
            ("retire", p.retire_uops_per_cycle, 1))


# 假设每阶段cycle0可使用P个槽；最后一次发起至少在(ceil(W/P)-1)*II，无隐含启动延迟。
def analyze_cpu(core: CpuCore, work: CpuWork) -> CpuCapacity:
    if not isinstance(core, CpuCore) or not isinstance(work, CpuWork):
        raise TypeError("analyze_cpu requires CpuCore and CpuWork")
    if core.uop_class == "unspecified" or core.uop_class != work.uop_class:
        raise ValueError("CPU capability requires an explicitly matching uop_class")
    stages = _stages(core.params)
    rates = tuple((name, Fraction(width, ii)) for name, width, ii in stages)
    peak = min(rate for _, rate in rates)
    spans = tuple((name, max(ceil_div(work.executed_uops, width) - 1, 0) * ii) for name, width, ii in stages)
    span = max(cycles for _, cycles in spans)
    return CpuCapacity(tuple((name, finite_fraction("stage rate", rate)) for name, rate in rates),
                       finite_fraction("CPU peak", peak), finite_fraction("CPU peak/s", peak * Fraction(core.clock.frequency_hz)),
                       tuple(name for name, rate in rates if rate == peak), work.executed_uops, spans, span,
                       core.clock.seconds(span), tuple(name for name, cycles in spans if cycles == span and span > 0),
                       None, "Homogeneous uop capacity only; no stage latency, dependencies, port mix, branches or memory execution",
                       core.profile_source)

"""外部总功率驱动的分段恒功率RC分析；不从性能下界构造功率或时长。"""

from dataclasses import dataclass
from fractions import Fraction

from chipmodel.common import finite_fraction, identifier, positive, real, typed_tuple
from chipmodel.packaging.thermal.rc import ThermalRc
from costmodel.interfaces.costs import CostSource


# 一个时间段内功率恒定；功率须为scope总输入，已包含的漏电不能再次相加。
@dataclass(frozen=True, slots=True, kw_only=True)
class PowerSegment:
    duration_s: float  # 分段时长 [s]，严格为正。
    power_w: float  # 本段外部给定总功率 [W]，非负。
    source: CostSource  # 功率与时间窗口的来源/假设。

    # 功率和时长独立于服务下界，所有分段保留来源。
    def __post_init__(self) -> None:
        object.__setattr__(self, "duration_s", positive("duration_s", self.duration_s))
        object.__setattr__(self, "power_w", real("power_w", self.power_w, minimum=0))
        if not isinstance(self.source, CostSource):
            raise TypeError("power segment requires source")


# 单节点热边界与功率轨迹；模型只代表明确scope，不推断空间热点或Die耦合。
@dataclass(frozen=True, slots=True, kw_only=True)
class ThermalTrace:
    resource_id: str  # 热RC所属的独立节点/物理scope。
    model: ThermalRc  # 固定Rth/Cth/Ta，不动态拟合PVT反馈。
    parameter_source: CostSource  # 热参数边界/方法/校准来源。
    initial_temperature_k: float  # t=0温度 [K]。
    limit_temperature_k: float  # 本情景判定阈值 [K]，不是自动器件认证值。
    segments: tuple[PowerSegment, ...]  # 依次相接的总功率段；允许空轨迹查询初态。

    # 输入冻结且绝对温度为正；功率来源与热参数来源分开。
    def __post_init__(self) -> None:
        identifier("resource_id", self.resource_id)
        if not isinstance(self.model, ThermalRc) or not isinstance(self.parameter_source, CostSource):
            raise TypeError("thermal trace needs RC and parameter source")
        for name in ("initial_temperature_k", "limit_temperature_k"):
            object.__setattr__(self, name, positive(name, getattr(self, name)))
        object.__setattr__(self, "segments", typed_tuple("segments", self.segments, PowerSegment))


# 每段恒功率一阶响应单调，峰值在初态或段末；外部功率积分不标为芯片预测能耗。
@dataclass(frozen=True, slots=True)
class ThermalResult:
    boundary_temperatures_k: tuple[float, ...]  # 初态和每段末温度 [K]。
    elapsed_s: float  # Σduration [s]，显式输入轨迹总时长。
    supplied_energy_j: float  # ΣP_i*T_i [J]，外部给定的能量输入。
    peak_temperature_k: float  # max(初态,各段末) [K]，不是空间热点。
    within_limit: bool  # 本单节点模型的peak≤limit，不证明实际物理可行。


# 顺序应用RC解析解；时间/能量用精确中间量累计，温度递推为binary64。
def analyze_thermal_trace(trace: ThermalTrace) -> ThermalResult:
    if not isinstance(trace, ThermalTrace):
        raise TypeError("trace must be ThermalTrace")
    temperatures = [trace.initial_temperature_k]
    for segment in trace.segments:
        temperatures.append(trace.model.temperature_after(initial_temperature_k=temperatures[-1],
                            power_w=segment.power_w, duration_s=segment.duration_s))
    elapsed = finite_fraction("trace duration", sum((Fraction(s.duration_s) for s in trace.segments), Fraction(0)))
    energy = finite_fraction("trace energy", sum((Fraction(s.duration_s) * Fraction(s.power_w) for s in trace.segments), Fraction(0)))
    return ThermalResult(tuple(temperatures), elapsed, energy, max(temperatures), max(temperatures) <= trace.limit_temperature_k)

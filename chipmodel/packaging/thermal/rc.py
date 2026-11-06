"""恒功率、恒环境的一阶 lumped thermal RC；不是多 Die 热网络。"""

from dataclasses import dataclass
from math import expm1

from chipmodel.common import positive, real


# 能量平衡 Cth*dT/dt=P−(T−Ta)/Rth；温度统一采用 kelvin。
@dataclass(frozen=True, slots=True, kw_only=True)
class ThermalRc:
    resistance_k_per_w: float  # 热阻 Rth [K/W]。
    capacitance_j_per_k: float  # 热容 Cth [J/K]。
    ambient_temperature_k: float  # 环境温度 Ta [K]。

    # Rth、Cth 和绝对温度为正；时间常数必须有限且可表示。
    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            positive(name, getattr(self, name))
        positive("time_constant_s", self.time_constant_s)

    # τ=Rth*Cth [s]；K/W*J/K=J/W=s。
    @property
    def time_constant_s(self) -> float:
        return self.resistance_k_per_w * self.capacitance_j_per_k

    # 恒功率 P≥0 [W] 时，稳态温度 T∞=Ta+P*Rth [K]。
    def steady_temperature(self, power_w: float) -> float:
        power = real("power_w", power_w, minimum=0)
        return positive("steady_temperature_k", self.ambient_temperature_k + power * self.resistance_k_per_w)

    # T(t)=T0+(T∞−T0)*(1−exp(−t/τ))；expm1 避免短时间步长的消减误差。
    def temperature_after(self, *, initial_temperature_k: float, power_w: float,
                          duration_s: float) -> float:
        initial = positive("initial_temperature_k", initial_temperature_k)
        duration = real("duration_s", duration_s, minimum=0)
        steady = self.steady_temperature(power_w)
        return positive("temperature_k", initial + (steady - initial)
                        * -expm1(-duration / self.time_constant_s))

"""端点对齐的理想电压 DAC；数值传递函数与时序服务分离。"""

from dataclasses import dataclass
from fractions import Fraction

from chipmodel.common import count, positive, real


# 数字码 q∈[0,2^N−1] 映射至 Vmin..Vmax，LSB=(Vmax−Vmin)/(2^N−1)。
@dataclass(frozen=True, slots=True, kw_only=True)
class VoltageDac:
    resolution_bits: int  # 无符号 DAC 编码宽度 N [bit]；首版支持 1..53。
    output_min_v: float  # q=0 时的输出电压 Vmin [V]。
    output_max_v: float  # q=2^N−1 时的输出电压 Vmax [V]。

    # 校验编码宽度和电压跨度；DAC 端点步长不同于 ADC 的 bin 宽度。
    def __post_init__(self) -> None:
        count("resolution_bits", self.resolution_bits)
        if self.resolution_bits > 53:
            raise ValueError("resolution_bits must be <=53")
        object.__setattr__(self, "output_min_v", real("output_min_v", self.output_min_v))
        object.__setattr__(self, "output_max_v", real("output_max_v", self.output_max_v))
        if self.output_min_v >= self.output_max_v:
            raise ValueError("output_max_v must exceed output_min_v")
        positive("step_v", float((Fraction(self.output_max_v) - Fraction(self.output_min_v))
                                 / ((1 << self.resolution_bits) - 1)))

    # V=Vmin+q*(Vmax−Vmin)/(2^N−1) [V]；越界码拒绝，不隐式截断。
    def convert(self, code: int) -> float:
        count("code", code, 0)
        maximum = (1 << self.resolution_bits) - 1
        if code > maximum:
            raise ValueError("code exceeds DAC resolution")
        return float(Fraction(self.output_min_v) + code * (
            Fraction(self.output_max_v) - Fraction(self.output_min_v)) / maximum)


# Sample/hold 的静态有效性约束，不维护实际槽所有权或采样事件。
@dataclass(frozen=True, slots=True, kw_only=True)
class SampleHoldLimits:
    slot_count: int  # 同时可保留的标量样本数 [sample]。
    valid_duration_s: float  # 从采样完成起允许的保持时长 [s]。

    # 容量和保持时间必须显式非零；不由 ADC lane 数推导样本容量。
    def __post_init__(self) -> None:
        count("slot_count", self.slot_count)
        positive("valid_duration_s", self.valid_duration_s)

    # 要求样本数≤槽数、使用时样本年龄≤保持期限；等于期限仍有效。
    def validate(self, *, sample_count: int, age_s: float) -> None:
        count("sample_count", sample_count, 0)
        real("age_s", age_s, minimum=0)
        if sample_count > self.slot_count or age_s > self.valid_duration_s:
            raise ValueError("sample count or age exceeds sample/hold limits")

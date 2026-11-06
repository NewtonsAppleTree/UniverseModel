"""Ideal voltage ADC：均匀 offset-binary 量化与固定时钟下的无争用估算。

L/II 由调用方给定；本模型不推断电路速度、ENOB、能量或面积。
仅依赖标准库，支持 Python 3.10+。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from fractions import Fraction
from math import isfinite
from typing import ClassVar


# 校验硬件计数为正整数；bool 不属于合法 lane/bit/cycle 数。
def _positive_int(name: str, value: int) -> None:
    if type(value) is not int:  # bool 属于 int 子类，但不是合法硬件计数。
        raise TypeError(f"{name} must be a Python int")
    if value <= 0:
        raise ValueError(f"{name} must be positive")


# 将显式标量归一为有限 binary64；拒绝单位字符串和非有限输入。
def _finite_real(name: str, value: float) -> float:
    if type(value) not in (int, float):
        raise TypeError(f"{name} must be a Python int or float")
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name} is outside the binary64 range") from exc
    if not isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


# 精确比值→正 float；派生结果溢出或下溢到零时拒绝配置。
def _positive_float(name: str, value: Fraction) -> float:
    """派生量转换为 binary64；拒绝 overflow 与下溢到零。"""
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name} is outside the binary64 range") from exc
    if not isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be representable as a positive finite float")
    return result


# ADC 的设计输入：N、P、L、II 与输入电压区间共同决定量化和服务能力。
@dataclass(frozen=True, slots=True, kw_only=True)
class AdcParams:
    """显式设计输入；修改时用 dataclasses.replace 创建新配置。"""

    resolution_bits: int  # Nominal resolution N [bit]；不等同于 ENOB。
    lane_count: int  # 并行转换通道 P [lane]；不表示 MUX 输入数。
    conversion_cycles: int  # Conversion latency L [cycle]；从发起到码值就绪。
    initiation_interval_cycles: int  # 每 lane 最小发起间隔 II [cycle]；独立于 L。
    input_min_v: float  # 输入下限 Vmin [V]；输出采用 offset-binary 编码。
    input_max_v: float  # 输入上限 Vmax [V]；要求 Vmax > Vmin。

    # 校验位宽/并行数/时序与 Vmax>Vmin，并确认 ΔV 可表示。
    def __post_init__(self) -> None:
        for name in ("resolution_bits", "lane_count", "conversion_cycles",
                     "initiation_interval_cycles"):
            _positive_int(name, getattr(self, name))
        # 首版 binary64 输入接口支持 1..53 bit；这是软件支持域，不是电路极限。
        if self.resolution_bits > 53:
            raise ValueError("resolution_bits must be in [1, 53]")
        for name in ("input_min_v", "input_max_v"):
            object.__setattr__(self, name, _finite_real(name, getattr(self, name)))
        if self.input_max_v <= self.input_min_v:
            raise ValueError("input_max_v must exceed input_min_v")
        span = Fraction(self.input_max_v) - Fraction(self.input_min_v)
        _positive_float("quantization_step_v", span / (1 << self.resolution_bits))


# 只读派生规格：K=2^N、ΔV=(Vmax−Vmin)/K、T=L/f、rate=P*f/II。
@dataclass(frozen=True, slots=True)
class AdcDerived:
    """由 Params 与固定频率推导；由 derive_adc 生成，不作为独立配置输入。"""

    code_count: int  # 码阶数 K = 2**N [code]；合法码值为 0..K-1。
    quantization_step_v: float  # LSB ΔV = (Vmax - Vmin) / K [V/code]。
    conversion_time_s: float  # 单样本服务延迟 L / f [s]；不含排队与采样建立。
    initiation_interval_s: float  # 每 lane 发起间隔 II / f [s]。
    ideal_conversions_per_s: float  # Bank 稳态上限 P * f / II [conversion/s]。
    minimum_inflight_per_lane: int  # 维持 II 所需在途槽下界 ceil(L / II) [slot/lane]。


# 按固定转换时钟推导码阶和时序；在途槽需求下界为 ceil(L/II)。
def derive_adc(p: AdcParams, *, frequency_hz: float) -> AdcDerived:
    """f 为固定转换时钟 [Hz]；cycles 均属此时钟域。

    Tclk = 1/f；latency = L*Tclk；bank rate = P/(II*Tclk)。
    在途槽下界假设同一时刻先完成、后发起；实际容量/背压需事件模型验证。
    """
    if not isinstance(p, AdcParams):
        raise TypeError("p must be AdcParams")
    frequency = _finite_real("frequency_hz", frequency_hz)
    if frequency <= 0:
        raise ValueError("frequency_hz must be positive")
    f = Fraction(frequency)
    count = 1 << p.resolution_bits
    span = Fraction(p.input_max_v) - Fraction(p.input_min_v)
    return AdcDerived(
        code_count=count,
        quantization_step_v=_positive_float("quantization_step_v", span / count),
        conversion_time_s=_positive_float("conversion_time_s", p.conversion_cycles / f),
        initiation_interval_s=_positive_float(
            "initiation_interval_s", p.initiation_interval_cycles / f),
        ideal_conversions_per_s=_positive_float(
            "ideal_conversions_per_s", p.lane_count * f / p.initiation_interval_cycles),
        minimum_inflight_per_lane=(p.conversion_cycles + p.initiation_interval_cycles - 1)
        // p.initiation_interval_cycles,
    )


# 单样本数值结果：输出码与严格越限标志分开，端点命中不算越限。
@dataclass(frozen=True, slots=True)
class AdcSample:
    """一次理想转换的功能结果；未附带事件完成或目标可见语义。"""

    code: int  # Offset-binary 码值 [code]；电压为负也不改用补码。
    clipped_low: bool  # 输入严格小于 Vmin；钳位到 code=0。
    clipped_high: bool  # 输入严格大于 Vmax；钳位到 code=K-1。


# S 个样本按 P lanes 分组：G=ceil(S/P)，末次完成 C=L+(G−1)II。
@dataclass(frozen=True, slots=True)
class AdcBatchEstimate:
    """所有样本在 cycle=0 就绪、bank 空闲且输出立即接收的分析结果。"""

    sample_count: int  # 待转换样本数 S [sample]；一个样本对应一次转换。
    group_count: int  # 发起批次数 G = ceil(S / P) [group]；末批可以不满。
    completion_cycles: int  # 末次码值就绪 C = L + (G-1)*II [cycle]；S=0 时为 0。
    completion_time_s: float  # 批次完成时间 C / f [s]；不是宿主 Python 耗时。


# 理想 ADC 把电压量化与无争用分析放在同一入口，不持有事件或缓冲状态。
@dataclass(frozen=True, slots=True, kw_only=True)
class IdealAdc:
    """无动态状态的功能/分析模型；每次调用独立，不预留真实 lane 或缓冲槽。"""

    model_id: ClassVar[str] = "ideal-voltage-adc/v1"  # 量化与估算语义版本。
    params: AdcParams  # 本实例的冻结配置；不接受单独覆盖派生量。
    frequency_hz: float  # 固定转换时钟 f [Hz]；本版本不支持运行中 DVFS。
    derived: AdcDerived = field(init=False)  # 构造时解析的只读派生量。
    _minimum: Fraction = field(init=False, repr=False)  # Vmin 的精确 binary64 数值 [V]。
    _step: Fraction = field(init=False, repr=False)  # 精确码阶 [V/code]；避免边界运算误入邻码。

    # 从冻结输入重算规格并保存精确量化边界，防止外部单独覆盖派生值。
    def __post_init__(self) -> None:
        frequency = _finite_real("frequency_hz", self.frequency_hz)
        derived = derive_adc(self.params, frequency_hz=frequency)
        minimum = Fraction(self.params.input_min_v)
        object.__setattr__(self, "frequency_hz", frequency)
        object.__setattr__(self, "derived", derived)
        object.__setattr__(self, "_minimum", minimum)
        object.__setattr__(self, "_step", (Fraction(self.params.input_max_v) - minimum)
                           / derived.code_count)

    # q=clamp(floor((V−Vmin)/ΔV),0,K−1)；精确比值避免邻近阈值的浮点误判。
    def convert(self, voltage_v: float) -> AdcSample:
        """输入已采样电压 [V]；q = clamp(floor((V - Vmin)/ΔV), 0, K-1)。

        Bin 左闭右开，Vmax 归入末码且不标记越限；NaN/inf 拒绝。
        Fraction 精确解释传入的 binary64 值，不恢复十进制输入前的精度。
        """
        voltage = _finite_real("voltage_v", voltage_v)
        if voltage <= self.params.input_min_v:
            return AdcSample(0, voltage < self.params.input_min_v, False)
        if voltage >= self.params.input_max_v:
            return AdcSample(self.derived.code_count - 1, False,
                             voltage > self.params.input_max_v)
        code = (Fraction(voltage) - self._minimum) // self._step
        return AdcSample(code, False, False)

    # 对有限电压序列逐样本量化，返回同序不可变结果；不表示硬件同时发起。
    def convert_many(self, voltages_v: Iterable[float]) -> tuple[AdcSample, ...]:
        """按输入顺序返回结果；voltages_v 是有限电压序列 [V]，不表示同时发起。"""
        return tuple(self.convert(value) for value in voltages_v)

    # 估算空闲 bank 上 S 个已就绪样本的尾批完成时间；S=0 时为零。
    def estimate_batch(self, sample_count: int) -> AdcBatchEstimate:
        """独立估算 S 个样本 [sample]；第 g 批在 g*II 发起、g*II+L 完成。

        假设 lane 同步发起、输入持续可用、在途容量充分且无输出背压。
        连续调用不会模拟批次之间的资源争用。
        """
        if type(sample_count) is not int:
            raise TypeError("sample_count must be a Python int")
        if sample_count < 0:
            raise ValueError("sample_count must be nonnegative")
        groups = (sample_count + self.params.lane_count - 1) // self.params.lane_count
        cycles = (self.params.conversion_cycles
                  + (groups - 1) * self.params.initiation_interval_cycles) if groups else 0
        seconds = (_positive_float("completion_time_s", cycles / Fraction(self.frequency_hz))
                   if cycles else 0.0)
        return AdcBatchEstimate(sample_count, groups, cycles, seconds)

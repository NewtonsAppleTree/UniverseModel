"""已编程电导阵列的位串行 MatVec 数值链；编程、时序和物理成本不由数值调用推断。"""

from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from chipmodel.common import count, identifier, positive, real, typed_tuple
from chipmodel.compute.cim.arrays.conductance import ConductanceArray, ConductanceArrayParams, transimpedance
from chipmodel.compute.cim.encoding.accumulate import shift_accumulate
from chipmodel.compute.cim.encoding.bit_serial import BitSerialParams, BitSerialWork, derive_bit_serial
from chipmodel.compute.cim.periphery.adc import AdcParams, AdcSample, IdealAdc
from chipmodel.compute.cim.periphery.dac import VoltageDac
from contracts.versions.json_codec import content_hash


# 一份明确的整数→电导→电压→码值→整数映射；不将 ADC 位数视作任务精度。
@dataclass(frozen=True, slots=True, kw_only=True)
class CimNumericParams:
    encoding: BitSerialParams  # 无符号输入相位、权重幅度切片及差分位置。
    array: ConductanceArrayParams  # 每份切片阵列的实际 R×C 与电气范围。
    conductance_step_s: float  # 权重 digit 每级增加的电导 ΔG [S/digit]。
    dac: VoltageDac  # 必须为 1-bit、Vmin=0；每相位输出 0 或 Vread [V]。
    tia_gain_ohm: float  # 带符号非零跨阻 Rtia [Ω]。
    tia_offset_v: float  # TIA 输出偏置 [V]；解码时显式移除。
    adc: AdcParams  # Offset-binary 量化；可更换量程/精度，并观察量化损失。
    output_bits: int  # 最终有符号整数宽度 [bit]；1..64，中间累加为无限精度。
    overflow: Literal["error", "saturate", "wrap"] = "error"  # 只在最终输出应用的溢出策略。

    # 限定位移与软件数值支持域；数字零必须对应零行电压。
    def __post_init__(self) -> None:
        for name, kind in (("encoding", BitSerialParams), ("array", ConductanceArrayParams),
                           ("dac", VoltageDac), ("adc", AdcParams)):
            if not isinstance(getattr(self, name), kind):
                raise TypeError(f"{name} must be {kind.__name__}")
        count("output_bits", self.output_bits)
        if self.output_bits > 64 or self.encoding.input_bits + self.encoding.magnitude_bits > 64:
            raise ValueError("CIM reference supports output <=64 bits and shifts <64")
        if self.encoding.cell_bits > 32:
            raise ValueError("CIM conductance encoding supports cell_bits <=32")
        if self.overflow not in ("error", "saturate", "wrap"):
            raise ValueError("unsupported output overflow policy")
        positive("conductance_step_s", self.conductance_step_s)
        real("tia_gain_ohm", self.tia_gain_ohm)
        real("tia_offset_v", self.tia_offset_v)
        if self.tia_gain_ohm == 0:
            raise ValueError("TIA gain cannot be zero")
        if self.dac.resolution_bits != 1 or self.dac.output_min_v != 0 or self.dac.output_max_v <= 0:
            raise ValueError("bit-serial CIM needs a zero-based 1-bit voltage DAC")
        if self.dac.output_max_v > self.array.max_abs_input_v:
            raise ValueError("DAC read voltage exceeds array input range")
        maximum_digit = (1 << min(self.encoding.cell_bits, self.encoding.magnitude_bits)) - 1
        maximum_g = Fraction(self.array.conductance_min_s) + maximum_digit * Fraction(self.conductance_step_s)
        if maximum_g > Fraction(self.array.conductance_max_s):
            raise ValueError("encoded weight states exceed characterized conductance range")
        positive("unit_current_a", self.conductance_step_s * self.dac.output_max_v)
        positive("unit_signal_v", abs(self.conductance_step_s * self.dac.output_max_v * self.tia_gain_ohm))


# 稠密完整阵列输入；正负权重用幅度与独立差分支路表示，未支持有符号输入编码。
@dataclass(frozen=True, slots=True, kw_only=True)
class CimInput:
    work_id: str  # 调用者的数据/工作身份；样本 ID 在此命名空间内产生。
    input_codes: tuple[int, ...]  # R 个无符号逻辑输入 [integer]。
    weights: tuple[tuple[int, ...], ...]  # 行优先整数 W[R,C]；权重预先驻留的边界数据。

    # 冻结整数矩阵与向量；shape/位宽是否适配硬件在执行入口检查。
    def __post_init__(self) -> None:
        identifier("work_id", self.work_id)
        values = typed_tuple("input_codes", self.input_codes, int)
        rows = typed_tuple("weights", self.weights, (tuple, list))
        rows = tuple(typed_tuple("weight row", row, int) for row in rows)
        if not values or not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
            raise ValueError("CIM inputs require a nonempty rectangular matrix and vector")
        if any(type(v) is not int for v in values) or any(type(v) is not int for row in rows for v in row):
            raise TypeError("CIM codes and weights must be Python integers, not bool")
        object.__setattr__(self, "input_codes", values)
        object.__setattr__(self, "weights", rows)


# 一个输出列/差分支路的真实转换输入与量化结果，保持其数据身份贯穿时序分析。
@dataclass(frozen=True, slots=True)
class CimReadout:
    sample_id: str  # work/bit/slice/branch/column 唯一样本 ID。
    column: int  # 输出列索引 [column]。
    branch: str  # difference、positive、negative 或 unsigned。
    current_a: float  # 本次 TIA 输入的列电流或差分电流 [A]。
    voltage_v: float  # TIA 输出、ADC 输入 [V]。
    adc_sample: AdcSample  # 码值及严格越量程标志。


# 一次输入 bit 与权重 slice 的完整局部数值路径；所有列完整执行，不跳过零。
@dataclass(frozen=True, slots=True)
class CimPhase:
    phase_id: str  # 此 bit/slice 组合的身份。
    input_bit: int  # 输入 bit 索引 [bit]。
    weight_slice: int  # 权重幅度 slice 索引 [slice]。
    row_codes: tuple[int, ...]  # 本次每行的 DAC 码 0/1 [code]。
    row_voltages_v: tuple[float, ...]  # DAC 实际行驱动 [V]。
    readouts: tuple[CimReadout, ...]  # 列优先，数字差分时同列 positive/negative 相邻。
    partials: tuple[int, ...]  # ADC 中点重建、仿射恢复后 ties-to-even 舍入的整数部分和。
    shift: int  # input_bit+weight_slice*cell_bits [bit]。


# 功能输出保留真实程序矩阵、中间值与编码来源；没有隐含目标时间。
@dataclass(frozen=True, slots=True)
class CimNumericResult:
    input_identity: str  # 完整 CimInput 的内容哈希。
    weight_identity: str  # 原始整数权重内容哈希。
    encoding_identity: str  # 编码/阵列/ΔG 与传递函数配置身份。
    programmed_arrays: tuple[ConductanceArray, ...]  # slice-major、positive/negative 顺序的已编程初态。
    work: BitSerialWork  # 逻辑 MAC、实际 cell/ADC 动作与物理权重位。
    phases: tuple[CimPhase, ...]  # bit-major/slice-major 的显式工作序列。
    unbounded_output: tuple[int, ...]  # 量化后部分和的无限精度移位累加结果。
    output: tuple[int, ...]  # 应用最终输出溢出策略后的结果。
    output_overflowed: tuple[bool, ...]  # 量化后无限精度结果是否超出输出宽度。
    clipped_samples: int  # ADC 严格越量程的样本数 [sample]。


# G=Gmin+digit*ΔG；尾 slice 的未使用高位保持零，正负幅度存入不同阵列。
def encode_conductances(p: CimNumericParams, weights: tuple[tuple[int, ...], ...]) -> tuple[ConductanceArray, ...]:
    if not isinstance(p, CimNumericParams):
        raise TypeError("p must be CimNumericParams")
    rows = typed_tuple("weights", weights, (tuple, list))
    rows = tuple(typed_tuple("weight row", row, int) for row in rows)
    if len(rows) != p.array.rows or any(len(row) != p.array.columns for row in rows):
        raise ValueError("weights must match full array geometry")
    maximum = (1 << p.encoding.magnitude_bits) - 1
    for row in rows:
        for value in row:
            if type(value) is not int:
                raise TypeError("weights must be Python ints")
            if abs(value) > maximum or (value < 0 and not p.encoding.differential):
                raise ValueError("weight sign/magnitude exceeds declared encoding")
    slices = (p.encoding.magnitude_bits + p.encoding.cell_bits - 1) // p.encoding.cell_bits
    mask = (1 << p.encoding.cell_bits) - 1
    result = []
    for weight_slice in range(slices):
        for sign in ((1, -1) if p.encoding.differential else (1,)):
            matrix = tuple(tuple(float(Fraction(p.array.conductance_min_s) + Fraction(p.conductance_step_s)
                                * ((max(sign * w, 0) >> (weight_slice * p.encoding.cell_bits)) & mask))
                                 for w in row) for row in rows)
            result.append(ConductanceArray(params=p.array, conductances_s=matrix))
    return tuple(result)


# ADC 返回区间码，重建值取 bin 中点；它不是 DAC 传递函数的逆。
def _midpoint(p: AdcParams, code: int) -> Fraction:
    step = (Fraction(p.input_max_v) - Fraction(p.input_min_v)) / (1 << p.resolution_bits)
    return Fraction(p.input_min_v) + (Fraction(code) + Fraction(1, 2)) * step


# 完整数值链；独立 ADC clock 仅供复用其构造接口，数值结果不依赖频率。
def evaluate_cim(p: CimNumericParams, inputs: CimInput, *, adc_frequency_hz: float = 1.0,
                 max_cell_evaluations: int = 1_000_000) -> CimNumericResult:
    if not isinstance(p, CimNumericParams) or not isinstance(inputs, CimInput):
        raise TypeError("evaluate_cim needs CimNumericParams and CimInput")
    count("max_cell_evaluations", max_cell_evaluations)
    work = derive_bit_serial(p.encoding, rows=p.array.rows, columns=p.array.columns)
    if work.cell_evaluations > max_cell_evaluations:
        raise ValueError("CIM work exceeds host max_cell_evaluations")
    if len(inputs.input_codes) != p.array.rows:
        raise ValueError("input vector must match array rows")
    if any(not 0 <= code < (1 << p.encoding.input_bits) for code in inputs.input_codes):
        raise ValueError("input code exceeds unsigned encoding")
    arrays = encode_conductances(p, inputs.weights)
    adc = IdealAdc(params=p.adc, frequency_hz=adc_frequency_hz)
    branches = 2 if p.encoding.differential else 1
    slices = len(arrays) // branches
    unit_v = Fraction(p.conductance_step_s) * Fraction(p.dac.output_max_v) * Fraction(p.tia_gain_ohm)
    phases = []
    for bit in range(p.encoding.input_bits):
        codes = tuple((value >> bit) & 1 for value in inputs.input_codes)
        voltages = tuple(p.dac.convert(code) for code in codes)
        baseline_v = Fraction(p.array.conductance_min_s) * sum(map(Fraction, voltages)) * Fraction(p.tia_gain_ohm)
        for weight_slice in range(slices):
            phase_id = f"{inputs.work_id}/bit/{bit}/slice/{weight_slice}"
            currents = tuple(array.evaluate(voltages) for array in arrays[weight_slice * branches:(weight_slice + 1) * branches])
            readouts, partials = [], []
            for column in range(p.array.columns):
                if p.encoding.subtract_before_adc:
                    samples = (("difference", currents[0][column] - currents[1][column]),)
                elif p.encoding.differential:
                    samples = (("positive", currents[0][column]), ("negative", currents[1][column]))
                else:
                    samples = (("unsigned", currents[0][column]),)
                reconstructed = []
                for branch, current in samples:
                    voltage = transimpedance((current,), gain_ohm=p.tia_gain_ohm, offset_v=p.tia_offset_v)[0]
                    sample = adc.convert(voltage)
                    readouts.append(CimReadout(f"{phase_id}/{branch}/column/{column}", column, branch, current, voltage, sample))
                    reconstructed.append(_midpoint(p.adc, sample.code))
                if len(reconstructed) == 2:
                    signal = reconstructed[0] - reconstructed[1]
                else:
                    signal = reconstructed[0] - Fraction(p.tia_offset_v)
                    if not p.encoding.differential:
                        signal -= baseline_v
                partials.append(round(signal / unit_v))
            phases.append(CimPhase(phase_id, bit, weight_slice, codes, voltages, tuple(readouts), tuple(partials),
                                   bit + weight_slice * p.encoding.cell_bits))
    totals = tuple(sum(phase.partials[j] << phase.shift for phase in phases) for j in range(p.array.columns))
    output = tuple(shift_accumulate(tuple(phase.partials[j] for phase in phases), tuple(phase.shift for phase in phases),
                                    width_bits=p.output_bits, overflow=p.overflow) for j in range(p.array.columns))
    lower, upper = -(1 << (p.output_bits - 1)), (1 << (p.output_bits - 1)) - 1
    clipped = sum(r.adc_sample.clipped_low or r.adc_sample.clipped_high for phase in phases for r in phase.readouts)
    return CimNumericResult(content_hash(inputs), content_hash(inputs.weights), content_hash(p), arrays, work,
                             tuple(phases), totals, output, tuple(not lower <= total <= upper for total in totals), clipped)

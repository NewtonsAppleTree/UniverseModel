"""位串行输入、差分权重的物理工作量；逻辑 MAC 与 cell/ADC 动作分开。"""

from dataclasses import dataclass

from chipmodel.common import ceil_div, count


# 一组位切片规则；权重位数表示 magnitude 编码宽度，符号由独立差分支路表达。
@dataclass(frozen=True, slots=True, kw_only=True)
class BitSerialParams:
    input_bits: int  # 无符号输入编码宽度 Bin [bit]；每 bit 一次输入相位。
    magnitude_bits: int  # 权重绝对值编码宽度 Bw [bit]。
    cell_bits: int  # 每个 cell 存储的幅度位数 Bcell [bit/cell]。
    differential: bool  # True 使用 G+、G− 两个支路表达有符号权重。
    subtract_before_adc: bool  # True 在 ADC 前求差；False 分别转换后数字相减。

    # 位宽为正，符号/差分策略显式；无差分支路时不允许声明模拟求差。
    def __post_init__(self) -> None:
        for name in ("input_bits", "magnitude_bits", "cell_bits"):
            count(name, getattr(self, name))
        for name in ("differential", "subtract_before_adc"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")
        if self.subtract_before_adc and not self.differential:
            raise ValueError("subtract_before_adc requires differential branches")


# 单次 R×C MatVec 的动作与物理容量；假设所有行列/位相位完整执行。
@dataclass(frozen=True, slots=True)
class BitSerialWork:
    logical_macs: int  # 逻辑工作 R*C [MAC]。
    physical_arrays: int  # ceil(Bw/Bcell)*branches [array]。
    input_phases: int  # Bin [phase]。
    cell_evaluations: int  # R*C*physical_arrays*Bin [cell-evaluation]。
    adc_conversions: int  # C*weight_slices*Bin*converted_branches [conversion]。
    physical_weight_bits: int  # R*C*physical_arrays*Bcell [bit]，包含空闲编码位。


# 展开差分/位切片的乘数；前 ADC 求差改变转换数，不消除两支阵列的 cell 活动。
def derive_bit_serial(p: BitSerialParams, *, rows: int, columns: int) -> BitSerialWork:
    count("rows", rows)
    count("columns", columns)
    slices = ceil_div(p.magnitude_bits, p.cell_bits)
    branches = 2 if p.differential else 1
    converted = 1 if p.subtract_before_adc else branches
    arrays = slices * branches
    return BitSerialWork(rows * columns, arrays, p.input_bits,
                         rows * columns * arrays * p.input_bits,
                         columns * slices * p.input_bits * converted,
                         rows * columns * arrays * p.cell_bits)

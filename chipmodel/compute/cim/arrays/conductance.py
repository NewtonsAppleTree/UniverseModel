"""理想 conductance crossbar：列电流 I_j=Σ_i G_ij V_i；不含线阻或读噪声。"""

from dataclasses import dataclass
from math import fsum

from chipmodel.common import count, positive, real


# 阵列几何与电气适用域；cell 数不直接给出吞吐或有效权重容量。
@dataclass(frozen=True, slots=True, kw_only=True)
class ConductanceArrayParams:
    rows: int  # 驱动行数 R [row]。
    columns: int  # 读出列数 C [column]。
    conductance_min_s: float  # 允许电导下限 Gmin [S]；可为理想零电导。
    conductance_max_s: float  # 电导上限 Gmax [S]。
    max_abs_input_v: float  # 输入绝对电压上限 |V| [V]。

    # 检查 R/C>0、0≤Gmin<Gmax 与 |V|max>0。
    def __post_init__(self) -> None:
        count("rows", self.rows)
        count("columns", self.columns)
        real("conductance_min_s", self.conductance_min_s, minimum=0)
        positive("conductance_max_s", self.conductance_max_s)
        positive("max_abs_input_v", self.max_abs_input_v)
        if self.conductance_min_s >= self.conductance_max_s:
            raise ValueError("conductance_min_s must be below conductance_max_s")


# 一份固定编程后的电导矩阵；深拷贝到 tuple，避免外部修改影响功能结果。
@dataclass(frozen=True, slots=True, kw_only=True)
class ConductanceArray:
    params: ConductanceArrayParams  # 阵列结构与电气范围。
    conductances_s: tuple[tuple[float, ...], ...]  # G[R,C] [S]；行优先。

    # 校验矩阵 shape 和每个 G；冻结编程初态，不模拟 program/erase 生命周期。
    def __post_init__(self) -> None:
        p = self.params
        values = tuple(tuple(real("conductance_s", g) for g in row)
                       for row in self.conductances_s)
        if len(values) != p.rows or any(len(row) != p.columns for row in values):
            raise ValueError("conductances_s must have shape [rows, columns]")
        if any(not p.conductance_min_s <= g <= p.conductance_max_s for row in values for g in row):
            raise ValueError("conductances_s outside characterized range")
        object.__setattr__(self, "conductances_s", values)

    # 给定 R 个行电压 [V]，计算 C 个列电流 I=GᵀV [A]；不隐式把 A 转成 V。
    def evaluate(self, voltages_v: tuple[float, ...]) -> tuple[float, ...]:
        values = tuple(real("voltage_v", v) for v in voltages_v)
        if len(values) != self.params.rows:
            raise ValueError("voltages_v length must equal rows")
        if any(abs(v) > self.params.max_abs_input_v for v in values):
            raise ValueError("voltages_v exceeds max_abs_input_v")
        return tuple(real("column_current_a", fsum(v * row[j] for v, row in zip(
            values, self.conductances_s))) for j in range(self.params.columns))


# 显式模拟前端增益：Vout=Voffset+I*Rtia；Rtia [Ω] 为带符号跨阻，极性由调用方决定。
def transimpedance(currents_a: tuple[float, ...], *, gain_ohm: float,
                   offset_v: float) -> tuple[float, ...]:
    gain = real("gain_ohm", gain_ohm)
    offset = real("offset_v", offset_v)
    return tuple(real("output_v", offset + real("current_a", i) * gain) for i in currents_a)

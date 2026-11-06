# encoding：逻辑量、编码量与物理动作

BitSerialParams 明确 input bits、权重 magnitude bits、cell bits、差分支路和求差位置。这里 magnitude_bits 表示绝对值编码宽度，不能直接解释为二进制补码的有效位数。

`weight_slices=ceil(magnitude_bits/cell_bits)`；physical arrays=切片数×支路数。cell 动作覆盖所有支路/相位；ADC 前求差可以减少转换数，却不减少两个支路的 cell 活动。物理权重 bit 包含未用编码位，逻辑 MAC 始终是 R*C。

`shift_accumulate` 是独立数值参考：Σpartial·2^shift，最终执行 error/saturate/wrap。参数 partial [integer code]、shift [bit]、width_bits [bit]、overflow [policy] 显式传入。当前支持 1..64 bit 输出和 0..63 bit 位移；只在最终输出溢出处理，与每一步都饱和的硬件并不等价。

最关心符号表达、求差位置、切片位权和累加宽度。稀疏跳过、权重编程与实际切片调度未实现；真实执行的次数需要由映射/事件模型确认。

<!-- model-fields:start -->

### [accumulate.py](accumulate.py)

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `shift_accumulate(partials: tuple[int, ...], shifts: tuple[int, ...], *, width_bits: int, overflow: str)` | y=Σ partial_i*2^shift_i；先用无限精度整数累加，再按 width_bits 做 error/saturate/wrap。 |

### [bit_serial.py](bit_serial.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `BitSerialParams` | `input_bits` | `int` | bit | 无符号输入编码宽度 Bin [bit]；每 bit 一次输入相位。 |
| `BitSerialParams` | `magnitude_bits` | `int` | bit | 权重绝对值编码宽度 Bw [bit]。 |
| `BitSerialParams` | `cell_bits` | `int` | bit/cell | 每个 cell 存储的幅度位数 Bcell [bit/cell]。 |
| `BitSerialParams` | `differential` | `bool` | 1（布尔） | True 使用 G+、G− 两个支路表达有符号权重。 |
| `BitSerialParams` | `subtract_before_adc` | `bool` | 1（布尔） | True 在 ADC 前求差；False 分别转换后数字相减。 |
| `BitSerialWork` | `logical_macs` | `int` | MAC | 逻辑工作 R*C [MAC]。 |
| `BitSerialWork` | `physical_arrays` | `int` | array | ceil(Bw/Bcell)*branches [array]。 |
| `BitSerialWork` | `input_phases` | `int` | phase | Bin [phase]。 |
| `BitSerialWork` | `cell_evaluations` | `int` | cell-evaluation | R*C*physical_arrays*Bin [cell-evaluation]。 |
| `BitSerialWork` | `adc_conversions` | `int` | conversion | C*weight_slices*Bin*converted_branches [conversion]。 |
| `BitSerialWork` | `physical_weight_bits` | `int` | bit | R*C*physical_arrays*Bcell [bit]，包含空闲编码位。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `BitSerialParams` | 一组位切片规则；权重位数表示 magnitude 编码宽度，符号由独立差分支路表达。 |
| `BitSerialWork` | 单次 R×C MatVec 的动作与物理容量；假设所有行列/位相位完整执行。 |
| `derive_bit_serial(p: BitSerialParams, *, rows: int, columns: int)` | 展开差分/位切片的乘数；前 ADC 求差改变转换数，不消除两支阵列的 cell 活动。 |

<!-- model-fields:end -->

# npu：稠密矩阵工作量与 MAC 服务

GemmWorkload 定义 A[M,K]×B[K,N]→C[M,N] 的逻辑量；MacArray 接收显式的实际 MAC 次数与 P/L/II/ClockDomain。逻辑 MAC=M*N*K；按 FLOP 汇报时另声明 2 FLOP/MAC。

输入和输出字节是每个张量的紧密 bit packing 存储量，分别向 byte 取整；不代表实际 SRAM/DRAM 访问流量。Tiling、权重重用、padding、重算和稀疏应由映射方改变 executed_macs 与路径流量。K=0 时没有 MAC，但输出张量仍可有存储需求，其初始化成本由上层明确。

最关心 M/N/K、精度、实际 lane 利用、供数和归约依赖。`estimate` 假设足够独立操作、所有输入就绪；latency 不是自动推导的 systolic fill/drain 时间。PE 编排、累加溢出、activation、normalization、稀疏数据流尚未实现。

使用顺序：GemmWorkload 查询逻辑量 → 映射成实际工作量/数据移动 → MacArray 独立估算 → memory/control/interconnect 与 composition 组合。数值正确性需具体算子参考；该模型只分析工作量。

CH6增加`MacArithmetic`签名与`MacWork`、`MacArray.analyze`。签名区分integer_mac/float_mul_add/float_fma以及operand/accumulator/output格式，FP16与BF16不互换；输出转换尚未纳入，output必须等于accumulator。每个profile只绑定一种签名，分析请求必须完全匹配；历史estimate仍是无格式的流水线查询，不构成格式支持证据。

实际工作至少为逻辑工作；额外MAC、G*P发起槽和尾空槽分别报告。packing_efficiency=executed/(G*P)，useful_work_fraction=logical/executed，空分母为None，均非动态利用率。执行时间/能耗未知，有限中间累加/舍入正确性由任务参考承担。Tile显式格式接口复用同一服务结果计费。手算、格式/尾批反例及MAC加倍仍受供数限制的证据见[CH6指南](../../docs/compute_capabilities.md)。

<!-- model-fields:start -->

### [mac.py](mac.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `MacArithmetic` | `operation` | `Literal['integer_mac', 'float_mul_add', 'float_fma']` | —（结构/对象） | 一乘一加的整数、两次舍入浮点或融合浮点语义。 |
| `MacArithmetic` | `operand_format` | `Literal['int8', 'int16', 'int32', 'int64', 'float16', 'bfloat16', 'float32', 'float64']` | —（结构/对象） | A/B相同的显式格式。 |
| `MacArithmetic` | `accumulator_format` | `Literal['int32', 'int64', 'float32', 'float64']` | —（结构/对象） | 部分和保存格式；不隐含无限精度。 |
| `MacArithmetic` | `output_format` | `Literal['int32', 'int64', 'float32', 'float64']` | —（结构/对象） | 本服务不含输出转换，必须与累加格式相同。 |
| `MacWork` | `arithmetic` | `MacArithmetic` | —（结构/对象） | 请求的操作/操作数/累加/输出格式签名。 |
| `MacWork` | `logical_macs` | `int` | MAC | 所需有效逻辑工作 [MAC]，可为0。 |
| `MacWork` | `executed_macs` | `int` | MAC | 实际包含padding/重算的工作 [MAC]，至少logical_macs。 |
| `MacAnalysis` | `arithmetic` | `MacArithmetic` | —（结构/对象） | 已匹配的请求/能力签名。 |
| `MacAnalysis` | `logical_macs` | `int` | MAC | 本次逻辑工作 [MAC]。 |
| `MacAnalysis` | `executed_macs` | `int` | MAC | 本次实际工作 [MAC]。 |
| `MacAnalysis` | `extra_macs` | `int` | MAC | executed-logical [MAC]，映射额外工作。 |
| `MacAnalysis` | `issued_lane_slots` | `int` | MAC slot | ceil(executed/P)*P [MAC slot]。 |
| `MacAnalysis` | `unused_tail_slots` | `int` | MAC slot | issued_lane_slots-executed [MAC slot]。 |
| `MacAnalysis` | `packing_efficiency` | `float \| None` | 1 | executed/issued_lane_slots [1]；无工作时None。 |
| `MacAnalysis` | `useful_work_fraction` | `float \| None` | 1 | logical/executed [1]；不等于动态执行利用率。 |
| `MacAnalysis` | `service` | `PipelineEstimate` | —（结构/对象） | 足够独立MAC、供数及在途容量下的孤立服务结果。 |
| `MacAnalysis` | `execution_time_s` | `None` | s | 实际任务时间 [s]；依赖、供数、流水槽/反馈未建模。 |
| `MacAnalysis` | `energy_j` | `None` | J | 服务能量 [J]，没有特征化输入。 |
| `MacAnalysis` | `unknown_reason` | `str` | 1（标识/枚举） | 未知时间/物理成本与功能边界。 |
| `MacAnalysis` | `profile_source` | `str` | 1（标识/枚举） | 签名对应的P/L/II和时钟参数来源。 |
| `GemmWorkload` | `m` | `int` | element | 输出行数 M [element]。 |
| `GemmWorkload` | `n` | `int` | element | 输出列数 N [element]。 |
| `GemmWorkload` | `k` | `int` | element | 归约维 K [element]。 |
| `GemmWorkload` | `operand_bits` | `int` | bit/element | A/B 每个元素的逻辑位宽 [bit/element]。 |
| `GemmWorkload` | `output_bits` | `int` | bit/element | C 每个元素的存储位宽 [bit/element]。 |
| `GemmWorkload` | `mac_count` | `int` | —（结构/对象） | 只读派生属性；稠密逻辑工作量 MAC=M*N*K；若按 FLOP 报告，调用方另声明 2 FLOP/MAC。 |
| `GemmWorkload` | `input_bytes` | `int` | —（结构/对象） | 只读派生属性；输入逻辑存储量：每个张量分别做 bit→byte 向上取整，不代表实际访问流量。 |
| `GemmWorkload` | `output_bytes` | `int` | B | 只读派生属性；输出逻辑存储量 ceil(M*N*output_bits/8) [B]。 |
| `MacArray` | `params` | `PipelineParams` | lane, cycle | P 个 MAC lane 及其 L/II [lane, cycle]。 |
| `MacArray` | `clock` | `ClockDomain` | —（结构/对象） | 固定计算时钟域。 |
| `MacArray` | `arithmetic` | `MacArithmetic \| None` | —（结构/对象） | 此档位唯一支持的签名；None仅可调用历史无格式estimate。 |
| `MacArray` | `profile_source` | `str` | 1（标识/枚举） | 操作/格式对应的服务来源，不能由NPU/tensor名称推断。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `MacArithmetic` | 操作和数值格式组成完整服务签名；同位宽格式及融合/非融合运算不互换。 |
| `MacWork` | 本包稠密任务的逻辑/实际工作分离；padding和重算由映射方提供，不能静默少算。 |
| `MacAnalysis` | 数量、尾批和显式服务边界；实际执行时间/能耗与数值质量不由峰值推导。 |
| `GemmWorkload` | GEMM 的逻辑语义：A[M,K]×B[K,N]→C[M,N]，一次 MAC 按一个逻辑操作计。 |
| `GemmWorkload.mac_count` | 稠密逻辑工作量 MAC=M*N*K；若按 FLOP 报告，调用方另声明 2 FLOP/MAC。 |
| `GemmWorkload.input_bytes` | 输入逻辑存储量：每个张量分别做 bit→byte 向上取整，不代表实际访问流量。 |
| `GemmWorkload.output_bytes` | 输出逻辑存储量 ceil(M*N*output_bits/8) [B]。 |
| `MacArray` | MAC engine 使用通用 P/L/II；每 lane 每次发起一个 MAC，供数和依赖由外部保证。 |
| `MacArray.estimate(self, executed_macs: int)` | 估算指定的实际 MAC 次数；包含 padding/重算的量须由映射方显式传入。 |
| `MacArray.analyze(self, work: MacWork)` | 完整签名匹配后统计尾批和额外工作；复用同一P/L/II公式，不收取第二份计算成本。 |

<!-- model-fields:end -->

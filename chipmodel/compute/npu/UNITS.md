# npu：稠密矩阵工作量与 MAC 服务

GemmWorkload 定义 A[M,K]×B[K,N]→C[M,N] 的逻辑量；MacArray 接收显式的实际 MAC 次数与 P/L/II/ClockDomain。逻辑 MAC=M*N*K；按 FLOP 汇报时另声明 2 FLOP/MAC。

输入和输出字节是每个张量的紧密 bit packing 存储量，分别向 byte 取整；不代表实际 SRAM/DRAM 访问流量。Tiling、权重重用、padding、重算和稀疏应由映射方改变 executed_macs 与路径流量。K=0 时没有 MAC，但输出张量仍可有存储需求，其初始化成本由上层明确。

最关心 M/N/K、精度、实际 lane 利用、供数和归约依赖。`estimate` 假设足够独立操作、所有输入就绪；latency 不是自动推导的 systolic fill/drain 时间。PE 编排、累加溢出、activation、normalization、稀疏数据流尚未实现。

使用顺序：GemmWorkload 查询逻辑量 → 映射成实际工作量/数据移动 → MacArray 独立估算 → memory/control/interconnect 与 composition 组合。数值正确性需具体算子参考；该模型只分析工作量。

<!-- model-fields:start -->

### [mac.py](mac.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
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

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `GemmWorkload` | GEMM 的逻辑语义：A[M,K]×B[K,N]→C[M,N]，一次 MAC 按一个逻辑操作计。 |
| `GemmWorkload.mac_count` | 稠密逻辑工作量 MAC=M*N*K；若按 FLOP 报告，调用方另声明 2 FLOP/MAC。 |
| `GemmWorkload.input_bytes` | 输入逻辑存储量：每个张量分别做 bit→byte 向上取整，不代表实际访问流量。 |
| `GemmWorkload.output_bytes` | 输出逻辑存储量 ceil(M*N*output_bits/8) [B]。 |
| `MacArray` | MAC engine 使用通用 P/L/II；每 lane 每次发起一个 MAC，供数和依赖由外部保证。 |
| `MacArray.estimate(self, executed_macs: int)` | 估算指定的实际 MAC 次数；包含 padding/重算的量须由映射方显式传入。 |

<!-- model-fields:end -->

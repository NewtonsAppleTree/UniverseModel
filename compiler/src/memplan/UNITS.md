# memplan：三缓冲容量与逐行搬运账本

`plan_memory` 规划三个互不重叠、紧密打包的 scratch arena；A/B/C 各取步骤最大所需字节，offset 为 0、A、A+B。allocation=A+B+C；peak_live=max_step(A_step+B_step+C_step)，不能用先后累计量冒充同时容量。容量不足时拒绝；物理资源由调用方提供，allocator 不创建第二份硬件。

`count_traffic` 先校验计划，再输出 LinearTraffic/LinearTransfer。A/B 每步都重读；C 首次置零无外部读，驻留方案仅最终写，回写方案在每个 K 边界各写/读一次。外部 row-major 子矩形按行发请求，无跨行合并、地址对齐或 cache 推断。payload 是有效字节，DMA burst/总线取整由消费模型计量。

设 qM=ceil(M/Tm)、qN=ceil(N/Tn)、qK=ceil(K/Tk)，输入每元素 b、C 每元素 c 字节，则 A 读=qN·MKb，B 读=qM·KNb，最终 C 写=MNc。回写方案额外读+写=`2(qK-1)MNc`；此公式只在本模块的 reload 策略成立。MAC 始终 MNK。块尺寸、累加精度和容量为关键敏感量；没有目标执行时间、bank/port/双缓冲或缓存命中模型。

顺序：已校验公共计划 → 内存分配/容量判断 → 行请求/计数 → 功能消费者或外部 DMA 分析。max_transfers 仅限制宿主请求列表。44 B 边界及 314/954 B 手算验证见[测试](../../tests/test_linear_mapping.py)，模型条件见[实验指南](../../../evaluation/docs/linear_mapping.md)。

<!-- model-fields:start -->

### [linear.py](linear.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `LinearMemory` | `a_offset` | `int` | B | A arena start [B]; zero in this allocator. |
| `LinearMemory` | `a_bytes` | `int` | B | Maximum packed A tile storage [B]. |
| `LinearMemory` | `b_offset` | `int` | B | B arena start=a_bytes [B]. |
| `LinearMemory` | `b_bytes` | `int` | B | Maximum packed B tile storage [B]. |
| `LinearMemory` | `c_offset` | `int` | B | C arena start=a_bytes+b_bytes [B]. |
| `LinearMemory` | `c_bytes` | `int` | B | Maximum accumulator/output tile storage [B]. |
| `LinearMemory` | `allocation_bytes` | `int` | B | a_bytes+b_bytes+c_bytes [B]; three simultaneously reserved arenas. |
| `LinearMemory` | `peak_live_bytes` | `int` | B | max over updates of A+B+C valid tile payload [B]. |
| `LinearMemory` | `capacity_bytes` | `int` | B | Declared single scratch resource capacity [B]. |
| `LinearTransfer` | `step_index` | `int` | step | Index of the consuming/producing plan update [step]. |
| `LinearTransfer` | `purpose` | `Literal['a_read', 'b_read', 'partial_read', 'partial_write', 'output_write']` | —（结构/对象） | Cost ownership. |
| `LinearTransfer` | `payload_bytes` | `int` | B | Contiguous row payload [B]; burst rounding belongs to DMA backend. |
| `LinearTraffic` | `executed_macs` | `int` | MAC | Sum of actual tail-aware update work [MAC]; no padding or skipped zeros. |
| `LinearTraffic` | `a_read_bytes` | `int` | B | Sum of row payloads loading A [B]. |
| `LinearTraffic` | `b_read_bytes` | `int` | B | Sum of row payloads loading B [B]. |
| `LinearTraffic` | `partial_read_bytes` | `int` | B | Reloaded unfinished C payload [B]. |
| `LinearTraffic` | `partial_write_bytes` | `int` | B | Spilled unfinished C payload [B]. |
| `LinearTraffic` | `output_write_bytes` | `int` | B | Final completed C payload written once per output [B]. |
| `LinearTraffic` | `transfers` | `tuple[LinearTransfer, ...]` | —（结构/对象） | Serial DMA requests in each step's data-dependency order. |
| `LinearTraffic` | `external_bytes` | `int` | B | 只读派生属性；Total external payload D=A+B+partial reads+writes+final output [B]. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `LinearMemory` | Contiguous scratch arenas; offsets are local bytes, not external tensor addresses. |
| `LinearTransfer` | One externally contiguous tensor-row copy; no cross-row coalescing, no implicit zero-byte requests. |
| `LinearTraffic` | Mapping-specific movement differs from the unique logical workload footprint. |
| `LinearTraffic.external_bytes` | Total external payload D=A+B+partial reads+writes+final output [B]. |
| `plan_memory(spec: LinearSpec, plan: LinearPlan, capacity_bytes: int)` | Reserve disjoint A/B/C arenas and reject insufficient capacity before functional execution. |
| `count_traffic(spec: LinearSpec, plan: LinearPlan, *, max_transfers: int=1000000)` | Expand row-major ROI copies; output-stationary retains C, reload-partials loads/stores between K slices. |

<!-- model-fields:end -->

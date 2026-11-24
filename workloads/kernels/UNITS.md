# kernels：稠密线性任务与逻辑工作量

`describe_work` 返回 `LinearWork`，`matvec_spec` 将矩阵向量乘映射到 N=1；`generate_inputs` 生成小规模不可变 A/B。只描述需完成的工作，不推断 cache、复用、padding 或跳零收益。输入格式/范围由[公共语义](../../contracts/workload/UNITS.md)约束。

工作量为 MNK MAC，按一乘一加记 2MNK op；A/B 唯一字节为 MK·b_in、KN·b_in，输出 MN·b_out。INT8 的 b_in=1，float64 的 b_in=8，b_out 均为 8。实际流量由 compiler 映射另外推导。

生成器 `sha256-index-v1` 对 `linear-input/v1:{seed}:{a或b}:{index}` 的 ASCII 字节求 SHA256，取首字节 `%17-8`，float64 再除以 16；这是稳定的有界测试数据，不声称无偏均匀抽样。seed 为 uint64，max_elements 限制 A/B 材料化元素总数，均不属于硬件资源。关键参数为形状/精度、seed 和宿主规模上限。

接口顺序：创建 spec → 生成或提供输入 → 逻辑计数/独立参考。固定 golden vector、存储和 MatVec 手算见[测试](../../tests/workloads/test_linear.py)。

## Attention 任务与计数

`attention.py` 的 AttentionWork 区分矩形 QK/AV MAC、因果有效配对、稳定softmax数学操作和唯一张量字节。B/Hq/Hkv/Sq/Skv/D/Dv及scale由[公共契约](../../contracts/workload/UNITS.md)维护；最敏感的是Sq·Skv、共享Hkv和D/Dv。因果配对P=B·Hq·[Sq·(query_start+1)+Sq·(Sq−1)/2]，矩形R=B·Hq·Sq·Skv；visible MAC=P·(D+Dv)，不自动代表硬件发射节省。分母加法按每行n−1计，排除软件初始化。

`generate_attention` 使用 attention-input/v1:{seed}:{q/k/v}:{index} 的ASCII SHA256首字节，取(byte%17−8)/16；seed为uint64，生成前限制总元素数。`describe_attention`不分配tensor，不受参考预算影响。矩形score字节只描述一个矩阵，不是强制scratch。完整公式/接口/依据见[指南](../docs/foundation_usage.md)，手算与独立数值验证见[测试](../../tests/workloads/test_attention.py)。

<!-- model-fields:start -->

### [attention.py](attention.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `AttentionWork` | `dense_qk_macs` | `int` | MAC | B*Hq*Sq*Skv*D [MAC], full rectangular QK contraction. |
| `AttentionWork` | `dense_av_macs` | `int` | MAC | B*Hq*Sq*Skv*Dv [MAC], full rectangular probability/value contraction. |
| `AttentionWork` | `visible_pairs` | `int` | pair | P valid query/key pairs [pair]; mask-aware algorithm opportunity, not executed work. |
| `AttentionWork` | `visible_pair_macs` | `int` | MAC | P*(D+Dv) [MAC]; exact mask exploitation must be justified by the mapping. |
| `AttentionWork` | `softmax_rows` | `int` | row | B*Hq*Sq [row], all nonempty by the contract. |
| `AttentionWork` | `reference_scale_multiplications` | `int` | multiply | P [multiply] for explicitly scaled visible logits. |
| `AttentionWork` | `reference_max_comparisons` | `int` | comparison | P-softmax_rows [comparison] for row maxima. |
| `AttentionWork` | `reference_subtractions` | `int` | subtract | P [subtract] for stable row shifts. |
| `AttentionWork` | `reference_exp_evaluations` | `int` | exp | P [exp]; the reference excludes masked scores before normalization. |
| `AttentionWork` | `reference_sum_additions` | `int` | add | P-softmax_rows [add], denominator reduction over valid exponentials. |
| `AttentionWork` | `reference_divisions` | `int` | divide | P [divide] to normalize probabilities; no reciprocal-fusion assumption. |
| `AttentionWork` | `q_bytes` | `int` | B | B*Hq*Sq*D*8 [B], unique query payload. |
| `AttentionWork` | `kv_bytes` | `int` | B | B*Hkv*Skv*(D+Dv)*8 [B], unique K/V payload without GQA replication. |
| `AttentionWork` | `output_bytes` | `int` | B | B*Hq*Sq*Dv*8 [B], output payload. |
| `AttentionWork` | `materialized_score_bytes` | `int` | B | B*Hq*Sq*Skv*8 [B] for one full matrix; not compulsory scratch or traffic. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `AttentionWork` | Keep complete rectangular demand, visible pairs, unique data and materialized intermediates separate. |
| `describe_attention(spec: AttentionSpec)` | Counts are shape/semantics dependent; no assumed cache reuse, bandwidth, scalar-to-MAC conversion or execution time. |
| `generate_attention(spec: AttentionSpec, seed: int, *, max_elements: int=1000000)` | Stable labeled SHA256 test inputs, values (byte%17-8)/16; synthetic bounded data, not a representative distribution. |

### [linear.py](linear.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `LinearWork` | `macs` | `int` | MAC | Dense logical work M*N*K [MAC]. |
| `LinearWork` | `conventional_operations` | `int` | operation | 2*M*N*K [operation], explicit 2-operation-per-MAC convention. |
| `LinearWork` | `a_bytes` | `int` | B | Unique logical A storage M*K*operand_bytes [B]. |
| `LinearWork` | `b_bytes` | `int` | B | Unique logical B storage K*N*operand_bytes [B]. |
| `LinearWork` | `output_bytes` | `int` | B | Unique logical C storage M*N*result_bytes [B]; excludes partial traffic. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `LinearWork` | Logical unique tensor storage is independent of mapping, cache behavior and physical transactions. |
| `describe_work(spec: LinearSpec)` | Return logical counts only; actual movement and scratch allocation belong to the selected plan. |
| `matvec_spec(rows: int, columns: int, *, dtype: str='int8')` | MatVec A[rows,columns] @ x[columns] uses N=1 and the same explicit accumulator semantics. |
| `generate_inputs(spec: LinearSpec, seed: int, *, max_elements: int=1000000)` | SHA256-index-v1 deterministically produces bounded codes [-8,8], or codes/16 for binary64. |

<!-- model-fields:end -->

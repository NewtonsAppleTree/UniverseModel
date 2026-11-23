# kernels：稠密线性任务与逻辑工作量

`describe_work` 返回 `LinearWork`，`matvec_spec` 将矩阵向量乘映射到 N=1；`generate_inputs` 生成小规模不可变 A/B。只描述需完成的工作，不推断 cache、复用、padding 或跳零收益。输入格式/范围由[公共语义](../../contracts/workload/UNITS.md)约束。

工作量为 MNK MAC，按一乘一加记 2MNK op；A/B 唯一字节为 MK·b_in、KN·b_in，输出 MN·b_out。INT8 的 b_in=1，float64 的 b_in=8，b_out 均为 8。实际流量由 compiler 映射另外推导。

生成器 `sha256-index-v1` 对 `linear-input/v1:{seed}:{a或b}:{index}` 的 ASCII 字节求 SHA256，取首字节 `%17-8`，float64 再除以 16；这是稳定的有界测试数据，不声称无偏均匀抽样。seed 为 uint64，max_elements 限制 A/B 材料化元素总数，均不属于硬件资源。关键参数为形状/精度、seed 和宿主规模上限。

接口顺序：创建 spec → 生成或提供输入 → 逻辑计数/独立参考。固定 golden vector、存储和 MatVec 手算见[测试](../../tests/workloads/test_linear.py)。

<!-- model-fields:start -->

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

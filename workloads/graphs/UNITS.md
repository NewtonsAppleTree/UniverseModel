# graphs：Linear 训练短链与完整语义工作

当前 `training.py` 构造窄范围的 Linear→可选 ReLU→Linear 训练链，支持 1–16 层 Linear；不是通用图 IR。语义值由 [contracts/workload](../../contracts/workload/UNITS.md)维护，输入生成和工作量不依赖 compiler/hardware。给定 TrainingSpec 与 seed，`generate_training` 返回 version=0 的独立权重快照及实际 x/target。

生成算法 `training-sha256-index-v1` 对 `training-input/v1:{seed}:{label}:{index}` 的 ASCII 字节求 SHA256，首字节 `%17-8` 再除 16；label 是 x、target、w0/w1 等独立张量名。seed 为 uint64，max_elements 限制参数和输入总元素数；仅为稳定有界测试数据，不声称代表性或无偏分布。

设 P=Σ din·dout，B=batch，D=B·d_final，H=B·Σhidden_width。完整 GEMM 工作=3BP MAC；mean MSE 的标量动作=4D+2，SGD=2P。ReLU 在前向/反向各 H 次比较与选择，identity 为零。反向材料化转置共 B·Σ各层输入宽+P 个元素，参数唯一容量=8P B。不能将 MAC 乘 2 后宣称包含全部训练工作；其他动作分开统计。

接口：spec → 生成 state/data / `describe_training` → 独立参考或外部执行。最敏感的是 batch/层宽、激活策略、精度、seed 与宿主规模预算；无模型时延/能耗。手算、MSE 归一化、有限差分见[验证](../../tests/workloads/test_training.py)，跨模块范围见[指南](../../evaluation/docs/training_step.md)。

<!-- model-fields:start -->

### [training.py](training.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `TrainingWork` | `gemm_macs` | `int` | MAC | 3*B*sum(d_l*d_(l+1)) [MAC]; includes every input and weight gradient. |
| `TrainingWork` | `scalar_arithmetic_operations` | `int` | scalar operation | Mean-MSE 4*B*d_L+2 plus SGD 2*P [scalar operation]. |
| `TrainingWork` | `comparisons` | `int` | comparison | Forward/backward ReLU 2*B*sum(hidden_widths) [comparison]; zero for identity. |
| `TrainingWork` | `selections` | `int` | selection | Forward/backward ReLU 2*B*sum(hidden_widths) [selection]; no floating multiply implied. |
| `TrainingWork` | `transpose_elements` | `int` | element | sum(B*d_l + d_l*d_(l+1)) [element]; explicit backward input/weight transposes. |
| `TrainingWork` | `parameter_bytes` | `int` | B | 8*P [B]; excludes activations, gradients, next state and scratch. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `TrainingWork` | Keep dense contractions, auxiliary arithmetic, comparisons and data rearrangements in distinct counters. |
| `describe_training(spec: TrainingSpec)` | Derive logical actions independently of the compiler schedule; do not approximate training with only 3x forward. |
| `generate_training(spec: TrainingSpec, seed: int, *, max_elements: int=1000000)` | SHA256-index-v1 uses distinct tensor labels, immutable dyadic float data and a materialization bound. |

<!-- model-fields:end -->

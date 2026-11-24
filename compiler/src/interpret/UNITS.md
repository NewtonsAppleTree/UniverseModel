# interpret：显式计划的功能执行

`execute_plan` 校验输入/计划/容量，复制每步 A/B 的局部数据，根据策略保留 C 或在 K 切片间回写/重读外部 C。INT8 用精确整数乘加，float64 按 K 顺序做标量乘法与加法，无 FMA，出现非有限中间和时拒绝。状态是一次调用内的缓冲和输出；多次调用互不共享。

输出平坦 row-major C[M,N]。所有尾块按有效 extent 执行，不能漏算、重复或通过 padding 改变工作量。容量字节由 memplan 统一校验；Python 对象内存不代表目标 scratch 物理分配。max_macs 是宿主预算，不进入目标性能指标。

形状、dtype、K 顺序和 C 生命周期决定功能及数值结果；本模块不推进目标时钟。调用顺序：spec/inputs/plan/capacity → 校验 → 局部更新 → 完整输出；不依赖 workloads 的参考函数。手算矩形、重排、尾块与浮点消减验证见[测试](../../tests/test_linear_mapping.py)，独立精确参考由 evaluation 接入。

## 训练 step 与独立更新

`execute_training` 依次执行固定训练计划，复用现有 GEMM 功能；额外支持转置、ReLU/反向 mask、顺序 binary64 mean MSE 和 plain SGD。完成返回 TrainingResult 与 TrainingPlan，局部 backing lease 在最后使用后释放，输出/梯度/新权重保留到 step 边界。辅助算子的局部变量/寄存器不作为已建模 scratch 成本。

`apply_sgd` 可独立调用，检查 dW/dX 形状、梯度源版本及源状态内容哈希，再做 W_next=W−lr·dW，返回 version+1；lr=0 也推进逻辑步，原对象不变。所有中间输出有限，溢出拒绝。数值与状态反例见[训练编译测试](../../tests/test_training.py)。

## Attention计划功能执行

`attention.py`使用float64独立乘加、math.exp稳定softmax和AV，按合法计划实际执行expanded副本及spill读写，屏蔽key不参与数学运算。先校验输入/计划/两份容量，再检查max_macs与max_elements宿主预算，最后返回O；非有限中间值失败。功能解释不提供目标时间，数值舍入独立于Fraction/Decimal参考；query_tile只改变分块，不改同一行归约次序。手算、18组随机形状×4策略、超限与格式差异见[集成测试](../../../tests/integration/test_attention_mapping_experiment.py)和[指南](../../../workloads/docs/mapping_and_quality.md)。

<!-- model-fields:start -->

### [attention.py](attention.py)

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `execute_attention_plan(spec: AttentionSpec, inputs: AttentionInputs, plan: AttentionPlan, *, scratch_capacity_bytes: int, backing_capacity_bytes: int, max_macs: int=1000000, max_elements: int=1000000)` | Execute visible QK, stable scalar softmax and AV; policies control actual copies and intermediate persistence. |

### [linear.py](linear.py)

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `execute_plan(spec: LinearSpec, inputs: LinearInputs, plan: LinearPlan, capacity_bytes: int, *, max_macs: int=1000000)` | Execute local C residency/spill semantics with K-ordered scalar multiply/add, independently of the reference. |

### [training.py](training.py)

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `apply_sgd(spec: TrainingSpec, state: TrainingState, gradients: TrainingGradients, learning_rate: float)` | Apply gradients only to their exact source state; produce a fresh version without altering any caller buffer. |
| `execute_training(spec: TrainingSpec, state: TrainingState, inputs: TrainingInputs, learning_rate: float, tile: TileShape, strategy: str, *, scratch_capacity_bytes: int, backing_capacity_bytes: int, max_macs: int=1000000)` | Execute the fixed recipe and release backing leases at last use; retained host audit values do not model SRAM. |

<!-- model-fields:end -->

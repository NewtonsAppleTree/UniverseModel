# reference：线性算子的精确参考与质量判定

`reference_linear` 不导入 compiler/chipmodel。INT8 用 Python 整数精确点积；float64 将每个二进制输入转换成精确 Fraction，乘法和累加不舍入，最后一次转换回 float。它是数值 oracle，不模拟目标 MAC 的中间舍入、时延或能耗。

`compare_output` 的整数结果要求类型与值完全相同，忽略宽松容差；float64 要求有限值且 `abs(actual-reference) <= atol+rtol*abs(reference)`。结果包含是否通过、失败的平坦索引和最大绝对误差。容差 [输出数值]/[1] 与数值幅度是关键参数，max_macs 是宿主运行预算；比较运算自身溢出也拒绝。

顺序：校验实际输入 → 精确参考 → 外部执行结果 → 显式质量结果。失败质量与异常/运行失败分开；测试用 `1e16+1-1e16` 保留残差 1，检出顺序 binary64 累加的 0。矩形、MatVec 与数值边界验证见[测试](../../tests/workloads/test_linear.py)。无物理校准主张。

## 训练独立参考

`reference_training` 使用 Fraction 完成整个 Linear/ReLU/mean-MSE 链和解析反向，再对预测、loss、dW/dX、SGD 新权重各观察值最终舍入；不调用 compiler 或共享其更新函数。`compare_training` 对所有观察字段采用既有 atol/rtol，并检查源状态身份和版本。默认学习率由实验显式声明；max_macs 限制完整 step 的 GEMM 工作。

原生 float64 中间舍入与精确链可能不同，数值不合格是独立结果。ReLU exact 零点梯度为 0，不把折点有限差分作为唯一依据。矩形/mean 归一化/中心差分见[训练测试](../../tests/workloads/test_training.py)，可选 PyTorch autograd 另提供独立实现证据。

<!-- model-fields:start -->

### [linear.py](linear.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `LinearValidation` | `passed` | `bool` | 1（布尔） | True iff all values satisfy the declared comparison rule. |
| `LinearValidation` | `mismatched_indices` | `tuple[int, ...]` | element index | Flat C indices failing equality/tolerance [element index]. |
| `LinearValidation` | `max_absolute_error` | `int \| float` | output value | max(abs(actual-reference)) [output value]. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `reference_linear(spec: LinearSpec, inputs: LinearInputs, *, max_macs: int=1000000)` | Scalar dot products use exact arithmetic; binary64 reference rounds only the final exact sum. |
| `LinearValidation` | Output quality is an explicit result, separate from execution success and performance claims. |
| `compare_output(spec: LinearSpec, actual: tuple[int \| float, ...], reference: tuple[int \| float, ...], *, atol: float=1e-12, rtol: float=1e-12)` | INT64 requires exact values/types; floats require \|actual-reference\| <= atol+rtol*\|reference\|. |

### [training.py](training.py)

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `reference_training(spec: TrainingSpec, state: TrainingState, inputs: TrainingInputs, learning_rate: float, *, max_macs: int=1000000)` | Evaluate the whole mathematical chain exactly, then round observed values once; no mapped execution is reused. |
| `compare_training(actual: TrainingResult, reference: TrainingResult, *, atol: float=1e-12, rtol: float=1e-12)` | Compare all observations and state transitions, not just the final loss or one tensor. |

<!-- model-fields:end -->

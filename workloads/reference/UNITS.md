# reference：线性算子的精确参考与质量判定

`reference_linear` 不导入 compiler/chipmodel。INT8 用 Python 整数精确点积；float64 将每个二进制输入转换成精确 Fraction，乘法和累加不舍入，最后一次转换回 float。它是数值 oracle，不模拟目标 MAC 的中间舍入、时延或能耗。

`compare_output` 的整数结果要求类型与值完全相同，忽略宽松容差；float64 要求有限值且 `abs(actual-reference) <= atol+rtol*abs(reference)`。结果包含是否通过、失败的平坦索引和最大绝对误差。容差 [输出数值]/[1] 与数值幅度是关键参数，max_macs 是宿主运行预算；比较运算自身溢出也拒绝。

顺序：校验实际输入 → 精确参考 → 外部执行结果 → 显式质量结果。失败质量与异常/运行失败分开；测试用 `1e16+1-1e16` 保留残差 1，检出顺序 binary64 累加的 0。矩形、MatVec 与数值边界验证见[测试](../../tests/workloads/test_linear.py)。无物理校准主张。

## 训练独立参考

`reference_training` 使用 Fraction 完成整个 Linear/ReLU/mean-MSE 链和解析反向，再对预测、loss、dW/dX、SGD 新权重各观察值最终舍入；不调用 compiler 或共享其更新函数。`compare_training` 对所有观察字段采用既有 atol/rtol，并检查源状态身份和版本。默认学习率由实验显式声明；max_macs 限制完整 step 的 GEMM 工作。

原生 float64 中间舍入与精确链可能不同，数值不合格是独立结果。ReLU exact 零点梯度为 0，不把折点有限差分作为唯一依据。矩形/mean 归一化/中心差分见[训练测试](../../tests/workloads/test_training.py)，可选 PyTorch autograd 另提供独立实现证据。

## 通用整数MatVec参考

`reference_integer_matvec(vector, matrix, max_macs=...)`不依赖硬件，逐列使用Python整数精确点积。允许一般有符号整数，拒绝bool/浮点/错误shape；不执行量化或硬件溢出。max_macs是宿主上限。CIM实验独立应用输出格式后比较，证据见[测试](../../tests/workloads/test_integer_matvec.py)。

## Attention 与 stable softmax

`attention.py`先对QK/scale和行最大值差使用精确Fraction，再以显式Decimal上下文做exp/归一化/AV。precision_digits为32–256有效位、默认80，独立于调用方全局上下文；结果与概率分别最终舍入为binary64，非有限输出拒绝，微小观察值可下溢为零。内部高精度概率用于AV，保存概率不强制与舍入后AV重新运算相同。此参考不模拟硬件中间舍入，也不是实数精确证明。

`reference_softmax`独立处理一个非空有限行；`reference_attention`按显式因果位置/GQA共享计算并返回完整输入身份、O与概率。最敏感参数是logit范围、消去、precision_digits和宿主max_score_pairs/max_macs；完整shape由contracts维护。预算分别约束完整概率材料化与有效QK+AV工作，无目标时延/能耗。公式、下溢和精度边界见[指南](../docs/foundation_usage.md)，60组独立float算法/手算/复制等价与极值见[测试](../../tests/workloads/test_attention.py)。

## 数值校验与分类质量

概率端点与行和共用`PROBABILITY_TOLERANCE=1e-9`；行和用fsum，原始argmax与观测不变。log-loss使用`min(1,max(p_true,probability_floor))`避免端点舍入产生负loss，clipped_samples只统计低于下限的真类概率。容差内值不是自动数值正确，独立Attention比较仍使用自身atol/rtol。反例与记录边界见[收尾审计](../docs/completion_audit.md)。

Attention新增compare_attention，先校验完整输入身份，再对输出逐元素检查atol+rtol，溢出/非有限/shape错误拒绝。`classification.py`的classification_metrics报告accuracy、自然对数loss、显式floor/裁剪数、confusion及逐例预测，argmax并列取首类；概率端点偏离[0,1]与行和误差均不得超过1e-9。classification_gate使用Fraction计数比和参数十进制值检验绝对质量/同split下降，避免0.95/0.05浮点边界误判。它们没有物理计量；参数范围、单例手算、精确阈值及质量负对照见[W5指南](../docs/mapping_and_quality.md)。

<!-- model-fields:start -->

### [attention.py](attention.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `AttentionReference` | `input_identity` | `str` | 1（标识/枚举） | SHA256 of complete Attention spec and actual Q/K/V. |
| `AttentionReference` | `output` | `tuple[float, ...]` | B,Hq,Sq,Dv | Row-major [B,Hq,Sq,Dv], rounded reference output. |
| `AttentionReference` | `probabilities` | `tuple[float, ...]` | B,Hq,Sq,Skv | [B,Hq,Sq,Skv], exact zero for masked positions; rounded observations. |
| `AttentionReference` | `precision_digits` | `int` | digit | Decimal significant digits used for exp/normalization/weighted sums [digit]. |
| `AttentionValidation` | `passed` | `bool` | 1（布尔） | Every output satisfies abs(actual-reference)<=atol+rtol*abs(reference). |
| `AttentionValidation` | `max_absolute_error` | `float` | output value | Largest absolute output difference [output value]. |
| `AttentionValidation` | `mismatched_indices` | `tuple[int, ...]` | —（结构/对象） | Flat output indices outside tolerance. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `reference_softmax(logits: tuple[float, ...], *, precision_digits: int=80)` | Standalone stable softmax over one nonempty finite row; no implicit mask, temperature or target SFU precision. |
| `AttentionReference` | Retain reference intermediates and source identity; successful evaluation is not an AI task-quality verdict. |
| `AttentionValidation` | Numerical agreement is separate from execution success and downstream classification quality. |
| `compare_attention(spec: AttentionSpec, inputs: AttentionInputs, actual: tuple[float, ...], reference: AttentionReference, *, atol: float=1e-12, rtol: float=1e-12)` | Bind the numerical oracle to the exact task/data and validate all observed outputs with explicit tolerances. |
| `reference_attention(spec: AttentionSpec, inputs: AttentionInputs, *, precision_digits: int=80, max_score_pairs: int=100000, max_macs: int=1000000)` | Reference uses valid pairs only, exact rational QK/scale and Decimal exp/AV; full probability storage is host-bounded. |

### [classification.py](classification.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `ClassificationMetrics` | `samples` | `int` | sample | Number of evaluated held-out samples [sample]. |
| `ClassificationMetrics` | `correct` | `int` | sample | Correct argmax labels [sample]. |
| `ClassificationMetrics` | `accuracy` | `float` | 1 | correct/samples [1]. |
| `ClassificationMetrics` | `mean_log_loss` | `float` | nat/sample | -mean(log(min(1,max(p_true,probability_floor)))) [nat/sample]; upper clamp removes endpoint roundoff. |
| `ClassificationMetrics` | `probability_floor` | `float` | 1 | Explicit log-loss clipping threshold [1], not a prediction modification. |
| `ClassificationMetrics` | `clipped_samples` | `int` | sample | True-class probabilities clipped for log reporting [sample]. |
| `ClassificationMetrics` | `confusion` | `tuple[tuple[int, ...], ...]` | true,predicted | [true,predicted] sample counts. |
| `ClassificationMetrics` | `predictions` | `tuple[int, ...]` | —（结构/对象） | Argmax output class for each input sample. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `ClassificationMetrics` | Confusion rows are true labels and columns predicted labels; ties select the first declared class. |
| `classification_metrics(probabilities: tuple[float, ...], labels: tuple[int, ...], classes: int, *, probability_floor: float=1e-15)` | Allow endpoint/row-sum roundoff within PROBABILITY_TOLERANCE; raw argmax is unchanged and only log reporting clamps. |
| `classification_gate(actual: ClassificationMetrics, baseline: ClassificationMetrics, *, minimum_accuracy: float, maximum_accuracy_drop: float)` | Compare exact sample-count ratios against decimal threshold values, avoiding binary64 boundary artifacts. |

### [integer_matvec.py](integer_matvec.py)

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `reference_integer_matvec(vector: tuple[int, ...], matrix: tuple[tuple[int, ...], ...], *, max_macs: int=1000000)` | 独立检查输入并按列做精确乘加；不量化、不截断，也不应用硬件输出溢出策略。 |

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

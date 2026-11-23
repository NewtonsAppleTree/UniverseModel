# Linear 训练 step、短链与 PyTorch 功能对照

本批在[线性映射实验](linear_mapping.md)上增加真实训练依赖：前向产生的激活要保留到反向，dW/dX 使用不同收缩轴，更新只能使用相应旧权重版本的梯度。目的在于验证工作负载、编译、硬件分析和实验记录的组合能力；实施与验收见[计划](../../docs/development/training_step_plan.md)。

## 范围与数值语义

支持 1–16 层、无 bias、正整数 batch/widths 的 float64 Linear 链，隐层为 ReLU 或 identity。W 存为 row-major [in,out]；激活为 [batch,width]。最后一层无 ReLU。每步使用完整 batch，无 microbatch 累积、momentum、weight decay、mixed precision、dropout 或分布式通信。

给定 A_l、W_l，Z_(l+1)=A_l W_l；隐层按配置取 ReLU(Z) 或 Z。输出 Y 与目标 T 的损失是 `L=Σ(Y−T)²/(B*d_final)`，按所有输出元素取均值。dY=2(Y−T)/(B*d_final)，dW_l=A_lᵀ dZ_(l+1)，dA_l=dZ_(l+1) W_lᵀ，ReLU 在正激活处传递梯度、负值与零处置零。SGD 为 `W_next=W−lr*dW`。

原生执行采用分开的 scalar multiply/add 和显式顺序 binary64 损失求和。默认参考用 Fraction 完成整条数学链、反向与更新，各观察值最终只舍入一次；数值容差由实验声明。可选 PyTorch 用原生 Linear/ReLU/MSE autograd 与 SGD，允许底层求和/更新顺序差异。两者均检查预测、loss、所有 dW/dX、新权重及版本，不只检查 loss。

## 独立调用与状态所有权

公共值见 [training.py](../../contracts/workload/training.py)，输入生成/完整工作量在 [workloads/graphs](../../workloads/graphs/UNITS.md)，精确参考在 [workloads/reference](../../workloads/reference/UNITS.md)，固定阶段/生命周期在 [compiler/sched](../../compiler/src/sched/UNITS.md)，功能执行在 [compiler/interpret](../../compiler/src/interpret/UNITS.md)。

```python
from contracts.workload.training import TrainingSpec, TrainingState, TrainingInputs
from contracts.plan.linear import TileShape
from compiler.src.interpret.training import execute_training, apply_sgd

spec = TrainingSpec(batch_size=1, widths=(2, 1))
state = TrainingState(version=0, weights=((1.0, 2.0),))
data = TrainingInputs(x=(3.0, 4.0), target=(1.0,))
result, plan = execute_training(
    spec, state, data, 0.1, TileShape(m=1, n=1, k=1), "output_stationary",
    scratch_capacity_bytes=24, backing_capacity_bytes=88,
)
assert result.prediction == (11.0,) and result.loss == 100.0
assert result.gradients.weights == ((60.0, 80.0),)
assert result.gradients.x == (20.0, 40.0)
assert result.next_state.weights == ((-5.0, -6.0),)
assert apply_sgd(spec, state, result.gradients, 0.1) == result.next_state
```

state/data/gradients 的嵌套数组均冻结为有限 float 元组。梯度绑定源 state 的内容哈希和版本，独立 `apply_sgd` 拒绝旧版本或相同版本但不同参数的梯度。更新返回 version+1，不修改旧状态；lr=0 也推进逻辑步。重复训练传入 result.next_state，有限候选比较则每个候选重置到相同旧状态。

本批提供固定训练配方的独立 step，不提供通用 autograd 引擎或任意训练图执行。单个 GEMM、计划/生命周期查询、精确参考与 SGD 可分别调用。

## 容量、工作和计量边界

阶段依次为所有前向 → mean MSE → 逐层反向 → 所有 SGD。反向 Aᵀ/Wᵀ 实际材料化，不能作为零成本视图；GEMM 沿用首批 tail-aware tile、C 驻留/回写和逐行外部请求。

两类容量独立检查：

- **backing 存储：** x/target、旧权重、激活、转置、梯度与新权重的命名稠密张量。生产到最后使用采用 inclusive 区间，某操作的输入和输出同时占用。预测、loss、dX/dW、新权重保留到 step 边界；其他对象释放 lease。峰值为同一阶段活跃字节之和的最大值。
- **GEMM scratch：** 每个收缩复用现有 A/B/C 三 arena 规划，容量取独立预算，不与 backing 混用。辅助算子的寄存器/本地 workspace 尚未建模，Python 对象和审计快照不等于目标存储。

因此 backing_peak 是本配方的逻辑分配可行性，不是实测 GPU peak memory。没有 cache、双缓冲、异步释放、框架 allocator、重计算、分片或跨层融合优化。通用性来自可独立验证和替换边界，不能把固定配方冒称为全图编译器。

令 P=Σdin·dout，D=B*d_final，H=B*Σhidden_width。三个 GEMM 类别共 3BP MAC；它只覆盖收缩工作。mean MSE 另计 4D+2 次 scalar add/sub/mul/div，SGD 另计 2P 次；ReLU 前向/反向合计 2H 次比较和 2H 次选择，identity 为零。显式转置 B·Σ各层输入宽+P 个元素。算术/比较/选择/复制分开，不统一冒称 FLOP。

GEMM 的 backing↔scratch payload 按实际行请求计数；辅助操作采用每输入读取一次、每输出写一次的逻辑 payload 边界，转置读和写都计。两者不重复叠加全张量传输。辅助动作尚无地址级事务、服务率或物理成本，因此 `gemm_resource_lower_bound` 只覆盖 GEMM 子集，**step_time 与 step_energy 均为明确未知**。不能据此计算训练加速比、MFU、samples/s 或能效。

## 配置、运行与保存

默认 [training_step.json](../../config/experiments/training_step.json) 使用 B=2、widths=(3,4,2)、ReLU、lr=0.125、seed=7；128 B GEMM scratch 与 4096 B backing。纯标准库路径：

```text
python -m example.training_demo
python -m example.training_demo --set workload.widths=[2,1]
python -m example.training_demo --output .build/training-study --source-revision YOUR_SOURCE_SNAPSHOT
python -m example.training_demo --read .build/training-study
```

保存目录必须全新；每个候选有 immutable run.json/manifest。输入权重/数据、有效配置、生成器版本/seed、参考环境、完整计划/生命周期、结果和失败原因进入记录。回读不执行训练、不导入 PyTorch，也不信任派生 summary.json。源码版本默认 unrecorded；正式实验仍须另存准确源码/未提交补丁及环境。

至少一个候选数值通过且没有已完成候选数值不合格时，CLI 退出 0；不可行候选保留，全失败或任一数值不合格退出 1。此规则适用于探索候选，验收须查看每行状态。

## 固定版本 PyTorch 对照

可选依赖在[独立清单](../../tools/requirements-training-torch.txt)。Windows PowerShell：

```text
python -m venv .build/torch-crosscheck
.build/torch-crosscheck/Scripts/python.exe -m pip install -r tools/requirements-training-torch.txt
.build/torch-crosscheck/Scripts/python.exe -m example.training_demo --torch-reference --output .build/training-pytorch
.build/torch-crosscheck/Scripts/python.exe -m unittest discover -s tests/integration -p "test_training_experiment.py" -v
```

Linux 将环境解释器路径替换为 `.build/torch-crosscheck/bin/python`。默认包和公共契约不增加强制 torch 依赖。PyTorch 参考使用 [v2.5.1 functional](https://github.com/pytorch/pytorch/blob/v2.5.1/torch/nn/functional.py) 与 [SGD](https://github.com/pytorch/pytorch/blob/v2.5.1/torch/optim/sgd.py) API；运行记录保存实际安装版本/git、Python、OS、threads、CPU/float64 条件。

2026-11-23 本地 Python 3.12.4、PyTorch 2.5.1+cpu 已运行。独立 autograd 对照覆盖单层、两层矩形 ReLU、两层 identity、三层 ReLU，均比较两种映射；另有默认配置的完整候选记录对照。此证据验证数值语义，未测量或校准目标训练性能，也不是收敛/任务质量实验。

[验证快照](../../docs/reference/data/training_validation_2026-11-23.json)记录实际数据/配置、工具依赖、源码哈希和 8 个候选运行的校验/指标。原始 bundle 为 `.build/training-exact-20261123`、`.build/training-pytorch-20261123`；可在未安装 PyTorch 的默认环境用 `--read` 校验回读。当前源码为工作区版本，正式复现仍须保留源码或补丁。

## 默认结果与验证证据

所有可行候选的 loss=0.18958117067813873，新状态 version=1，预测/全部梯度/更新均通过精确参考和 PyTorch 对照。工作量 120 MAC、58 次辅助算术、16 次比较、16 次选择、34 个转置元素；backing 峰值 568 B，辅助逻辑 payload 为 1448 B。

| 候选 | GEMM scratch 峰值 | GEMM payload | GEMM 子集资源下界 | 状态 |
| --- | --- | --- | --- | --- |
| resident_2x2x2 | 96 B | 1392 B | 532 ns | 数值通过 |
| spill_2x2x2 | 96 B | 1680 B | 644 ns | 数值通过 |
| resident_1x2x2 | 64 B | 1840 B | 704 ns | 数值通过 |
| infeasible_full | 首个 GEMM 需 208 B | 未执行 | 未知 | 超过 128 B scratch |

辅助 payload 可分解为 ReLU 128 B、MSE/梯度 104 B、四次转置 544 B、ReLU 反向 192 B、两个 SGD 更新 480 B，合计 1448 B。不能只统计前向输入/输出，或将转置与更新当成免费。

验证文件：[语义/归一化/有限差分](../../tests/workloads/test_training.py)、[编译/生命周期/旧梯度反例](../../compiler/tests/test_training.py)、[实验/产物/可选 PyTorch](../../tests/integration/test_training_experiment.py)。后续优先在这一训练配方上比较保存/重计算或跨层驻留机制，再将 GEMM 共同案例与外部架构工具的布局、数据流和服务假设对齐，补充性能/成本证据。

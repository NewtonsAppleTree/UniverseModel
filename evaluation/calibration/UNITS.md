# calibration：可选外部训练功能对照

`pytorch_training` 延迟导入 PyTorch，在 CPU/float64 上使用 `functional.linear`、ReLU、mean MSE 的 autograd 与 `optim.SGD`。本项目 W 的布局为 [in,out]，传给 PyTorch Linear 时显式转置成 [out,in]。不复用手写反向公式。输入是公共训练 spec/state/data 与学习率，输出是相同 TrainingResult 边界，调用者状态不修改。

`pytorch_environment` 记录实际 torch 版本/git、Python、平台、线程数、device/dtype；runner 把它纳入有效配置身份。默认标准库路径不导入第三方包。可选环境及命令见[训练指南](../docs/training_step.md)和[依赖清单](../../tools/requirements-training-torch.txt)。

这是功能交叉验证，位于 calibration 目录但没有校准目标性能、面积或能耗。关键参数是浮点舍入/容差、形状、激活零点、loss reduction、SGD 设置以及工具版本。无独立物理量；外部框架可能采用不同求和或更新运算顺序，因此按显式容差比较。所有预测、loss、dW/dX 和新权重参与比较；运行证据见[集成测试](../../tests/integration/test_training_experiment.py)。

<!-- model-fields:start -->

### [pytorch_training.py](pytorch_training.py)

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `pytorch_environment()` | Record the actual external implementation/environment, with no target hardware timing claim. |
| `pytorch_training(spec: TrainingSpec, state: TrainingState, inputs: TrainingInputs, learning_rate: float)` | Use framework Linear, ReLU, MSE autograd and SGD; no hand-written backward equations are reused. |

<!-- model-fields:end -->

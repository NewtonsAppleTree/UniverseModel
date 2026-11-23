# 验证归属

本目录按 contracts、configuration、costmodel、chipmodel、systemmodel、clustermodel、workloads、runtime、simulator、artifacts、evaluation、ui 与 integration 划分。compiler 的阶段验证保留在 compiler/tests。

本目录规定测试归属，已完成的验证与可运行命令见[实现状态](../docs/STATUS.md)。功能与时序实现时，优先增加独立参考、容量/端口/因果反例、可手算争用与完整复现案例，避免仅重复代码行为。

完整验收标准见[验证规范](../docs/architecture/validation.md)。

ADC 的独立阈值参考在 [test_adc.py](chipmodel/test_adc.py)；各子模块及系统关系测试在 [test_models.py](chipmodel/test_models.py)，覆盖工作量、GPU 驻留、CIM 功能链、DDR/突发、容量/布局、热模型、资源包络与计量范围。在仓库根目录用 Python 3.10+ 标准库执行：

```text
python -m unittest discover -s tests/chipmodel -p "test_*.py" -v
```

结构检查另行运行 `python tools/check_structure.py`；它不代替数值或时序验证。

代码/参数文档规则另行运行 `python tools/check_model_rules.py`。更新字段后可用 `--write-docs` 刷新各目录 UNITS.md 的生成区；默认只检查，不修改文件。

通用工程边界在 [test_framework.py](integration/test_framework.py) 验证：严格配置/覆盖、冻结嵌套值、规范化哈希、独立 ADC/DMA 接入、重复调用隔离、失败/未知指标、模式/单位、保存往返与损坏/不完整产物，以及依赖/注释检查的非法样例。单独运行：

```text
python -m unittest discover -s tests/integration -p "test_*.py" -v
```

它验证工程接口，不代替硬件的数值或时序校核。结构检查还核对主模块 Python import，允许依赖以 modules.json 为单一维护定义。

线性实验新增三层验证：[workloads](workloads/test_linear.py) 提供手算/精确参考、格式与身份边界；[compiler](../compiler/tests/test_linear_mapping.py) 检查尾块、覆盖、归约生命周期和容量/流量；[integration](integration/test_linear_experiment.py) 验证 MAC/DMA 时钟、未知能耗、数值失败、敏感性、记录和 CLI 回读。后者随现有 integration 命令运行，前两组单独运行：

```text
python -m unittest discover -s tests/workloads -p "test_*.py" -v
python -m unittest discover -s compiler/tests -p "test_*.py" -v
```

本轮 27 项新增测试验证声明语义；尚未提供外部工具性能校准或训练执行证据。

2026-11-23 训练批次另新增 23 项测试：[workloads](workloads/test_training.py) 7 项手算/归一化/有限差分/边界，[compiler](../compiler/tests/test_training.py) 8 项反向轴、ReLU、状态和生命周期/容量反例，[integration](integration/test_training_experiment.py) 6 项完整工作/记录/多形状/质量检查，以及 2 项可选 PyTorch autograd/SGD。它们使用上面的四组 discover 命令；默认共 108 项通过、2 项跳过，固定 PyTorch 环境额外通过这 2 项。外部 CPU 数值对照不是目标性能校准。

```text
.build/torch-crosscheck/Scripts/python.exe -m unittest discover -s tests/integration -p "test_training_experiment.py" -v
```

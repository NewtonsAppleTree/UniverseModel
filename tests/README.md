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

# 示例

[`chipmodel_demo.py`](chipmodel_demo.py) 展示独立 DDR 查询，以及 GEMM 的输入/计算/输出工作量、DMA/缓冲配置、资源归属和部分系统时间下界。仓库根目录运行 `python -m example.chipmodel_demo`。它打印完整假设与未覆盖项，系统关系见 [chipmodel 设计](../chipmodel/docs/system_model_design.md)。

[`adc_demo.py`](adc_demo.py) 是独立 ADC 的可运行示例：显式参数、输入电压、输出码与越限标志，以及 4/8 lanes 的理想批次时间。它只导入 chipmodel，使用标准库；L/II 和时钟为示例假设。完整参数与边界见 [ADC 说明](../chipmodel/docs/adc_model.md)。

在仓库根目录运行：

```text
python -m example.adc_demo
```

`specs` 放可检查的结构/规划示例；其中 JSON 不是可执行 HardwareSpec 或 BenchSpec。`workflows` 预留端到端示例。

先读 [specs 说明](specs/README.md)。未来首个工作流应覆盖输入、配置、计划、参考比对、手算时序与运行清单，达到[阶段 B/C](../docs/architecture/validation.md)后才标为可执行。

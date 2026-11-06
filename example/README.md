# 示例

[`universal_demo.py`](universal_demo.py) 使用同一工程接口独立调用 ADC 或 DMA：JSON → 冻结参数 → 注入函数 → 带单位记录 → 可选本地保存。配置字段仍采用原模型的专业类型；新增类只描述两个示例的参数/输入边界。

```text
python -m example.universal_demo --case adc
python -m example.universal_demo --case adc --set configuration.adc.lane_count=8
python -m example.universal_demo --case dma --set inputs.payload_bytes=64
python -m example.universal_demo --case dma --output data/runs/dma-demo
```

默认文件为 [ADC](../config/experiments/universal_adc.json) / [DMA](../config/experiments/universal_dma.json)。`--config` 替换文件；`--set` 使用 dotted path 和 JSON 值，未知/派生字段失败；`--source-revision` 显式记录代码来源，默认 unrecorded。输出目录必须是新的，内容可由 `artifacts.storage.local.read_run` 校验读取。

ADC 示例独立处理 5 个已采样电压，4 lanes 的批次为 4 cycles，8 lanes 为 2 cycles；DMA 示例独立搬运 72 B，为 10 cycles。这里的 72 B 是**一条** DMA 请求，与未来 MatVec 的输入/输出两条请求不同。未知能量记录为 null；时钟/L/II 为软件假设。框架与全部模块接入设计见 [ENGINEERING_FRAMEWORK.md](../ENGINEERING_FRAMEWORK.md)。

[`chipmodel_demo.py`](chipmodel_demo.py) 展示独立 DDR 查询，以及 GEMM 的输入/计算/输出工作量、DMA/缓冲配置、资源归属和部分系统时间下界。仓库根目录运行 `python -m example.chipmodel_demo`。它打印完整假设与未覆盖项，系统关系见 [chipmodel 设计](../chipmodel/docs/system_model_design.md)。

[`adc_demo.py`](adc_demo.py) 是独立 ADC 的可运行示例：显式参数、输入电压、输出码与越限标志，以及 4/8 lanes 的理想批次时间。它只导入 chipmodel，使用标准库；L/II 和时钟为示例假设。完整参数与边界见 [ADC 说明](../chipmodel/docs/adc_model.md)。

在仓库根目录运行：

```text
python -m example.adc_demo
```

`specs` 放可检查的结构/规划示例；其中 JSON 不是可执行 HardwareSpec 或 BenchSpec。`workflows` 预留端到端示例。

先读 [specs 说明](specs/README.md)。完整硬件工作流仍需覆盖计划、参考比对与手算时序，达到[阶段 B/C](../docs/architecture/validation.md)后才标为可执行。

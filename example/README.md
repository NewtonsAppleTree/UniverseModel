# 示例

CH1–CH10六组默认夹具统一运行/回读：`python tools/validate_chipmodel.py --output .build/chipmodel-acceptance`，然后以`--read`回读同一目录。固定案例名单、源码身份和证据范围见[完成报告](../chipmodel/docs/completion.md)。

新增六节点[leaf-spine配置](../config/experiments/cluster_leaf_spine.json)，可用`--config config/experiments/cluster_leaf_spine.json --overview`查看安装资源/方向可达性与需求矩阵。停用来源和失败回读见[横向指南](../clustermodel/docs/breadth_usage.md)。

[`cluster_demo.py`](cluster_demo.py)运行四节点同预算放置比较，输出共享通信账本与条件下界，可保存完整候选（含失败）并校验回读；见[基础指南](../clustermodel/docs/foundation_usage.md)。

[`network_demo.py`](network_demo.py)独立分析C1直连网络中的一个方向，默认1 MB、200 Gbit/s、2 μs固定延迟，孤立链路结果42 μs。使用显式[网络配置](../config/experiments/network_link.json)，保留未知能量和来源；用法及计量边界见[C1指南](../clustermodel/docs/c1_usage.md)。

```text
python -m example.network_demo
python -m example.network_demo --output .build/network-c1
python -m example.network_demo --read .build/network-c1
```

[`training_demo.py`](training_demo.py) 运行 Linear/ReLU 短链的前向、mean MSE、全部反向及 SGD，比较相同旧状态的有限映射，保留容量失败。`--torch-reference` 在可选 CPU PyTorch 环境做独立 autograd/SGD 校验；回读不需要该环境。命令和数值/存储/时间边界见[训练指南](../evaluation/docs/training_step.md)。

```text
python -m example.training_demo
python -m example.training_demo --output .build/training-study
python -m example.training_demo --read .build/training-study
```

[`linear_demo.py`](linear_demo.py) 比较同一 GEMM 的输出驻留/部分和回写方案，贯通 workload、显式映射、容量/流量、功能参考、MAC/DMA 分析与产物。默认三项数值校验通过，一项因容量不足留下失败记录；348/588/460 ns 是条件化资源下界。语义、手算、独立调用和限制见[线性实验指南](../evaluation/docs/linear_mapping.md)。

```text
python -m example.linear_demo
python -m example.linear_demo --set hardware.scratch_capacity_bytes=256
python -m example.linear_demo --output .build/linear-study
python -m example.linear_demo --read .build/linear-study
```

输出目录必须全新，回读从校验过的 run bundle 重建汇总。至少一项数值通过且无数值不合格的已完成候选时退出 0；不可行候选仍保留。默认源码来源为 unrecorded，正式实验用 `--source-revision` 标明实际源码快照。

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

## 外存与缓存

[`memory_demo.py`](memory_demo.py)运行CH7的三组21个有限案例，比较DRAM行条件/共享总线、缓存LRU回填/脏写回和NAND页缓冲/外部data/OOB输出。运行 `python -m example.memory_demo --output .build/memory-study`，再用 `--read .build/memory-study` 回读。完整profile、访问、初态、源码身份与失败/未知均保存；条件分析界不等于执行时间。见[外存与缓存指南](../chipmodel/docs/memory_access.md)。

## Tile/Die/Package组合

[`physical_demo.py`](physical_demo.py)运行CH9四组20案例，保留真实来源点、未知成本、几何/热必要条件和预期失败。`python -m example.physical_demo --output .build/physical-study` 保存，`--read .build/physical-study` 回读；运行无需联网，见[物理证据指南](../chipmodel/docs/physical_evidence.md)。

[`assembly_demo.py`](assembly_demo.py)运行CH8五组16个案例，比较固定工作的位置、共享端口/时钟、完整job顺序和D2D方向预算。`python -m example.assembly_demo --output .build/assembly-study` 保存，`--read .build/assembly-study` 回读。完整工作/资源/预留/来源及失败保留，未知执行/能量不补零；见[组合指南](../chipmodel/docs/assembly.md)。

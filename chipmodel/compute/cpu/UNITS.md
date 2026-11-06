# cpu：微操作供给与执行能力

Unit 为 CpuCore，输入 CpuCoreParams 与 ClockDomain，输出所选 μop 类别的稳态能力上界。取指能力须先依据 workload 的 instruction→μop 展开关系归一；这里不执行 ISA。

关键关系是 `r=min(fetch,decode,issue,retire,execution_lanes/execution_ii)`，再乘 f 得 μop/s。最关心各阶段瓶颈和 μop 类型；执行 lane 只统计能执行该类型的端口。增加不兼容执行端口不会提高此操作的能力。

ROB、rename、issue queue、分支预测、LSU、load/store queue 尚未建模。以后分别引入 entries [entry]、恢复周期 [cycle]、在途访问 [request] 与依赖/访存轨迹；不能用一个固定 IPC 替代这些机制。缓存和 TLB 归 memory。

先构造参数和时钟，再查询 `peak_uops_per_cycle/peak_uops_per_s`。没有程序完成时间、状态更新或异常语义。参考 gem5 的参数分层做法，峰值公式的验收采用最窄阶段反例。

<!-- model-fields:start -->

### [core.py](core.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `CpuCoreParams` | `fetch_uops_per_cycle` | `int` | μop/cycle | 已按指令展开比例归一的取指供给 [μop/cycle]。 |
| `CpuCoreParams` | `decode_uops_per_cycle` | `int` | μop/cycle | 解码带宽 [μop/cycle]。 |
| `CpuCoreParams` | `issue_uops_per_cycle` | `int` | μop/cycle | 最大总发射宽度 [μop/cycle]。 |
| `CpuCoreParams` | `retire_uops_per_cycle` | `int` | μop/cycle | 提交宽度 [μop/cycle]；不等同于 ISA IPC。 |
| `CpuCoreParams` | `execution_lanes` | `int` | lane | 可执行所选 μop 类型的等价端口数 [lane]。 |
| `CpuCoreParams` | `execution_ii_cycles` | `int` | cycle | 每执行 lane 的发起间隔 II [cycle]。 |
| `CpuCore` | `params` | `CpuCoreParams` | —（结构/对象） | 冻结的阶段能力参数。 |
| `CpuCore` | `clock` | `ClockDomain` | —（结构/对象） | Core 固定时钟域。 |
| `CpuCore` | `peak_uops_per_cycle` | `float` | μop/cycle | 只读派生属性；各阶段速率的最小值 r=min(fetch,decode,issue,retire,lanes/II) [μop/cycle]。 |
| `CpuCore` | `peak_uops_per_s` | `float` | μop/s | 只读派生属性；r*f [μop/s]；依赖、分支、端口混合与供数均可能进一步降低实测速率。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `CpuCoreParams` | 描述独立、同类 μop 的供给/发射/执行/提交能力，最窄阶段限制稳态吞吐。 |
| `CpuCore` | CPU 峰值计算只表达 min(stage capacities)，不输出无依据的程序运行时间。 |
| `CpuCore.peak_uops_per_cycle` | 各阶段速率的最小值 r=min(fetch,decode,issue,retire,lanes/II) [μop/cycle]。 |
| `CpuCore.peak_uops_per_s` | r*f [μop/s]；依赖、分支、端口混合与供数均可能进一步降低实测速率。 |

<!-- model-fields:end -->

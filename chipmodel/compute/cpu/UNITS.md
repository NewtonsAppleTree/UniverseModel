# cpu：微操作供给与执行能力

Unit 为 CpuCore，输入 CpuCoreParams 与 ClockDomain，输出所选 μop 类别的稳态能力上界。取指能力须先依据 workload 的 instruction→μop 展开关系归一；这里不执行 ISA。

关键关系是 `r=min(fetch,decode,issue,retire,execution_lanes/execution_ii)`，再乘 f 得 μop/s。最关心各阶段瓶颈和 μop 类型；执行 lane 只统计能执行该类型的端口。增加不兼容执行端口不会提高此操作的能力。

ROB、rename、issue queue、分支预测、LSU、load/store queue 尚未建模。以后分别引入 entries [entry]、恢复周期 [cycle]、在途访问 [request] 与依赖/访存轨迹；不能用一个固定 IPC 替代这些机制。缓存和 TLB 归 memory。

先构造参数和时钟，再查询 `peak_uops_per_cycle/peak_uops_per_s`。没有程序完成时间、状态更新或异常语义。参考 gem5 的参数分层做法，峰值公式的验收采用最窄阶段反例。

CH6新增`CpuWork`和`analyze_cpu`：必须显式匹配所选uop_class，返回全部阶段速率、精确并列瓶颈以及有限W的各阶段发起跨度`max(ceil(W/P)-1,0)*II`。每阶段假设cycle0有P槽，各跨度取max，只是忽略延迟/依赖的必要条件；单项跨度0不表示执行零耗时。`execution_time_s=None`保留未知。默认身份unspecified仅可查询历史峰值，任务分析拒绝；profile_source记录来源。验证含60组逐cycle枚举与大整数并列边界，见[CH6指南](../../docs/compute_capabilities.md)。

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
| `CpuCore` | `uop_class` | `str` | 1（标识/枚举） | 此组等价端口支持的同类μop语义身份；不是ISA指令名。 |
| `CpuCore` | `profile_source` | `str` | 1（标识/枚举） | 阶段能力的假设/特征化来源；未记录不等于已校准。 |
| `CpuCore` | `peak_uops_per_cycle` | `float` | μop/cycle | 只读派生属性；各阶段速率的最小值 r=min(fetch,decode,issue,retire,lanes/II) [μop/cycle]。 |
| `CpuCore` | `peak_uops_per_s` | `float` | μop/s | 只读派生属性；r*f [μop/s]；依赖、分支、端口混合与供数均可能进一步降低实测速率。 |
| `CpuWork` | `uop_class` | `str` | 1（标识/枚举） | 必须与所选CPU能力的操作语义身份相同。 |
| `CpuWork` | `executed_uops` | `int` | uop | 包括显式额外工作在内的μop数 [uop]，可为0。 |
| `CpuCapacity` | `stage_rates_uops_per_cycle` | `tuple[tuple[str, float], ...]` | uop/cycle | 每阶段P/II [uop/cycle]。 |
| `CpuCapacity` | `peak_uops_per_cycle` | `float` | uop/cycle | min(各阶段速率) [uop/cycle]。 |
| `CpuCapacity` | `peak_uops_per_s` | `float` | uop/s | 最窄阶段速率*f [uop/s]。 |
| `CpuCapacity` | `bottlenecks` | `tuple[str, ...]` | 1（标识/枚举） | 精确有理速率相等的全部最窄阶段，与工作数量无关。 |
| `CpuCapacity` | `executed_uops` | `int` | uop | 本次同类实际工作 [uop]。 |
| `CpuCapacity` | `stage_issue_spans_cycles` | `tuple[tuple[str, int], ...]` | cycle | 每阶段(max(ceil(W/P)-1,0))*II [cycle]。 |
| `CpuCapacity` | `issue_span_lower_bound_cycles` | `int` | cycle | 各阶段跨度取max，不包含阶段延迟/依赖 [cycle]。 |
| `CpuCapacity` | `issue_span_lower_bound_s` | `float` | s | 跨度下界/f [s]；不是程序完成时间。 |
| `CpuCapacity` | `span_bottlenecks` | `tuple[str, ...]` | 1（标识/枚举） | 本批非零跨度达到最大值的阶段，可能与稳态瓶颈不同。 |
| `CpuCapacity` | `execution_time_s` | `None` | s | 程序执行时间 [s]，缺少指令/依赖/缓存/阶段延迟。 |
| `CpuCapacity` | `unknown_reason` | `str` | 1（标识/枚举） | 时间证据缺口，不把吞吐上界冒充IPC或执行性能。 |
| `CpuCapacity` | `profile_source` | `str` | 1（标识/枚举） | 当前能力参数来源。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `CpuCoreParams` | 描述独立、同类 μop 的供给/发射/执行/提交能力，最窄阶段限制稳态吞吐。 |
| `CpuCore` | CPU 峰值计算只表达 min(stage capacities)，不输出无依据的程序运行时间。 |
| `CpuCore.peak_uops_per_cycle` | 各阶段速率的最小值 r=min(fetch,decode,issue,retire,lanes/II) [μop/cycle]。 |
| `CpuCore.peak_uops_per_s` | r*f [μop/s]；依赖、分支、端口混合与供数均可能进一步降低实测速率。 |
| `CpuWork` | 映射方提供一种同类μop的实际工作量；不从宏指令数猜测展开比例。 |
| `CpuCapacity` | 稳态瓶颈与有限工作发起跨度分别报告，未建模的程序时间保持未知。 |
| `analyze_cpu(core: CpuCore, work: CpuWork)` | 假设每阶段cycle0可使用P个槽；最后一次发起至少在(ceil(W/P)-1)*II，无隐含启动延迟。 |

<!-- model-fields:end -->

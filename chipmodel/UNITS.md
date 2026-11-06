# chipmodel：系统资源与公共分析量

从[系统级设计](docs/system_model_design.md)和[第一性原理](../docs/architecture/first_principles.md)进入。模型先回答功能、数据位置、资源约束、因果与物理条件，再定义参数。全仓库规则见 [AGENTS.md](../AGENTS.md)，本模块规则见 [AGENTS.md](AGENTS.md)。

设计时先用[顶层参数清单](../ARCHITECTURE_PARAMETERS.md)筛选相关物理量和关系；本页及子目录的生成表维护实际代码字段与接口，两者不重复维护配置定义。

| 子模块 | Unit 与系统责任 | 最关键的参数/边界 |
| --- | --- | --- |
| [compute](compute/UNITS.md) | CPU/GPU/NPU/CIM 的能力、数值和动作量 | 操作语义、工作量、精度、并行度、供数条件 |
| [memory](memory/UNITS.md) | SRAM/buffer/cache/DRAM/NAND 的容量与访问边界 | 逻辑/物理容量、bank/端口、访问粒度、行/页时序 |
| [control](control/UNITS.md) | DMA 服务与 TMA 地址生成 | 描述符范围、stride、burst、启动开销 |
| [interconnect](interconnect/UNITS.md) | NoC 与 D2D 的显式数据路径 | 协议开销、有效数据/线路速率、hop、粒度 |
| [composition](composition/UNITS.md) | 归属、连接、计量范围与任务时间下界 | 唯一资源身份、依赖、工作量与供给包络 |
| [packaging](packaging/UNITS.md) | 几何约束与热能量平衡 | 位置、面积、热阻/热容、温度、功率来源 |
| [registry](registry/UNITS.md) | 可选的显式软件构造入口 | 模型身份、参数校验、实例隔离；无物理计量 |
| [docs](docs/UNITS.md) | 规则、模型说明、验证与维护来源 | 代码字段表自动更新；设计与实现状态分开 |

## 公共量与使用顺序

`common.py` 只提供校验、ClockDomain 和 PipelineParams/Estimate。固定时钟先构造一次，再由需要的局部模型引用；没有全局 simulator、隐藏时钟或注册状态。`estimate_pipeline` 中一个 item 的含义由调用模块明确，可以是 MAC、转换或已定义的执行原语，不能在系统汇总中混算。

设计输入 → 类型/范围/单位校验 → 纯公式或功能计算 → 带单位的结果 → 按需要组合。`L+(ceil(W/P)-1)II` 假设等价 lane、输入就绪、在途容量充分、无输出背压。它支持 L≠II，但不代替缓存、路由、依赖或 DDR 命令调度。

最关心的是实际工作量 W、资源并行度 P、latency L、II、时钟 f 的区别。修改 P 可能改变供数和物理条件；提高 f 不证明电路可实现；峰值不能当成端到端吞吐。训练/推理的算子、KV cache 和并行策略由上层映射成这些工作量与路径。

## 参数与接口（来自代码）

<!-- model-fields:start -->

### [common.py](common.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `ClockDomain` | `domain_id` | `str` | 1（标识/枚举） | Clock-domain identity；无量纲标识。 |
| `ClockDomain` | `frequency_hz` | `float` | Hz | 固定时钟频率 f [Hz]。 |
| `ClockDomain` | `period_s` | `float` | s | 只读派生属性；时钟周期 Tclk=1/f [s]。 |
| `PipelineParams` | `lane_count` | `int` | lane | 等价并行服务通道 P [lane]。 |
| `PipelineParams` | `latency_cycles` | `int` | cycle | 单项从发起到完成的延迟 L [cycle]。 |
| `PipelineParams` | `initiation_interval_cycles` | `int` | cycle | 每 lane 发起间隔 II [cycle]。 |
| `PipelineEstimate` | `work_items` | `int` | item | 本批实际执行工作 W [item]；item 由具体 Unit 定义。 |
| `PipelineEstimate` | `issue_groups` | `int` | group | 发起组数 G=ceil(W/P) [group]。 |
| `PipelineEstimate` | `completion_cycles` | `int` | cycle | C=L+(G-1)II [cycle]；W=0 时 C=0。 |
| `PipelineEstimate` | `completion_time_s` | `float` | s | 本域完成时间 C/f [s]。 |
| `PipelineEstimate` | `peak_items_per_s` | `float` | item/s | 稳态发起上限 P*f/II [item/s]，不等于批次平均速率。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `count(name: str, value: int, minimum: int=1)` | 校验离散计数 n∈Z 且 n≥minimum；bool 不作为硬件数量。 |
| `real(name: str, value: float, *, minimum: float \| None=None)` | 归一有限实数；不接受单位字符串、bool 或隐式数组标量。 |
| `positive(name: str, value: float)` | 校验严格正的物理量；拒绝零频率、零时间常数和浮点下溢到零。 |
| `identifier(name: str, value: str)` | 校验显式身份/协议名称；名称不隐含任何厂商能力。 |
| `ceil_div(n: int, d: int)` | 整数向上取整 ceil(n/d)；n≥0、d>0，避免大整数先转 float。 |
| `ClockDomain` | 固定时钟域：Tclk=1/f；不同 domain 的 cycle 数不能直接相加。 |
| `ClockDomain.period_s` | 时钟周期 Tclk=1/f [s]。 |
| `ClockDomain.seconds(self, cycles: int)` | 本域 cycle→second：T=C/f；C=0 表示无工作。 |
| `PipelineParams` | P 条等价 lane 的服务参数；L 与 II 独立，不描述队列或背压。 |
| `PipelineEstimate` | 一批独立工作在空闲流水线上的分析结果；没有跨调用状态。 |
| `estimate_pipeline(p: PipelineParams, clock: ClockDomain, work_items: int)` | 从 cycle=0 发起 W 项：最后一组在 (G−1)II 发起，再经过 L 完成。 |

<!-- model-fields:end -->

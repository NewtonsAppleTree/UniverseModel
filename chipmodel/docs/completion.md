# chipmodel 基础开发完成报告

日期：2026-11-23。依据[项目使命](../../PROJECT_MISSION.md)与[开发计划](development_plan.md)，CH1–CH10的基础研究路径已完成实现和统一验收。这里的完成范围是可独立调用、可组合、可追溯的功能与分析基础；具体课题所需的执行精度、AI任务质量和器件校准继续按研究主张补充。实际批次结果统一记入[STATUS](../../docs/STATUS.md)。

## 1 覆盖与证据

| 范围 | 研究什么 | 怎样建模、从哪里调用 | 如何证明及适用边界 |
| --- | --- | --- | --- |
| 公共量与契约 | 同一工作/预算下的必要服务时间 | [common](../UNITS.md)、[bounds/graph](../composition/UNITS.md)：固定时钟、离散计数、资源包络、依赖DAG | 有理参考、大整数credit、循环/单位/重复身份反例；包络是必要条件 |
| CPU | 哪个阶段限制给定μop工作 | [CpuCore](../compute/cpu/UNITS.md)：显式工作类别、阶段需求与有限跨度 | 阶段消融和错误μop反例；不执行ISA或混合端口调度 |
| GPU | block能否驻留、启动与尾warp损失 | [occupancy](../compute/gpu/UNITS.md)：寄存器/shared-memory分配与grid约束 | 容量/量化/尾warp边界和单因素比较；occupancy不是kernel吞吐 |
| NPU | 格式、MAC并行度和供数怎样限制计算 | [MacArray](../compute/npu/UNITS.md)、数字Tile：显式操作格式、尾批、SRAM/DMA需求 | 同输入整数参考、格式拒绝、供数消融；不推断脉动阵列/厂商tensor指令 |
| CIM | 编码、ADC精度/共享与保持条件如何影响数值和服务 | [MatVec与台架](cim_bench.md)：DAC→GᵀV→TIA→ADC→移位累加；输入、阵列、外围身份明确 | 整数/Decimal参考、截断/溢出、ADC资源与精度对照、保持失败；串行策略显式，无编程/读噪声校准 |
| SRAM与buffer | 布局、bank/端口和容量是否可行 | [memory](../memory/UNITS.md)：byte范围拆word、读/写/共享RW、半开区间预留 | 地址枚举、byte-enable、bank计数、槽/存储容量反例；不模拟动态仲裁 |
| cache | 实际轨迹带来多少fill、dirty eviction和延后写回 | [CacheState/trace_cache](../memory/UNITS.md)：精确LRU、write-back/write-allocate、显式快照/flush | 时间戳参考、跨行、恢复等价、dirty守恒；无数据值、MSHR、coherence或命中时延 |
| DRAM | 地址/组织/burst及行条件怎样改变外存需求 | [DramReadProfile](../memory/controllers/UNITS.md)：CK/数据时钟关系、行块映射、隔离读取与搬运接入 | 混合进制地址参考、跨行/时钟/写反例、共享rank总线；行状态由输入声明，无完整调度/刷新/写 |
| NAND | 页缓冲重用与外部输出怎样分摊服务 | [NandReadProfile](../memory/flash/UNITS.md)：单die单页缓冲、data/OOB分列、快照恢复 | 冷/热页、边界与未知接口成本；无FTL/GC/多die并行推断 |
| control与互连 | 数据经过哪些资源，协议/编码带来多少工作 | [DMA/TensorLayout](../control/UNITS.md)、[NoC/D2D](../interconnect/UNITS.md)、[transfer](../composition/UNITS.md) | 源读/通道/每hop/目标写守恒、逐包枚举与大计数；同构NoC路径或单串行链路，无隐式协议桥 |
| Tile/Die/Package | 共享预算和跨Die流量是否被正确组合 | [assembly](assembly.md)：资源清单单一owner、多job DAG、保守容量并发、同指标scope投影 | 工作/容量/credit只计一次，跨域/路径/重叠反例和规模扫描；无一般事件执行、多CIM同步或可见性模型 |
| 几何、成本与热 | 物理条件与成本证据能支持哪一级判断 | [physical](physical_evidence.md)：静态完整资源覆盖、叶子动作、PVT精确查询、观测窗口、外部功率RC | 布局反例、摘要/叶子互斥、未知传播、来源哈希、Decimal热参考；面积fit仅必要条件，无完整芯片PPA |
| registry与工程 | 能否替换参数、独立构造并保存完整实验 | [registry](../registry/UNITS.md)、configuration/artifacts、[统一验收工具](../../tools/validate_chipmodel.py) | 严格配置、独立实例、来源/输入/失败记录、完整保存与只读回放、wheel隔离执行；不从配置动态导入代码 |

每个实现目录的[UNITS](../UNITS.md)维护参数术语、单位、关系、调用顺序和来源；[候选清单](component_inventory.md)只用于查漏，不表示候选机制已经实现。摘要与细模型不可重复收费，host运行时间不可作为目标硬件性能。

## 2 本次收尾修复

| 复现问题 | 修复与独立验证 |
| --- | --- |
| 串行链路8×10^308 bit在10^308 bit/s下应有有限时间，中间int→float却溢出 | 精确计数和有理除法后转binary64；逐包/末次lane beat枚举及Decimal商参考 |
| 冷却初温10^20 K、环境300 K、τ=1 s、时长1000 s时旧式抵消得到0 K | 冷却使用T∞+(T0−T∞)exp(−t/τ)，加热保留expm1短步长形式；70组高精度参考、零时长与单调边界 |
| CIM电流求和及TIA在最终结果有限时仍可中间溢出，极小乘积可能提前丢失 | 有理乘加后转带符号binary64；保留精确抵消/负电流，非零最终下溢明确拒绝；50组Decimal乘加及subnormal反例 |
| TensorLayout及CIM直接输入可把字典键误用为数据 | 统一仅接受list/tuple、冻结输入；保留广播、非连续布局、合法直接调用与JSON配置一致性 |

极值只检验数学实现的数值边界，不是推荐器件参数。CIM有理乘加增加宿主计算开销，适合当前局部功能参考规模；大阵列或统计误差课题应按精度要求选择并验证后端。计数仍为Python整数，连续输出仍为binary64，不因此声称无限精度物理硬件。

## 3 可重复验收

在仓库根目录运行，输出目录必须为新目录：

```powershell
python tools/check_model_rules.py
python tools/check_structure.py
python -m unittest discover -s tests/chipmodel -p "test_*.py" -v
python -m unittest discover -s tests/integration -p "test_*.py" -v
python tools/validate_chipmodel.py --output .build/chipmodel-acceptance
python tools/validate_chipmodel.py --read .build/chipmodel-acceptance
```

统一验收覆盖六组固定夹具：数字Tile 24、CIM 7、计算能力16、外存21、组合16、物理20，共104个案例。82个分析成功，22个预期边界失败全部保留诊断。主比较质量由各CLI检查；CIM精度消融的质量损失和物理总成本未知仍完整保留。预期失败意外成功也会使验收失败，不能只检查进程退出状态。

产物包含实际Python/config/pyproject原始字节哈希、HEAD、Python/平台、完整运行bundle、摘要、命令和host耗时。`acceptance.json`最后写入，代表该次运行完成；`--read`核对完整文件清单/哈希后只读取已有bundle，不执行研究模型、不改写历史源码身份。该工具不代替全仓库回归、物理来源校准或签名认证。全仓库测试仍按[CI](../../.github/workflows/structure.yml)的七组分别启动，避免测试模块同名冲突。

本次全仓库368项测试中366通过、2项可选PyTorch跳过；模型规则/结构检查通过。wheel的79份Python与工作区字节一致，隔离解释器导入59个项目模块并复算全部104案例，结果和保存回读一致。

本次证据位于`.build/chipmodel-closeout-20261123`。其中`studies`是统一验收输出，`validation.json`汇总检查，wheel检查保留源码字节比对和隔离进程记录。旧CH7–CH9证据保留。示例/配置/工具从checkout运行；wheel提供生产模块，需要调用方显式提供配置数据，不自动安装示例CLI。

## 4 后续工作的进入条件

| 研究主张需要什么 | 下一项实际工作 | 验收必须增加什么 |
| --- | --- | --- |
| 真实任务完成时间、重叠、尾延迟 | runtime/simulator与chipmodel局部服务接入 | accepted/完成/可见/释放语义、有限队列、合法调度、独立时序参考 |
| 量化/稀疏/CIM近似带来AI收益 | workloads/reference + compiler映射 | 数据集/任务质量门槛、额外索引/转换/重算工作、同预算基线 |
| CPU/GPU/DRAM/cache机制性能 | 明确指令/轨迹/协议子集和后端 | 固定版本参考、适配损失、校准及留出集、无收益案例 |
| 能效、PPA、多Die热或EDA方案优劣 | costmodel外部表/工具与具体结构绑定 | 真实动作/PVT覆盖、统计窗口、校准误差、联合几何/供电/热约束 |
| 芯片到节点/集群的组合 | systemmodel或既有上层研究路径引用资源 | summary/detail替代、端到端工作守恒、相同指标与预算、完整边界证据 |

基础阶段没有未完成的CH包。后续机制的开发顺序由具体课题和证据缺口决定；当前公开Nangate来源只再现两个标准单元面积/库标量漏电，不提供MAC/SRAM能耗或独立硅校准。其余候选硬件不以空类和默认零成本填充。

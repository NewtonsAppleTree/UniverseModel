# CH7：外存与缓存接入

本包按[项目使命](../../PROJECT_MISSION.md)支持AI工作集、访问布局和局部驻留研究。任务含义与布局生成仍由上层提供，chipmodel接收显式地址和资源。交付范围是独立访问模型、局部组合、已有Linear/Tile外存接入及可复现对照；后续[CH8：Tile/Die/Package组合](assembly.md)也已完成；当前下一包为CH9物理条件与成本证据。完成状态与本地验证证据见[STATUS](../../docs/STATUS.md)。

## 研究什么

| 研究问题 | 对照条件 | 可检验的结果 |
| --- | --- | --- |
| 更多rank/channel能否改善当前请求供数？ | 固定访问与时序，只改单个资源维度 | rank增容量但共享接口带宽不变；新channel若未被当前地址使用，单次服务不改善 |
| 未对齐、行边界、行状态怎样改变读成本？ | 显式地址、burst及hit/closed/conflict条件 | 逻辑byte与完整burst byte分开；越行明确拒绝或拆分 |
| 局部驻留能节省多少外存流量？ | 固定资源比较实际地址轨迹，另列ways资源消融 | 逐行hit/miss、回填、脏逐出和窗口末未写回量 |
| NAND局部列访问与页重用的代价来自哪里？ | 固定几何/tR/接口，改变page及data/OOB列请求 | 整页阵列服务、页缓冲命中和外部输出分别计量 |

上述比较不执行AI数值运算。Linear接入另用原有独立数值参考验证任务结果不变；没有新增AI质量提升、真实器件性能或物理可行性结论。

## 怎样建模

| 边界 | 输入/所有权 | 输出与精度 |
| --- | --- | --- |
| [MemoryAccess / cache](../memory/UNITS.md) | 资源本地byte范围和read/write；显式cache几何、策略、初态 | 确定性元数据状态与有序整行事务；无数据值、时序或一致性 |
| [DRAM组织](../memory/dram/UNITS.md) | 独立channel、共享rank、bank/row/column；整行连续地址布局 | 容量、峰值、混合进制地址坐标；支持非2幂bank数 |
| [DRAM读profile](../memory/controllers/UNITS.md) | 组织、CK/data clock、burst、行条件、来源 | 单行隔离读；span按行拆分并给条件界；无控制器调度 |
| [NAND读路径](../memory/flash/UNITS.md) | 单die、单页缓冲、页data/OOB范围、接口/命令成本、初态 | 页缓冲状态与无重叠串行策略时间；缺项保持未知 |
| [缓存/搬运组合](../composition/UNITS.md) | 引用唯一backing；SRAM/DRAM/容量边界互斥 | cache回填接DRAM；搬运按channel汇总burst，DRAM写成本未知 |
| [研究适配](../../evaluation/experiments/runner/UNITS.md) | 完整profile、工作、策略、源码身份与案例名单 | RunRecord保存/回读；Linear外存load声明行条件，store不套读时序 |

### DRAM：地址、数据率和条件界

`row_bytes=columns_per_row*payload_width_bits/8`。每个row块连续，`row_order`明确bank/row/rank/channel从低到高的混合进制顺序；不覆盖XOR散列或行内channel交织。

数据率`R=fdata*transfers_per_data_clock` [transfer/s]，有效`MT/s=R/10^6`；`burst_bytes=burst_transfers*payload_width_bits/8`，`burst_cycles/fCK=burst_transfers/R`。CK与WCK可不同频，但同一时钟域身份不能声明两个频率。当前burst时长须可表示为整数CK周期，profile严格拒绝不一致输入；技术名不隐含JEDEC时序。

非空请求的burst数为`ceil((start mod burst_bytes + length)/burst_bytes)`。单行入口`estimate_dram_access`拒绝跨行；`estimate_dram_span`按行分段，累计每channel的完整burst字节。接口界是`max(channel_bytes/channel_rate)`，span条件界取接口界与最慢独立片段条件服务的最大值。

行命中前缀为CL，closed为tRCD+CL，conflict为tRP+tRCD+CL；之后每额外burst间隔为max(tCCD,tBURST)。每段均假设PRE/ACT在其起点已合法，没有刷新、其他请求和完整命令约束带来的等待。row_state是调用方声明的条件；cache hit与DRAM row hit是两种不同状态。

这些片段分析没有连续更新open row，也没有计算全队列完成时间，不能把各段时间累加后宣称控制器性能。span.execution_time_s为None。直接写请求被读入口拒绝；组合中的目标写保留未知。max_fragments是宿主展开限制，非硬件队列深度。

### Cache：有状态的功能轨迹

当前唯一策略为`lru-write-back-write-allocate/v1`。每次byte访问拆成line touch；精确LRU在每set选择最久未使用的有效行。所有miss，包括整行覆盖写，都先整行读入；不包含整行写免读、write-around或预取优化。写命中/分配置dirty，dirty逐出在回填前发整行写回。

默认初态为空；`initial_state`显式恢复同profile的驻留顺序和dirty集合。默认不flush，deferred_dirty_bytes给出窗口末仍未写回的整行字节。显式flush按行地址序写回并清dirty，仍保留有效行。批内动作ID唯一；合并多批应携带批身份或重命名。

命中率只能按实际touch计数计算，不能从几何推断；零touch不定义比例。`metadata_bits`不含LRU替换电路或ECC。内部使用稀疏set状态，max_line_touches约束宿主材料化；数据值、MSHR、cache时序、coherence和原子操作仍未建模。

`analyze_cached_dram`校验原访问及初态处于DRAM backing，且完整cache行不会越过容量；将回填读交给DRAM span，按共享channel累计一次burst量。写回保留事务及未知成本，read_lower_bound_s只描述读子集；执行时间、lookup与写服务不能据此补零。

### NAND：页服务与输出字节分开

NandReadProfile仅支持一个die及一个完整页缓冲，plane数不隐含并行。page miss按完整data+OOB加载，随后只向外输出请求的列；同页hit跳过阵列服务，换页替换缓冲。data与OOB范围独立检查，OOB不加入可用数据容量。空输出不会加载页或改变缓冲。

page_read_s只计阵列→页缓冲，外部输出为`(data+OOB)/output_rate`，command_overhead_s覆盖每非空请求所需全部命令/地址。profile应为选定的列选择提供适用开销，模型不自动生成ONFI/SPI命令。当输出率或命令成本未知时，逐项输出None并给原因；modeled_time_s也保持None，known_service_s只累加已知部分。

完整已知时也只是无重叠串行策略的分析时间。暖缓冲初态不表示此前读取免费。NandTiming仍保留read/program按页、erase按块的独立时间查询；本包没有Flash写入状态、部分编程约束、FTL/GC/ECC、坏块、retry或耐久模拟。

## 如何证明

[芯片测试](../../tests/chipmodel/test_memory.py)使用独立笛卡尔积坐标检查全部24种DRAM维度排列；枚举单行byte集合得到burst覆盖；检查行界、时钟关系、rank共享、跨channel和无效输入。缓存使用60组随机轨迹与独立last-access时间戳参考比较，而非重复生产LRU列表实现；另检查脏逐出顺序、flush、零工作、宿主上限及分批快照等价。NAND由手算和分批恢复验证页加载、data/OOB、输出/命令缺项及粒度。

[集成测试](../../tests/integration/test_memory_experiment.py)检查完整名单、单参数资源消融、固定资源访问对照、失败/未知保留、输入/源码身份、保存回读和CLI。相同Linear任务换成DRAM源后，功能输出、scratch事务和MAC计量不变；DRAM通道需求等于实际burst总和，只有一次计费，目标写服务仍未知。

默认[配置](../../config/experiments/memory_access.json)有三组21个合成案例，其中17次分析成功、4个预期边界失败。成功项包含1个NAND输出成本未知。合成profile用来检验机制，不对应具体商用器件。

| 对照 | 可复核结果 | 解释边界 |
| --- | --- | --- |
| DRAM地址15、长度2 B，16 B burst | 实际传32 B；hit/closed/conflict为12/15/20 ns | CK=1 GHz，条件前缀分别4/7/12 cycles，两个burst |
| DRAM rank 1→2 | 容量512→1024 B，接口仍4 GB/s | 共享channel，不新增总线 |
| DRAM channel 1→2 | 总峰值4→8 GB/s，当前单行读仍12 ns | 访问只使用一个channel |
| 地址63、长度3 B | span拆1+2 B，实际传32 B，closed条件界11 ns | 单行入口拒绝；11 ns不是连续队列时间 |
| 32 B cache，0/32/0/32四次1 B读 | 0 hit、4 miss、64 B回填，读子集界16 ns | 两set单路，冲突到同一set |
| 同预算改为0/16/0/16 | 2 hit、2 miss、32 B回填，读子集界8 ns | 相同访问数/逻辑长度，地址布局改变 |
| 原轨迹ways 1→2 | 同样32 B回填与8 ns读界 | cache容量32→64 B，属于额外资源消融 |
| 写0/32/0 | 48 B回填、32 B逐出写回、16 B未写回 | 显式flush后写回总量48 B，DRAM写时间未知 |
| NAND同页输出4 B data+2 B OOB，再1 B OOB | 1次阵列页读，合计7 B外部输出，串行21 μs | 页32+4 B，tR=10 μs，1 MB/s，每请求命令2 μs |
| NAND只将输出率翻倍 | 串行17.5 μs | 页服务和命令不变，不能按带宽翻倍推算时间减半 |
| 第二次NAND请求换页 | 2次阵列读，串行31 μs | 接口字节不变，多一次页读取 |

这些时间只在声明条件及策略内成立，没有硬件实测、面积/能耗校准或真实控制器吞吐证据。建模参数关系查[参数清单](../../ARCHITECTURE_PARAMETERS.md)第5节；其gem5 DRAMInterface及Winbond W25N01GV等来源用于边界参考，不代表本包完成了相关器件校准。

## 调用与复现

专业模型可直接用构造器和纯函数调用。下面只从示例数据读取一份profile，绕过完整实验链：

```python
from configuration.resolution.dataclass_config import load_config
from evaluation.experiments.runner.memory import MemoryStudy
from chipmodel.memory.access import MemoryAccess
from chipmodel.memory.controllers.dram_read import estimate_dram_span

study = load_config(MemoryStudy, "config/experiments/memory_access.json")
profile = study.cases[0].profile
request = MemoryAccess(request_id="read", address_bytes=63,
                       length_bytes=3, direction="read")
result = estimate_dram_span(profile, request, row_state="closed")
assert [part.logical_bytes for part in result.fragments] == [1, 2]
```

Cache可单独调用trace_cache，不依赖DRAM；NAND可单独调用analyze_nand_reads。接入搬运时为MemoryResource提供dram_read，TransferRequest提供source_row_state；LinearTileBackend用external_read_row_state传递每次load条件，资源与地址构造例见集成测试。

```powershell
python -m example.memory_demo --source-revision <源码身份> --output .build/memory-study
python -m example.memory_demo --read .build/memory-study
python -m unittest discover -s tests/chipmodel -p "test_memory.py" -v
python -m unittest discover -s tests/integration -p "test_memory_experiment.py" -v
python tools/check_model_rules.py
python tools/check_structure.py
```

输出目录须为新路径。每个RunRecord保存完整案例清单、profile、实际输入、冷初态/flush条件、源码身份、假设、结果和诊断。资源消融自动检查只有一个数值参数改变；访问对照自动检查资源固定。回读验证完整性但不重新计算；host_elapsed_s单独记录，不进入目标性能指标。未提供源码身份时显式记为unrecorded。

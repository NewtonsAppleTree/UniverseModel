# CH8：Tile/Die/Package组合

本包按[项目使命](../../PROJECT_MISSION.md)研究固定工作、硬件清单和访问条件下，计算位置、共享资源及跨Die路径如何改变必要服务瓶颈。它承接CH4数字Tile和CH7外存，支持独立单Die子图及多Die组合。完成状态和本地证据见[STATUS](../../docs/STATUS.md)；[CH9物理条件与成本证据](physical_evidence.md)已接入成本查询、资源/能量/几何账本与热轨迹，器件校准按具体研究主张补充。

## 研究什么

| 问题 | 固定条件 / 改变因素 | 可检验结果 |
| --- | --- | --- |
| 多Tile分工是否改善供数或计算？ | 相同硬件和逐job TileWork，只改tile_id | 实际MAC/访存不变，共享memory/MAC的服务界可能不同 |
| 额外端口或lane的收益来自哪里？ | 固定全部job，只改一个数值资源参数 | 比较瓶颈是否迁移；额外资源不标成同预算算法收益 |
| 跨Die数据路径的代价是什么？ | 显式源/目标、方向、packet和编码 | 逻辑payload、协议byte和wire bit分开；共享方向合并计费 |
| 额外顺序限制会怎样影响结果？ | 固定工作、硬件和位置，只改完整job依赖 | 依赖路径与资源包络分别计算，不能拿调用顺序当硬件时间 |
| 摘要是否隐藏重复资源？ | 对同一分析选择Package、Die或叶子视图 | 唯一容量与资源贡献保持一致；祖先/后代混选被拒绝 |

本包输入是已映射工作和显式访问，未执行AI数值运算。它验证容量、工作量和必要时间的组合语义；任务质量仍需要workloads/reference或实际执行证据。数字Tile/CIM原有功能验证保持独立，不能据本包分析成功宣称真实芯片可行或任务加速。

## 怎样建模

### 唯一资源与明确归属

[TileBinding](../composition/tile/binding.py)只保存Tile/MAC/scratch身份和MAC配置，通过bind引用一份TransferResources生成原有DigitalTile视图。每个Tile的MAC必须位于其所有权子树；不同Tile不能将同一MAC登记成两份资源。同Die多个Tile可引用同一SRAM，容量与bank端口仍只有一份。

[DomainPlacement](../composition/die/topology.py)把每个实际memory/route域映射到一个声明Die，或映射到None表示本scope内的外部边界。所有引用域必须恰好声明一次；memory域与backing的物理归属必须相符。声明Die不能互相嵌套，所有节点必须属于本次scope。

NoC端点与资源位于同一Die；本包的串行PathLink表示跨边界完整方向，资源归scope层，端点属于不同Die或明确外部边界。双向接口拆成独立资源。Die内DMA只能把本Die的memory列为直接附加；跨界访问必须经过显式路径。当前复用CH3的同构NoC多hop或单串行link，混合NoC/串行/bridge多段路径仍明确拒绝。

`ChipAssembly.scope_id`可以直接是Die节点，独立调用不要求完整Package。多Die或外部边界可使用一个Package/bench根。Die/Package容器不产生额外latency、容量或算力；外部容量只表示清单中声明的地址空间，不能称为芯片片上存储总量。

所有MAC/SRAM/DMA/NoC/DRAM时钟去重，同一domain_id不得有两个频率。各资源cycle先按自己的时钟换成second；这不会自动补上CDC同步、相位、排队和可见性成本。

### 任务、预留与时间

[AssemblyJob](../composition/package/assembly.py)包含job_id、tile_id、原有TileWork和完整前驱job IDs。内部请求ID属于各自job；组合用长度前缀命名，避免不同job采用相同请求名或含斜线的ID时冲突。

每job先走独立analyze_tile的边界/能力验证。全局再将所有DMA搬运计一次，并合并所有local与DMA源读/目标写到唯一SRAM backing；同一MAC上多个job的工作量和初始发起credit只计算一次。新增job开始/完成屏障表达完整前驱；独立job下界只是一个并行的必要时间约束，没有额外资源demands。

全局结果保留三个不同层次：

1. 每个物理资源累计工作W和包络界`max(0,(W-credit)/rate)`。
2. 全局SRAM/MAC在忽略释放顺序后的必要服务，以及逐job内部条件界。
3. 显式job依赖形成的关键路径。

整体lower_bound_s取这些必要界的最大值。例：同一P=4、L=3、II=2的MAC承担两份8项工作，忽略任务释放的16项服务界是9 cycles；若明确两job先后执行，各自5 cycles使依赖界成为10 cycles。不能把两份job结果当作两套流水线，也不能对所有下界求和。

SRAM预留采用半开区间。同一backing上，没有完整先后关系的job可能同时活跃，其预留不得重叠；显式传递依赖允许复用区域。当前不推断共享只读别名、动态释放、双缓冲重叠、分块可见或取消。预留检查和地址容量通过也不证明数据值或执行因果正确。

`max_jobs`和`max_accesses`是宿主展开限制，不是硬件队列深度。实现保留逐job独立校验和完整DAG前驱关系；大规模或稠密依赖会增加宿主开销，不宣称恒定成本或线性伸缩。

### 边界与摘要

BoundaryTraffic按有向跨界link统计payload_bytes、protocol_bytes、wire_bits和packet_count。同一link上的真实多次传输累计，两个独立方向则各自使用预算。DRAM通过CH7的MemoryResource.dram_read接入，row_state仍是条件，目标写成本仍未知。

`project_scopes(analysis, selected_ids)`从同一冻结分析投影`resource-envelope-lower-bound/v1`。选择必须完整覆盖物理资源且无祖先重叠；输出保留原叶子贡献和各自工作单位，不把MAC、word、byte、bit相加。每行resource_lower_bound_s取所属贡献的最大值，行容量只汇总唯一backing。

该摘要用于解释同一个资源包络指标，不能作为另一份可叠加成本provider，也不代替整个任务的依赖/延迟界。Package或Die摘要与其内部叶子不能在同一视图中混选；各摘要时间不能直接求和当作执行时间。

## 如何证明

[芯片测试](../../tests/chipmodel/test_assembly.py)验证单job与原DigitalTile一致、共享容量/端口/engine、L与II、完整依赖及预留复用、独立双向D2D、ID隔离、摘要互斥和放置/时钟反例。45组随机资源和工作配置使用整数发起组数与Fraction换钟手算作为独立参考。

[集成测试](../../tests/integration/test_assembly_experiment.py)验证实验协议、完整名单、输入/源码身份、保存/回读/CLI，以及CH7外部DRAM经明确边界进入Die。不同模型层不重复收费，未知执行时间与能量保留为None和原因。

默认[实验配置](../../config/experiments/chip_assembly.json)为五组16案例：12次分析成功、4个预期失败（并发预留重叠、缺失前驱、缺少跨界路径、容量越界）。参数均为合成假设，不代表器件校准。

| 对照 | 结果 | 解释 |
| --- | --- | --- |
| 两份32 MAC、各8次4 B读，先都在Tile0，再分别放到两个Tile | 两者整体界均16 ns | 共用单bank/单读端口，MAC并行没有减少共享读工作 |
| 上述并行放置，仅将共享读端口1→2 | 16→8 ns | 数据容量仍512 B，读端口预算增加 |
| 上述基线，仅将SRAM时钟1 GHz→500 MHz | 16→32 ns | 先用SRAM时钟换算服务时间，其他时钟不随之变化 |
| 两份64 MAC、访存保持不变，Tile0集中→两Tile分工 | 32→16 ns | 同硬件/同工作的位置比较，计算瓶颈得到缓解 |
| 两Tile上的上述工作加完整job先后依赖 | 16→32 ns | 额外顺序限制增加关键路径，资源工作量没有变化 |
| 两个17 B请求共用一个1 Gb/s D2D方向 | 34 B payload、16 B协议、500 wire bit，整体界500 ns | 每请求两packet，共用线路预算只计一次 |
| D2D lanes 1→2 | 500→250 ns | 实际线路量仍500 bit，带宽预算翻倍 |
| D2D固定延迟2→20 ns | 整体界仍500 ns | 累计共享总线需求仍占主导 |

同向线路量由逐请求分包/编码推导，不以简化payload带宽代替。单个17 B请求有2个packet，每packet 4 B开销、8b/10b编码，合计250 bit；双向同时各一个请求则各用自己的方向资源，界为252 ns，并非把500 bit除以单方向带宽。

本包没有一般事件调度、混合路径bridge、多CIM台架合并、真实数据一致性或几何/热/功率验证。CH9提供带来源的物理条件接口，未特征化的本包资源成本仍保持未知，缺失能耗不以零表示。

## 独立调用与复现

专业接口可以直接构造，不要求运行完整实验。以下只借示例读取一组静态参数：

```python
from configuration.resolution.dataclass_config import load_config
from evaluation.experiments.runner.assembly import AssemblyStudy
from chipmodel.composition.package.assembly import analyze_assembly, project_scopes

study = load_config(AssemblyStudy, "config/experiments/chip_assembly.json")
case = study.cases[0]
result = analyze_assembly(case.assembly, case.jobs)
summary = project_scopes(result, (case.assembly.scope_id,))
assert result.memory_capacities == (("scratch", 512),)
```

```powershell
python -m example.assembly_demo --source-revision <源码身份> --output .build/assembly-study
python -m example.assembly_demo --read .build/assembly-study
python -m unittest discover -s tests/chipmodel -p "test_assembly.py" -v
python -m unittest discover -s tests/integration -p "test_assembly_experiment.py" -v
python tools/check_model_rules.py
python tools/check_structure.py
```

输出目录须为新路径。资源消融只允许改一个数值资源参数并固定全部job；位置比较固定硬件、TileWork及依赖；顺序比较固定硬件、位置及TileWork。完整清单、工作、来源、失败与未知进入RunRecord；回读不重算。host_elapsed_s单独记录，不进入目标指标。源码身份未提供时为unrecorded。

本地证据另保留2/8/32 Tile与job的规模观测，固定每job工作和2048 B共享SRAM，分别记录实际输入、目标必要界、宿主运行时间及tracemalloc峰值。它用于说明模型运行成本，单次宿主观测不作为跨平台性能或硬件扩展性结论；具体结果由STATUS和保存产物维护。

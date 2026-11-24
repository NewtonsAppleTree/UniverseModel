# runner：独立调用与有限线性映射比较

`system_tiering.py`的TierStudy/TierCase固定相同硬件、tier/CXL/DMA声明及15例完整候选。记录同phase驻留、原生CXL内存行工作、三状态迁移预留或失败；原生时间未知，兼容DMA保留S3条件下界。回读使用保存路径重分析，不执行producer/新寻路；核对容量、decoder、瞬时预留、对象身份、方法/工作/指标、来源与全名单。接口、人工参数和未覆盖机制见[S4指南](../../../systemmodel/docs/tiering_usage.md)。

`system_transfer.py`的TransferStudy/TransferCase固定DmaSystem，各case保存完整CopyBatch。独立PCIe分包与DMA服务由systemmodel提供；runner记录实际路径、物理读写/帧/DMA工作、整copy依赖与已知条件下界。payload_bytes、copied_bytes与pcie_frame_bytes区分任务/多次搬运/线路工作；known_service_lower_bound不是target_execution_time，完整能耗仍未知。回读只验证保存路径并静态重分析，保留全部失败与来源，不执行producer或新寻路。专业接口见[S3指南](../../../systemmodel/docs/transfer_usage.md)。

`system.py`新增NodeStudy/NodeCase：固定完整node清单，逐case保存实际PathRequest、静态路径或失败。目标时延/能量未知；回读不搜索/执行，只检查保存路径在同一拓扑上的合法性、资源引用、指标、完整名单与来源。属于静态证据重分析，不证明最少跳数、真实设备能力或任务质量。示例与专业参数见[系统首包](../../../systemmodel/docs/foundation_usage.md)。

`system_memory.py`的MemoryStudy/MemoryCase固定MemorySystem，每例保存完整MemoryPlan与可选MemoryAccessRequest。独立placement-only不声明路径；副本按粒度预留、地址alias不增容，phase仅为逻辑生命周期。输出每backing峰值、解析物理区间、请求路径和NUMA分类；不相加各池的独立峰值，不推算目标成本。回读静态重分析区间/映射/NUMA并检查保存路径、计数、unknown reason、全名单与来源，既不搜索也不执行producer。失败诊断只保留不重跑。用法和比较口径见[内存指南](../../../systemmodel/docs/memory_usage.md)。

`attention_evidence.py`只消费保存的任务/计划/观测，验证行所有权、资源守恒与边界，并用保存参考输出重新计算数值比较；不拥有硬件或执行状态。mapping/retrieval新implementation为v2，必存reference_output，NumPy另存两条实际输出。历史v1仅执行能由原证据支持的检查；配置/bundle仍为v1。retrieval还验证选参计数、训练标签/类配额、Attention语义和预测变化；指标与未知成本不能互相矛盾。详见[审计](../../../workloads/docs/completion_audit.md)。

`workload.py`接入AttentionSuite/Case：先准备并保存实际Q/K/V，再调用独立参考和逻辑计数；准备失败保留清单/错误，参考失败保留实际输入。完整名单、来源、预算、假设和内容参与记录；succeeded不表示真实AI质量通过。目标时间/能量为None+原因，host_elapsed_s仅覆盖通用callback/收集。write_study/read_study沿用不可覆盖bundle并验证名单/身份/输出结构，回读不执行参考或访问原dataset。公式、关键宿主预算、顺序和证据见[workloads指南](../../../workloads/docs/foundation_usage.md)与[集成测试](../../../tests/integration/test_workload_experiment.py)。

CH6的`compute.py`使用ComputeCase/ComputeStudy连接CPU/GPU/NPU专业入口。每组唯一基线，资源消融固定work且仅改变一个数值模型参数，工作消融固定model且只改一个数值需求；语义变化列boundary。返回专业分析与未知execution_time指标，不作跨架构性能排名或数值质量声明。完整名单/输入/来源参与记录，保存/回读拒绝混用和缺失，且回读不重跑模型。详见[CH6指南](../../../chipmodel/docs/compute_capabilities.md)。

`run_experiment(spec, configuration, inputs, execute)` 返回 RunRecord。execute 接收隔离副本，返回 producer payload 与 tuple[Metric]；没有动态 import、插件发现、隐式编译或模拟时钟。

使用顺序：序列化输入快照 → 深拷贝边界 → 调用 → 输出/指标校验 → succeeded/failed。host_elapsed_s 是宿主执行/收集开销 [s]；目标时间必须显式来自模型。闭包/外部状态由调用者负责，状态组件在每次调用中重建或传入初态。

最关心隔离、异常可见、不可变快照、指标口径；执行成功不宣称数值验证通过。结构输入错误发生于调用前；callback/结果错误变成失败记录，无 fabricated output。测试见[工程测试](../../../tests/integration/test_framework.py)。

`linear.py` 提供 LinearHardware/MappingCandidate/LinearExperiment/LinearStudy 和 `evaluate_mapping`、`run_study`、`summarize_records`。一次生成相同实际输入，各候选独立建立计划/容量/流量并做功能和精确参考比对，再复用已有 MAC/DMA 服务模型。候选失败保留为记录，不将运行 succeeded 与数值 passed 等同。

研究参数包括 M/N/K、格式、tile、C 策略、scratch [B]、MAC lanes/L/II 与 compute clock、DMA bytes/cycle/burst/startup 与 DMA clock；容差/seed/host 工作上限另属验证设置。目标下界为 `max(T_MAC_ideal, T_DMA_serial)` [s]，仅在声明服务模型下成立，不是事件完成时间。能耗明确未知；没有额外全局硬件资源或执行状态。完整假设、手算与限制见[指南](../../docs/linear_mapping.md)，验证见[线性集成测试](../../../tests/integration/test_linear_experiment.py)。

## 训练有限候选

`training.py` 使用 TrainingStudy/TrainingExperiment，所有候选重置到同一个旧 state/data；完整固定训练计划、实际输入、生成版本、独立参考环境与比较结果进入记录。GEMM MAC/行请求、辅助逻辑 payload、backing 峰值、GEMM scratch 峰值分开计量。`gemm_resource_lower_bound` 只覆盖 GEMM 子集，`step_time` 和 `step_energy` 明确未知。

精确有理数参考为默认；显式选择 PyTorch 时延迟加载 CPU autograd/SGD，实际工具版本进入配置身份。`summarize_training` 从记录回读，不需要安装原参考后端。详情见[训练指南](../../docs/training_step.md)，完整验证见[集成测试](../../../tests/integration/test_training_experiment.py)。

## 集群有限放置比较

cluster.py提供ClusterStudy/PlacementCandidate、evaluate_cluster、run_study、summarize_records、write_study/read_study。候选共享图、组和固定P2P输入，只改变placement；装配/路径/profile失败在runner内部留档。记录含完整候选清单，回读拒绝缺候选或混用预算/输入/来源。最后写研究索引，底层使用既有run bundle，不另建硬件引擎。

时间指标为资源、必要路径延迟、指定割及其max的条件下界[s]。帧量[B]和能量[J]无依据则None+原因。宿主时间独立。字段由下表生成，见[集群指南](../../../clustermodel/docs/foundation_usage.md)和[集成测试](../../../tests/integration/test_cluster_experiment.py)。

ClusterStudy新增可选NetworkOutage，所有候选共享原图与停用条件。原图/条件先保存，再在每个callback内部生成静态视图；未知选择、失效显式路径和断路保留失败记录。成功payload增加network_overview、traffic_description、outage_view，原下界账本字段保留。summarize_records(include_overview=True)及CLI --overview只读取已保存观测；旧记录缺观测返回None，不重新执行。见[横向指南](../../../clustermodel/docs/breadth_usage.md)。

集群回读还检查配置schema与字段、快照候选清单自身的重复、跨候选run_id唯一性，以及索引/条目的确切字段。旧版本同schema记录允许缺可选outage；不会为缺总览的旧观测重新执行模型。拒绝重复清单可防止集合化汇总掩盖候选身份冲突，验证见集群集成测试。

## 数字Tile地址适配

`tile_mapping.py`提供LinearTileBackend与map_linear_tile：从compiler计划显式生成外部行地址、packed scratch地址和本地计算访问。`scalar-ab-register-c/v1`每MAC读A/B、每K slice寄存器累加C后写回scratch；后续slice读取C。禁止由外部DMA字节推断本地复用。

LinearHardware.tile_backend可选；接入时MAC/DMA/容量必须与旧摘要字段一致。输出增加tile_work和tile_analysis，全部参数/轨迹进入记录；摘要时间作为诊断，不再额外相加。`max_local_accesses`为宿主材料化上限。配置/主对照/单因素敏感性与完整候选保存回读见[芯片基础指南](../../../chipmodel/docs/foundation_usage.md)。

## CIM局部研究对照

`cim.py`提供CimStudy/CimCandidate、apply_candidate、evaluate_cim_experiment、run_study与完整summarize/write/read。主mapping只改变ADC前/后差分；ADC资源与精度消融另有标签并限制为匹配类别的单项改动。相同整数输入、完整候选名单、profile、初态、时序/数值轨迹、质量与未知成本进入记录。

`reference_integer_matvec`给独立点积，再独立应用最终输出格式。运行成功、质量通过、容量/保持失败分开；resource_lower_bound与serial_policy_time分别是下界和策略分析。max_cell_evaluations为宿主预算。详情见[CIM指南](../../../chipmodel/docs/cim_bench.md)。

## CH7外存/缓存研究与Linear接入

memory.py提供MemoryWork/Case/Study和run/summarize/write/read_study，分别调用DRAM条件分析、cache→DRAM组合和NAND串行读取。案例固定冷cache/页缓冲初态并保存完整profile、实际访问、行状态、flush策略、来源与未知成本。每组一个baseline，resource_ablation保持work且只改一个数值资源参数，access_comparison保持全部资源；boundary保留失败或未知。指标不作跨介质统一性能排名，成功不表示执行时间或物理可行性已证实。

LinearTileBackend.external_read_row_state将显式DRAM条件传给每次load；store的写成本仍未知。替换外部profile保持原任务、scratch事务及MAC计量，DRAM通道只累计真实burst一次。完整名单保存/回读拒绝遗漏、混来源/输入、重复和越界索引；回读不运行模型。见[CH7指南](../../../chipmodel/docs/memory_access.md)与[集成测试](../../../tests/integration/test_memory_experiment.py)。

## CH8固定工作与共享资源研究

assembly.py提供AssemblyCase/Study、run/summarize/write/read_study，直接接收ChipAssembly与实际AssemblyJob。五组默认案例区分placement、单数值resource_ablation、ordering_ablation和boundary。位置变化保持硬件/TileWork/依赖；资源消融固定全部job；顺序变化固定硬件/位置/TileWork。没有数值执行或物理可行性主张。

完整清单、实际访问、预留、依赖、来源、失败和未知进入RunRecord，回读拒绝混来源/输入/名单且不重跑模型。返回全局分析、scope与whole的同指标投影；目标必要界和host_elapsed_s分开。专业接口与证据见[CH8指南](../../../chipmodel/docs/assembly.md)，协议验证见[集成测试](../../../tests/integration/test_assembly_experiment.py)。

CH9的[physical.py](physical.py)连接PhysicalModel/PhysicalWork、CostTable和可选ThermalTrace。每组基线固定来源表，geometry/observation/thermal/pvt/activity各限定变动范围，thermal仅单数值变化。专业输入、完整名单和来源保留，已知子集/未知总成本、几何必要条件和热阈值与程序成功分开。保存/回读不执行模型，宿主时间不参与积分；见[CH9指南](../../../chipmodel/docs/physical_evidence.md)。

## Attention映射、真实任务与共享bundle

`attention.py`固定AttentionMappingStudy的task/input/hardware比较query_tile、score驻留及KV布局；专业memory/traffic、独立数值校验和格式匹配的MAC/DMA服务分开保存，SFU/存储/执行与能量未知。`retrieval.py`按RetrievalProfile保存真实观测、train-only状态、validation选参表、逐例test输出、独立数值/任务质量和可选NumPy；质量失败可为预期负对照，不改成运行失败。`bundle.py`复用固定目录索引/原始SHA256和调用方语义检查，回放不执行模型；分类指标由保存观察重算。参数、资源边界、默认5/12例与完整验收见[W4/W5指南](../../../workloads/docs/mapping_and_quality.md)。

`system_network.py`提供NodeWork/MessageBinding/NetworkCase/NetworkStudy：node端点与容量原样导入cluster，同节点消息仅用本地DMA，跨节点绑定TX/RX、实际object/version/offset/bytes。node局部与NIC/fabric计量互斥；组合取必要界最大值。`system_ai.py`提供AiTask/AiCase/AiStudy：Linear/训练/Attention实际输入与独立参考绑定节点预留/完整copy，保守workspace与scratch分开，策略同预算、参数干预显式记录。两种runner的回读均无producer/新寻路，AI只以独立reference重验保存actual；全部失败、来源和unknown保留。见[S5](../../../systemmodel/docs/network_usage.md)与[S6](../../../systemmodel/docs/ai_usage.md)。

<!-- model-fields:start -->

### [assembly.py](assembly.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `AssemblyCase` | `name` | `str` | 1（标识/枚举） | 全研究唯一案例身份。 |
| `AssemblyCase` | `group` | `str` | 1（标识/枚举） | 固定基线的一组位置/资源/顺序比较。 |
| `AssemblyCase` | `role` | `Literal['baseline', 'placement', 'resource_ablation', 'ordering_ablation', 'boundary']` | —（结构/对象） | 区分调度位置、额外资源与边界反例。 |
| `AssemblyCase` | `assembly` | `ChipAssembly` | —（结构/对象） | 唯一资源/时钟/Die/domain清单及profile来源。 |
| `AssemblyCase` | `jobs` | `tuple[AssemblyJob, ...]` | —（结构/对象） | 实际任务、MAC/访问/搬运、地址预留与依赖。 |
| `AssemblyStudy` | `cases` | `tuple[AssemblyCase, ...]` | —（结构/对象） | 全部有限比较名单，包括失败反例。 |
| `AssemblyStudy` | `schema_version` | `Literal['chip-assembly-study/v1']` | —（结构/对象） | 配置与比较协议版本。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `AssemblyCase` | 专业组合与完整job输入直接进入记录；role约束允许变化的研究因素。 |
| `AssemblyStudy` | 每组一基线；位置变化保留实际工作，资源消融只改一个数值参数，顺序消融只改依赖。 |
| `run_study(study: AssemblyStudy, *, source_revision: str='unrecorded')` | 完整清单、配置、实际工作与来源参与身份；运行异常保存failed记录，不删去反例。 |
| `summarize_records(records: tuple[RunRecord, ...])` | 回读检查完整同源名单和真实工作；保留专业分析、全部失败与未知指标。 |
| `write_study(records: tuple[RunRecord, ...], directory: str \| Path)` | 哈希bundle先落盘，固定相对路径索引最后写；禁止覆盖已存在的研究目录。 |
| `read_study(directory: str \| Path)` | 回读不执行模型；索引路径、run身份和完整研究协议必须一致。 |

### [attention.py](attention.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `AttentionCandidate` | `name` | `str` | 1（标识/枚举） | Unique mapping identity. |
| `AttentionCandidate` | `query_tile` | `int` | token | Maximum rows per query block [token]. |
| `AttentionCandidate` | `score_policy` | `Literal['fused', 'spill']` | —（结构/对象） | Explicit intermediate residency. |
| `AttentionCandidate` | `kv_layout` | `Literal['shared', 'expanded']` | —（结构/对象） | Logical sharing or explicitly copied backing. |
| `AttentionCandidate` | `expected_status` | `Literal['succeeded', 'failed']` | —（结构/对象） | Reviewed fixture expectation. |
| `AttentionHardware` | `scratch_capacity_bytes` | `int` | B | Separate scratch reservation budget [B]. |
| `AttentionHardware` | `backing_capacity_bytes` | `int` | B | Original inputs, outputs and temporary backing reservation budget [B]. |
| `AttentionHardware` | `mac` | `MacArray` | —（结构/对象） | Explicit arithmetic/P/L/II/clock/source profile; must match binary64 mul-add at evaluation. |
| `AttentionHardware` | `dma` | `DmaParams` | —（结构/对象） | One serialized payload service channel; no implicit second charge for memory traffic. |
| `AttentionHardware` | `dma_clock` | `ClockDomain` | —（结构/对象） | DMA service clock, independently converted to seconds. |
| `AttentionMappingStudy` | `workload` | `AttentionSpec` | —（结构/对象） | Common task semantics for all candidates. |
| `AttentionMappingStudy` | `hardware` | `AttentionHardware` | —（结构/对象） | Common resource budget, no per-candidate overprovisioning. |
| `AttentionMappingStudy` | `candidates` | `tuple[AttentionCandidate, ...]` | —（结构/对象） | Complete unique mapping roster, including failures. |
| `AttentionMappingStudy` | `seed` | `int` | —（结构/对象） | Deterministic uint64 Q/K/V generation seed. |
| `AttentionMappingStudy` | `atol` | `float` | output value | Absolute numerical output tolerance [output value]. |
| `AttentionMappingStudy` | `rtol` | `float` | 1 | Relative numerical tolerance [1]. |
| `AttentionMappingStudy` | `max_macs` | `int` | MAC | Host visible-pair contraction budget [MAC]. |
| `AttentionMappingStudy` | `max_elements` | `int` | element | Host input/interpreter storage guard [element]. |
| `AttentionMappingStudy` | `max_score_pairs` | `int` | pair | Host independent-reference probability matrix limit [pair]. |
| `AttentionMappingStudy` | `schema_version` | `Literal['attention-mapping/v1']` | —（结构/对象） | Same-task fixed-budget comparison. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `AttentionCandidate` | A candidate changes only declared mapping choices; every candidate shares the same task/input/hardware budget. |
| `AttentionHardware` | MAC and serialized DMA are separate resources; scalar operations and actual external-memory timing remain uncovered. |
| `AttentionMappingStudy` | One complete comparison fixes quality tolerances, host limits and source-independent workload inputs. |
| `evaluate_attention(study: AttentionMappingStudy, candidate: AttentionCandidate, inputs: AttentionInputs)` | Execute and compare against the independent reference, then query each resource once with matching arithmetic. |
| `run_study(study: AttentionMappingStudy, *, source_revision: str='unrecorded')` | Keep all candidates, including input preparation failures; records own actual inputs rather than just seeds. |
| `summarize_records(records: tuple[RunRecord, ...])` | Replay validates complete common conditions and output identities without running mapping, input generation or models. |
| `write_study(records: tuple[RunRecord, ...], directory: str \| Path)` | Commit a complete immutable mapping bundle using the common checked index. |
| `read_study(directory: str \| Path)` | Read committed mapping evidence without invoking its models or reference. |

### [attention_evidence.py](attention_evidence.py)

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `validate_saved_plan(spec: AttentionSpec, snapshot: dict, *, query_tile: int, score_policy: str='fused', kv_layout: str='shared')` | A saved plan must own all rows of this task and use the candidate's exact declared mapping choices. |
| `validate_saved_resources(spec: AttentionSpec, plan: dict, memory: dict, traffic: dict, *, scratch_capacity_bytes: int, backing_capacity_bytes: int)` | Check saved reservations, payload bounds and work conservation; no allocator, traffic generator or device model is rerun. |
| `validate_saved_comparison(spec: AttentionSpec, inputs: AttentionInputs, actual: list, validation: dict, *, reference_output: list \| None=None, atol: float=1e-12, rtol: float=1e-12)` | v1 evidence gets structural checks; v2 additionally reconstructs error/tolerance results from saved reference observations. |

### [bundle.py](bundle.py)

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `write_records(records: tuple[RunRecord, ...], directory: str \| Path, schema: str, validate: Callable)` | Validate a complete study, then write immutable runs before committing its index. |
| `read_records(directory: str \| Path, schema: str, validate: Callable)` | Read only fixed local run names and verify complete semantics without executing producers. |

### [cim.py](cim.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `CimCandidate` | `name` | `str` | 1（标识/枚举） | 当前study唯一的候选身份。 |
| `CimCandidate` | `category` | `Literal['baseline', 'mapping', 'resource_ablation', 'precision_ablation', 'boundary']` | —（结构/对象） | 明确比较口径。 |
| `CimCandidate` | `subtract_before_adc` | `bool \| None` | —（结构/对象） | 模拟/数字差分位置；None沿用基线。 |
| `CimCandidate` | `adc_lane_count` | `int \| None` | lane | ADC通道数 [lane]，改变属于资源消融。 |
| `CimCandidate` | `adc_frequency_hz` | `float \| None` | Hz | ADC时钟 [Hz]，不自动更改物理校准来源。 |
| `CimCandidate` | `adc_resolution_bits` | `int \| None` | bit | 名义ADC精度 [bit]，改变不自动推断速度/能耗收益。 |
| `CimCandidate` | `hold_slot_count` | `int \| None` | sample | 外部标量保持槽数 [sample]。 |
| `CimCandidate` | `hold_valid_duration_s` | `float \| None` | s | 外部保持有效期 [s]。 |
| `CimStudy` | `tile` | `CimTile` | —（结构/对象） | 所有候选共有的基线硬件及profile来源。 |
| `CimStudy` | `inputs` | `CimInput` | —（结构/对象） | 同一份已驻留整数输入/权重。 |
| `CimStudy` | `candidates` | `tuple[CimCandidate, ...]` | —（结构/对象） | 完整有限候选名单；首项是唯一baseline。 |
| `CimStudy` | `max_cell_evaluations` | `int` | cell evaluation | 宿主工作/轨迹展开上限 [cell evaluation]，非硬件预算。 |
| `CimStudy` | `max_abs_error` | `int` | integer | 输出整数允许的绝对误差 [integer]；默认精确匹配。 |
| `CimStudy` | `schema_version` | `Literal['cim-study/v1']` | —（结构/对象） | 研究配置版本。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `CimCandidate` | 有限且可审阅的单因素改动；没有可执行公式或任意配置路径。 |
| `CimStudy` | 同一组实际向量/矩阵在相同基线及有标签的消融下比较，失败和质量损失都保留。 |
| `apply_candidate(tile: CimTile, candidate: CimCandidate)` | 显式替换生产者字段；依赖校验与范围由原始模型负责，不创建另一份参数公式。 |
| `evaluate_cim_experiment(tile: CimTile, inputs: CimInput, *, max_cell_evaluations: int=1000000, max_abs_error: int=0)` | 独立整数参考再应用最终输出格式；量化误差、输出溢出、ADC限幅分别观察。 |
| `run_study(study: CimStudy, *, source_revision: str='unrecorded')` | 每个候选共享真实数据与完整名单；质量失败和执行失败保持不同状态。 |
| `summarize_records(records: tuple[RunRecord, ...])` | 由记录重建完整对照；拒绝混用来源/输入/预算、遗漏失败候选或重复运行身份。 |
| `write_study(records: tuple[RunRecord, ...], directory: str \| Path)` | 先写全部不可变bundle，最后提交索引；目录存在时拒绝覆盖。 |
| `read_study(directory: str \| Path)` | 只回读哈希验证的记录，不重新编程/计算；索引不能指向任意路径或漏掉失败样本。 |

### [cluster.py](cluster.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `PlacementCandidate` | `name` | `str` | 1（标识/枚举） | Unique candidate identity; never interpreted as a filesystem path. |
| `PlacementCandidate` | `placements` | `tuple[RankPlacement, ...]` | —（结构/对象） | Requested placements; graph/group feasibility is checked inside the run. |
| `ClusterStudy` | `graph` | `NetworkGraph` | —（结构/对象） | Identical node/fabric resource budget for all candidates. |
| `ClusterStudy` | `traffic` | `TrafficInput` | —（结构/对象） | Identical data identities, lengths, routes/policy and requested cuts. |
| `ClusterStudy` | `candidates` | `tuple[PlacementCandidate, ...]` | —（结构/对象） | Nonempty finite roster, including infeasible requested placements. |
| `ClusterStudy` | `groups` | `tuple[CommunicationGroup, ...]` | —（结构/对象） | Shared logical membership and ordering. |
| `ClusterStudy` | `outage` | `NetworkOutage \| None` | —（结构/对象） | Optional static channel/owner outage shared by every placement; original graph is retained. |
| `ClusterStudy` | `schema_version` | `Literal['cluster-placement-study/v1']` | —（结构/对象） | Comparison input schema. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `PlacementCandidate` | One candidate changes rank placement only; shared graph, groups and messages define the comparison budget. |
| `ClusterStudy` | A strict nonexecutable study declares a finite candidate roster and one common communication workload. |
| `evaluate_cluster(cluster: ClusterSpec, traffic: TrafficInput)` | Adapt independent cluster analysis to standard metrics, preserving unknown costs and conditional lower bounds. |
| `run_study(study: ClusterStudy, *, source_revision: str='unrecorded')` | Run every declared candidate with the same input/resource budget; no result-based filtering is performed. |
| `summarize_records(records: tuple[RunRecord, ...], *, include_overview: bool=False)` | Reconstruct the complete roster from snapshots and reject mixed budgets, versions or missing candidate evidence. |
| `write_study(records: tuple[RunRecord, ...], directory: str \| Path)` | Write all existing RunRecord bundles then a final study index; incomplete studies cannot silently lose failures. |
| `read_study(directory: str \| Path)` | Verify a committed roster and each bundle's hashes; never execute the model while reading observations. |

### [compute.py](compute.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `ComputeCase` | `name` | `str` | 1（标识/枚举） | 全研究唯一的案例身份。 |
| `ComputeCase` | `group` | `str` | 1（标识/枚举） | 同一家族的一组基线与单因素比较，不进行跨架构性能排名。 |
| `ComputeCase` | `family` | `Literal['cpu', 'gpu', 'npu']` | —（结构/对象） | 所选能力分析入口。 |
| `ComputeCase` | `role` | `Literal['baseline', 'resource_ablation', 'workload_ablation', 'boundary']` | —（结构/对象） | 资源、工作变化与边界反例分开。 |
| `ComputeCase` | `model` | `CpuCore \| GpuSmParams \| MacArray` | —（结构/对象） | 显式能力、服务/分配规则及profile来源。 |
| `ComputeCase` | `work` | `CpuWork \| GpuBlock \| MacWork` | —（结构/对象） | 该模型对应的独立任务需求。 |
| `ComputeStudy` | `cases` | `tuple[ComputeCase, ...]` | —（结构/对象） | 完整有限名单，包含不可行或不支持的边界案例。 |
| `ComputeStudy` | `schema_version` | `Literal['compute-capacity-study/v1']` | —（结构/对象） | 配置语义版本。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `ComputeCase` | 封闭的三类独立调用；family只选择已有入口，不接受可执行字符串。 |
| `ComputeStudy` | 基线与消融都保存完整参数；每组一个基线，资源消融固定工作且仅改单个数值参数。 |
| `run_study(study: ComputeStudy, *, source_revision: str='unrecorded')` | 每条记录保存完整研究名单、实际输入和源码身份；错误签名在记录内部失败。 |
| `summarize_records(records: tuple[RunRecord, ...])` | 验证完整名单/同源研究并展示各专业输出；不以succeeded代替物理可行性或数值质量。 |
| `write_study(records: tuple[RunRecord, ...], directory: str \| Path)` | 各run先写哈希校验bundle，最后提交索引；目标目录不覆盖已有实验。 |
| `read_study(directory: str \| Path)` | 只读保存结果，不重新分析；路径、身份、完整名单与单因素协议均复核。 |

### [linear.py](linear.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `LinearHardware` | `operand_dtype` | `Literal['int8', 'float64']` | —（结构/对象） | Supported operand format; matching 64-bit accumulation/output assumed. |
| `LinearHardware` | `scratch_capacity_bytes` | `int` | B | Shared A/B/C scratch capacity [B]; >0. |
| `LinearHardware` | `compute_clock` | `ClockDomain` | Hz | MAC clock f_compute [Hz]; distinct from transfer clock. |
| `LinearHardware` | `mac` | `PipelineParams` | lane, cycle | MAC lanes P and service L/II [lane, cycle]; supplied assumptions, not calibration. |
| `LinearHardware` | `dma_clock` | `ClockDomain` | Hz | Single DMA channel clock f_dma [Hz]. |
| `LinearHardware` | `dma` | `DmaParams` | —（结构/对象） | Row-request DMA service parameters; external DRAM/NoC are not added implicitly. |
| `LinearHardware` | `tile_backend` | `LinearTileBackend \| None` | —（结构/对象） | 可选逐地址 SRAM/路径分析；None 保留原 MAC/DMA 摘要边界。 |
| `MappingCandidate` | `name` | `str` | 1（标识/枚举） | Human-readable unique candidate identity, never a path or executable string. |
| `MappingCandidate` | `tile` | `TileShape` | element | Requested maximum tile extents [element]. |
| `MappingCandidate` | `strategy` | `Literal['output_stationary', 'reload_partials']` | —（结构/对象） | C residency/partial traffic policy. |
| `LinearExperiment` | `workload` | `LinearSpec` | —（结构/对象） | Unmapped dense task semantics and operand format. |
| `LinearExperiment` | `hardware` | `LinearHardware` | —（结构/对象） | Single resource capability/budget and service assumptions. |
| `LinearExperiment` | `candidate` | `MappingCandidate` | —（结构/对象） | One explicit mapping to validate and execute. |
| `LinearExperiment` | `max_macs` | `int` | MAC | Host functional/reference work limit [MAC]; not target capacity. |
| `LinearExperiment` | `atol` | `float` | output value | Absolute binary64 acceptance tolerance [output value]; integers compare exactly. |
| `LinearExperiment` | `rtol` | `float` | 1 | Relative binary64 acceptance tolerance [1]; integers compare exactly. |
| `LinearStudy` | `workload` | `LinearSpec` | —（结构/对象） | Shared task; all candidates compare the same actual operands. |
| `LinearStudy` | `hardware` | `LinearHardware` | —（结构/对象） | Shared resource budget and service rates. |
| `LinearStudy` | `candidates` | `tuple[MappingCandidate, ...]` | —（结构/对象） | Finite candidate list, including infeasible cases. |
| `LinearStudy` | `seed` | `int` | 1 | SHA256-index-v1 generation seed [1]; unsigned 64-bit. |
| `LinearStudy` | `max_macs` | `int` | MAC | Host execution/reference bound [MAC]. |
| `LinearStudy` | `atol` | `float` | output value | Absolute output quality tolerance [output value]. |
| `LinearStudy` | `rtol` | `float` | 1 | Relative output quality tolerance [1]. |
| `LinearStudy` | `schema_version` | `Literal['linear-study/v1']` | —（结构/对象） | JSON study schema version. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `LinearHardware` | Explicit single scratch/MAC/DMA capability assumption; throughput is valid only for the declared dtype. |
| `MappingCandidate` | One candidate is explicit; unsuccessful capacity checks remain part of the comparison. |
| `LinearExperiment` | Functional work limit and quality thresholds are declared, not hidden hardware parameters. |
| `LinearStudy` | Study-level generation and finite candidate enumeration; direct evaluate_mapping accepts explicit data. |
| `evaluate_mapping(params: LinearExperiment, inputs: LinearInputs)` | Validate numerics, count actual row payloads, and query isolated resource service; this is not event simulation. |
| `run_study(study: LinearStudy, *, source_revision: str='unrecorded')` | Execute a finite comparison with identical data/budget; callback failures are retained as failed RunRecords. |
| `summarize_records(records: tuple[RunRecord, ...])` | Rebuild comparison rows solely from immutable records; execution success and numerical quality stay separate. |

### [memory.py](memory.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `MemoryWork` | `accesses` | `tuple[MemoryAccess, ...]` | —（结构/对象） | DRAM单请求或cache有序byte访问。 |
| `MemoryWork` | `nand_requests` | `tuple[NandReadRequest, ...]` | —（结构/对象） | NAND有序page/data/OOB列请求。 |
| `MemoryWork` | `row_state` | `Literal['hit', 'closed', 'conflict'] \| None` | —（结构/对象） | DRAM每行片段的隔离起点条件。 |
| `MemoryWork` | `single_row` | `bool` | 1（布尔） | DRAM单行API；True时越行必须失败。 |
| `MemoryWork` | `flush` | `bool` | 1（布尔） | Cache窗口末显式写回dirty行；默认保留dirty状态。 |
| `MemoryCase` | `name` | `str` | 1（标识/枚举） | 完整研究内唯一案例身份。 |
| `MemoryCase` | `group` | `str` | 1（标识/枚举） | 一组共享研究问题的基线/消融/边界案例。 |
| `MemoryCase` | `family` | `Literal['dram', 'cached_dram', 'nand']` | —（结构/对象） | 已实现的三个调用边界。 |
| `MemoryCase` | `role` | `Literal['baseline', 'resource_ablation', 'access_comparison', 'boundary']` | —（结构/对象） | 单参数资源变化与访问/边界变化分开。 |
| `MemoryCase` | `profile` | `DramReadProfile \| NandReadProfile` | —（结构/对象） | 外存资源来源、几何、时钟/接口和成本。 |
| `MemoryCase` | `work` | `MemoryWork` | —（结构/对象） | 真实访问及显式策略，研究固定冷cache/NAND buffer初态。 |
| `MemoryCase` | `cache` | `CacheParams \| None` | —（结构/对象） | cached_dram必需；其他家族不得附加未使用缓存。 |
| `MemoryStudy` | `cases` | `tuple[MemoryCase, ...]` | —（结构/对象） | 完整有限案例名单，含失败/未知结果。 |
| `MemoryStudy` | `schema_version` | `Literal['memory-access-study/v1']` | —（结构/对象） | 参数与比较语义版本。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `MemoryWork` | 访问与策略边界；DRAM行状态条件不是由缓存命中推导。 |
| `MemoryCase` | family选择已有专业入口；资源profile可独立替换，配置没有可执行字符串。 |
| `MemoryStudy` | 一组一个基线；资源消融仅改一个数值，访问对照固定全部资源。 |
| `run_study(study: MemoryStudy, *, source_revision: str='unrecorded')` | 每次运行保留完整名单、输入、初态、条件和版本；模型异常转换为failed记录。 |
| `summarize_records(records: tuple[RunRecord, ...])` | 回读检查同一研究/版本、真实输入和完整名单；保留失败与所有未知成本。 |
| `write_study(records: tuple[RunRecord, ...], directory: str \| Path)` | 先写哈希校验bundle，再写固定相对路径索引；已有目录不覆盖。 |
| `read_study(directory: str \| Path)` | 回读不运行模型；路径、索引、输入身份与完整比较协议必须一致。 |

### [physical.py](physical.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `PhysicalCase` | `name` | `str` | 1（标识/枚举） | 全研究唯一案例名。 |
| `PhysicalCase` | `group` | `str` | 1（标识/枚举） | 一个基线及其敏感性/反例集合。 |
| `PhysicalCase` | `role` | `Literal['baseline', 'geometry', 'observation', 'thermal', 'pvt', 'activity', 'boundary']` | —（结构/对象） | 明确允许变化因素。 |
| `PhysicalCase` | `model` | `PhysicalModel` | —（结构/对象） | 唯一资源、结构/PVT、面积计量和几何约束。 |
| `PhysicalCase` | `work` | `PhysicalWork` | —（结构/对象） | 动作账本、覆盖缺口及外部观测窗口。 |
| `PhysicalCase` | `table` | `CostTable` | —（结构/对象） | 明确来源/单位/条件与误差未知状态。 |
| `PhysicalCase` | `thermal` | `ThermalTrace \| None` | —（结构/对象） | 可选外部总功率驱动的单节点轨迹。 |
| `PhysicalStudy` | `cases` | `tuple[PhysicalCase, ...]` | —（结构/对象） | 完整研究名单，含未知结果与失败反例。 |
| `PhysicalStudy` | `schema_version` | `Literal['physical-evidence-study/v1']` | —（结构/对象） | 配置/比较语义版本。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `PhysicalCase` | 一个固定来源表下的物理情景；输入工作与模型/功率条件分别保存。 |
| `PhysicalStudy` | 每组一基线；查询表与来源固定，避免把换成本数据误作方案收益。 |
| `run_study(study: PhysicalStudy, *, source_revision: str='unrecorded')` | 来源/PVT/完整名单和工作进入身份，失败分析不丢弃。 |
| `summarize_records(records: tuple[RunRecord, ...])` | 完整同源名单和实际输入校验，保留全部来源、失败与未知值。 |
| `write_study(records: tuple[RunRecord, ...], directory: str \| Path)` | 先写哈希bundle，再写固定相对路径索引；不覆盖已有实验目录。 |
| `read_study(directory: str \| Path)` | 回读只核对工件/输入身份和完整协议，不运行物理模型。 |

### [retrieval.py](retrieval.py)

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `prepare_retrieval(profile: RetrievalProfile, data: ClassificationData, seed: int)` | Prepare actual source data/model/selection once per seed; no held-out test label participates in fitting or selection. |
| `evaluate_retrieval(config: dict, prepared: dict)` | Compare actual mapped arithmetic to the oracle, then evaluate held-out task quality and optional two-form NumPy evidence. |
| `run_study(profile: RetrievalProfile, *, data_root: str \| Path, source_revision: str='unrecorded', numpy_reference: bool=False)` | Retain every split/variant including data/selection/tool failures; the optional backend version is part of configuration identity. |
| `summarize_records(records: tuple[RunRecord, ...])` | Summarize complete paired cases without fitting/selection/reference or external-data access; validate recorded metrics from observations. |
| `write_study(records: tuple[RunRecord, ...], directory: str \| Path)` | Preserve a complete immutable task-quality bundle, including failed executions and negative controls. |
| `read_study(directory: str \| Path)` | Read verified saved observations; NumPy and original dataset files are unnecessary for replay. |

### [single.py](single.py)

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `run_experiment(spec: ExperimentSpec, configuration: P, inputs: I, execute: Callable[[P, I], tuple[R, tuple[Metric, ...]]])` | Snapshot explicit inputs, invoke a fresh copied boundary, and record success/failure without hidden stages. |

### [system.py](system.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `NodeCase` | `name` | `str` | 1（标识/枚举） | Unique case identity in this finite study. |
| `NodeCase` | `request` | `PathRequest` | —（结构/对象） | Source/target operation and explicit or searched route. |
| `NodeCase` | `expected_status` | `Literal['succeeded', 'failed']` | —（结构/对象） | Expected execution outcome, independently checked after recording. |
| `NodeStudy` | `node` | `NodeSpec` | —（结构/对象） | Fixed complete node ownership, model references, capabilities and connectivity. |
| `NodeStudy` | `cases` | `tuple[NodeCase, ...]` | —（结构/对象） | Complete finite success/failure roster. |
| `NodeStudy` | `schema_version` | `Literal['system-connectivity/v1']` | —（结构/对象） | Static node-path study. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `NodeCase` | Each case asks one operation/path question; expected failure is a reviewed fixture condition, not suppressed evidence. |
| `NodeStudy` | All cases share one sourced node; studies compare access feasibility, not measured hardware performance. |
| `run_study(study: NodeStudy, *, source_revision: str='unrecorded')` | Each request creates an independent terminal record with the full node/case roster and immutable input snapshot. |
| `summarize_records(records: tuple[RunRecord, ...])` | Recheck saved route legality and roster consistency without search, hardware analysis or target execution. |
| `write_study(records: tuple[RunRecord, ...], directory: str \| Path)` | Commit the complete checked study once; existing evidence directories are never overwritten. |
| `read_study(directory: str \| Path)` | Rebuild route observations from saved structure alone; no execution callback or path search is needed. |

### [system_ai.py](system_ai.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `AiTask` | `task_id` | `str` | 1（标识/枚举） | Unique task identity, shared by its placement/policy comparison group. |
| `AiTask` | `seed` | `int` | 1 | Deterministic input seed [1], uint64. |
| `AiTask` | `linear` | `LinearSpec \| None` | —（结构/对象） | Dense Linear task; exactly one task kind is provided. |
| `AiTask` | `training` | `TrainingSpec \| None` | —（结构/对象） | Dense MSE/SGD chain, including gradient and next-state checks. |
| `AiTask` | `attention` | `AttentionSpec \| None` | —（结构/对象） | Attention/GQA/KV task with explicit numerical semantics. |
| `AiCase` | `name` | `str` | 1（标识/枚举） | Unique candidate identity. |
| `AiCase` | `task_id` | `str` | 1（标识/枚举） | Existing shared task. |
| `AiCase` | `strategy` | `str` | 1（标识/枚举） | resident, direct or staged complete input-buffer preparation. |
| `AiCase` | `bandwidth_scale` | `float` | 1 | Multiplicative change to one declared shared service ceiling [1], positive. |
| `AiCase` | `startup_scale` | `int` | 1 | Multiplicative DMA startup-cycle intervention [1], positive. |
| `AiCase` | `expected_status` | `str` | 1（标识/枚举） | Reviewed feasibility expectation. |
| `AiStudy` | `system` | `DmaSystem` | —（结构/对象） | Physical node resources and local service source. |
| `AiStudy` | `source_backing_id` | `str` | 1（标识/枚举） | Initial remote device storage for direct/staged policies. |
| `AiStudy` | `target_backing_id` | `str` | 1（标识/枚举） | Compute device's backing for inputs plus conservative workspace reservation. |
| `AiStudy` | `staging_backing_id` | `str` | 1（标识/枚举） | Host backing used only by staged policy. |
| `AiStudy` | `shared_resource_id` | `str` | 1（标识/枚举） | Declared payload ceiling changed by explicit bandwidth sensitivity cases. |
| `AiStudy` | `scratch_capacity_bytes` | `int` | B | Separate compute-local scratch arena [B], checked by existing compiler models. |
| `AiStudy` | `compute_capacity_macs_s` | `float` | MAC/s | MAC-only service ceiling [MAC/s] for target owner; scalar/softmax service remains unknown. |
| `AiStudy` | `compute_source_ref` | `str` | 1（标识/枚举） | Compute/scratch assumption or calibration provenance. |
| `AiStudy` | `tasks` | `tuple[AiTask, ...]` | —（结构/对象） | Task roster; no comparison of different tasks as a speedup. |
| `AiStudy` | `cases` | `tuple[AiCase, ...]` | —（结构/对象） | Complete policies, sensitivities and infeasible tasks. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `AiTask` | Task semantics are replaceable; small deterministic inputs exercise exact compute and node-demand linkage. |
| `AiCase` | Bandwidth/startup changes are explicit sensitivity interventions, separate from same-budget strategy comparisons. |
| `AiStudy` | Fixed memory/DMA budget and declared compute/scratch service; input copies and workspace are derived from each task. |
| `task_inputs(task: AiTask)` | Store actual deterministic operands/state; all strategy cases for one task use identical values and versions. |
| `task_evidence(study: AiStudy, task: AiTask, inputs: dict, saved: dict \| None=None)` | Execute mapped numerics or verify saved numerics with an independent reference; derive actual operand/backing/scratch demand. |
| `case_hardware(study: AiStudy, case: AiCase)` | Derive and record the exact single-resource and startup interventions; unchanged cases retain original hardware identity. |
| `map_task(study: AiStudy, case: AiCase, evidence: dict)` | Reserve packed input copies and conservative compute workspace, with full-buffer staging only for the staged policy. |
| `analyze_ai(study: AiStudy, case: AiCase, inputs: dict, saved: dict \| None=None)` | Link checked task values to exact byte demand and node work; compute and transfer ceilings are necessary bounds only. |
| `run_study(study: AiStudy, *, source_revision: str='unrecorded')` | Save actual input tensors/state and full common budget for every successful or failed candidate. |
| `summarize_records(records: tuple[RunRecord, ...])` | Replay saved actual numerics against independent references and saved DMA routes without mapped execution or a new search. |
| `write_study(records: tuple[RunRecord, ...], directory: str \| Path)` | Save one verified complete task/policy/sensitivity study without overwriting previous evidence. |
| `read_study(directory: str \| Path)` | Recover records and recheck independent numeric/static evidence, retaining prior failure diagnostics. |

### [system_memory.py](system_memory.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `MemoryCase` | `name` | `str` | 1（标识/枚举） | Unique identity in the complete finite study. |
| `MemoryCase` | `plan` | `MemoryPlan` | —（结构/对象） | Full demand/copies/views; infeasibility is recorded by execution. |
| `MemoryCase` | `request` | `MemoryAccessRequest \| None` | —（结构/对象） | None checks placement only, without any path claim. |
| `MemoryCase` | `expected_status` | `Literal['succeeded', 'failed']` | —（结构/对象） | Reviewed fixture expectation, not evidence by itself. |
| `MemoryStudy` | `memory` | `MemorySystem` | —（结构/对象） | Fixed resource ownership, capacity, topology and NUMA placement. |
| `MemoryStudy` | `cases` | `tuple[MemoryCase, ...]` | —（结构/对象） | Complete roster including negative controls and placement-only cases. |
| `MemoryStudy` | `schema_version` | `Literal['system-memory-study/v1']` | —（结构/对象） | Static analysis evidence. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `MemoryCase` | Each case declares one complete candidate placement and optionally one live address-access question. |
| `MemoryStudy` | One sourced memory system is shared by all cases; task/budget equivalence must be stated per comparison. |
| `run_study(study: MemoryStudy, *, source_revision: str='unrecorded')` | Snapshot the full hardware/roster and preserve every success or failure independently of fixture expectations. |
| `summarize_records(records: tuple[RunRecord, ...])` | Recheck static intervals/mappings/locality and the saved explicit route; do not invoke the producer or search for paths. |
| `write_study(records: tuple[RunRecord, ...], directory: str \| Path)` | Commit checked immutable records and their manifest once; do not overwrite prior research evidence. |
| `read_study(directory: str \| Path)` | Validate saved data and declared static semantics only; failure diagnostics remain observations, not rerun proofs. |

### [system_network.py](system_network.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `NodeWork` | `node_id` | `str` | 1（标识/枚举） | Existing physical node identity. |
| `NodeWork` | `nic` | `NicBatch \| None` | —（结构/对象） | Inter-node flows with explicit supply/drain buffers. |
| `NodeWork` | `local` | `CopyBatch \| None` | —（结构/对象） | Same-node messages served entirely by local DMA; no network charge. |
| `MessageBinding` | `message_id` | `str` | 1（标识/枚举） | Exact cluster traffic identity. |
| `MessageBinding` | `tx_flow_id` | `str \| None` | 1（标识/枚举） | Source-node NIC flow for an inter-node message. |
| `MessageBinding` | `rx_flow_id` | `str \| None` | 1（标识/枚举） | Destination-node NIC flow for an inter-node message. |
| `MessageBinding` | `local_chain_id` | `str \| None` | 1（标识/枚举） | Same-node copy chain, mutually exclusive with NIC flow IDs. |
| `NetworkCase` | `name` | `str` | 1（标识/枚举） | Unique candidate identity. |
| `NetworkCase` | `traffic` | `TrafficInput` | —（结构/对象） | Exact simultaneous messages; remote routes must be explicit for deterministic replay. |
| `NetworkCase` | `nodes` | `tuple[NodeWork, ...]` | —（结构/对象） | One shared batch per active node. |
| `NetworkCase` | `bindings` | `tuple[MessageBinding, ...]` | —（结构/对象） | Complete message-to-service roster. |
| `NetworkCase` | `expected_status` | `str` | 1（标识/枚举） | Reviewed expectation, separate from actual feasibility. |
| `NetworkStudy` | `systems` | `tuple[NicSystem, ...]` | —（结构/对象） | Node hardware, uniquely identified by topology scope. |
| `NetworkStudy` | `cluster` | `ClusterSpec` | —（结构/对象） | Fabric graph, exact exported endpoints/capacities and rank placements. |
| `NetworkStudy` | `cases` | `tuple[NetworkCase, ...]` | —（结构/对象） | Complete success/failure study. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `NodeWork` | One node's simultaneous local work must be analyzed in a single batch to conserve shared demand and hazards. |
| `MessageBinding` | Each P2P message binds both node endpoints or one entirely local whole-copy chain. |
| `NetworkCase` | Every candidate uses the same node/fabric hardware; only demand and explicit paths/buffers vary. |
| `NetworkStudy` | Hardware assembly joins actual standard-library endpoint exports, preserving one authoritative NIC budget. |
| `analyze_network(study: NetworkStudy, case: NetworkCase, saved: dict \| None=None)` | Compose supply/drain, NIC and fabric necessary bounds by max; no completed-message or overlap schedule is inferred. |
| `run_study(study: NetworkStudy, *, source_revision: str='unrecorded')` | Preserve the full hardware/budget and candidate roster in every record. |
| `summarize_records(records: tuple[RunRecord, ...])` | Replay declarations and exact saved local routes; no producer or fabric path selection runs. |
| `write_study(records: tuple[RunRecord, ...], directory: str \| Path)` | Save only a complete verified study into a fresh output directory. |
| `read_study(directory: str \| Path)` | Read immutable observations and validate static accounting without a new experiment callback. |

### [system_tiering.py](system_tiering.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `TierCase` | `name` | `str` | 1（标识/枚举） | Unique candidate identity in the complete finite study. |
| `TierCase` | `placement` | `MemoryPlan` | —（结构/对象） | Initial static placement; must equal migration.before when a migration is requested. |
| `TierCase` | `phase` | `int` | —（结构/对象） | Shared logical phase for initial usage, native accesses and all migration snapshots. |
| `TierCase` | `access` | `CxlAccessRequest \| None` | —（结构/对象） | Optional native access query, mutually exclusive with migration. |
| `TierCase` | `migration` | `TierMigration \| None` | —（结构/对象） | Explicit before/overlap/after transition. |
| `TierCase` | `cxl_copy` | `CxlCopyRequest \| None` | —（结构/对象） | Native host-copy transport for a migration. |
| `TierCase` | `dma_copy` | `CopyBatch \| None` | —（结构/对象） | Compatible existing S3 transport for a migration. |
| `TierCase` | `expected_status` | `Literal['succeeded', 'failed']` | —（结构/对象） | Reviewed fixture expectation, separate from actual status. |
| `TierStudy` | `system` | `TieredMemorySystem` | —（结构/对象） | Complete physical tier assignment. |
| `TierStudy` | `cxl` | `CxlMemorySystem` | —（结构/对象） | Native capability/decoder assembly on the same MemorySystem. |
| `TierStudy` | `cases` | `tuple[TierCase, ...]` | —（结构/对象） | Complete success/failure roster. |
| `TierStudy` | `dma` | `DmaSystem \| None` | —（结构/对象） | Optional compatible PCIe/DMA assembly; not a CXL.mem protocol implementation. |
| `TierStudy` | `schema_version` | `Literal['system-tiering-study/v1']` | —（结构/对象） | Static residency/access/transition evidence. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `TierCase` | Each case checks one placement and optionally native access or exactly one explicitly transported migration. |
| `TierStudy` | Every candidate uses the same physical hardware; changing a placement never invents new capacity or protocol capability. |
| `run_study(study: TierStudy, *, source_revision: str='unrecorded')` | Preserve complete hardware, all cases and selected input for every success/failure independently of fixture expectation. |
| `summarize_records(records: tuple[RunRecord, ...])` | Recheck roster/source and all saved static evidence without producer execution; failed diagnostics remain prior observations. |
| `write_study(records: tuple[RunRecord, ...], directory: str \| Path)` | Commit one complete checked study into a new immutable output directory. |
| `read_study(directory: str \| Path)` | Decode records and verify saved static evidence without creating a new execution or data-transfer claim. |

### [system_transfer.py](system_transfer.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `TransferCase` | `name` | `str` | 1（标识/枚举） | Unique case identity, including negative controls. |
| `TransferCase` | `batch` | `CopyBatch` | —（结构/对象） | Full placement, logical phase and ordered whole-copy chains. |
| `TransferCase` | `expected_status` | `Literal['succeeded', 'failed']` | —（结构/对象） | Fixture expectation checked separately from execution status. |
| `TransferStudy` | `system` | `DmaSystem` | —（结构/对象） | Fixed, sourced hardware capacities and packet/DMA service assumptions. |
| `TransferStudy` | `cases` | `tuple[TransferCase, ...]` | —（结构/对象） | Complete finite candidate roster. |
| `TransferStudy` | `schema_version` | `Literal['system-transfer-study/v1']` | —（结构/对象） | Analytical posted-write/whole-copy study. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `TransferCase` | One candidate retains its full source/destination/staging placement and finite independent copy chains. |
| `TransferStudy` | All cases share one complete memory/channel/fabric budget; specific comparisons must also match useful task bytes. |
| `run_study(study: TransferStudy, *, source_revision: str='unrecorded')` | Save exact hardware, full roster and selected batch on every attempt; expectations never suppress failures. |
| `summarize_records(records: tuple[RunRecord, ...])` | Reanalyze exact saved routes/bytes/dependencies under the same source; no producer callback or path search executes. |
| `write_study(records: tuple[RunRecord, ...], directory: str \| Path)` | Preserve one complete validated study in an immutable directory; never overwrite existing evidence. |
| `read_study(directory: str \| Path)` | Read exact stored observations and recheck their static semantics without producing a new execution. |

### [tile_mapping.py](tile_mapping.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `LinearTileBackend` | `tile` | `DigitalTile` | —（结构/对象） | 独立可调用的 MAC/SRAM/DMA/路径组合。 |
| `LinearTileBackend` | `external_memory_id` | `str` | 1（标识/枚举） | 外部 A/B/C 数据所在资源 ID。 |
| `LinearTileBackend` | `channel_id` | `str` | 1（标识/枚举） | 本研究使用的单个串行 DMA 通道 ID。 |
| `LinearTileBackend` | `profile_source` | `str` | 1（标识/枚举） | 服务参数来源/假设版本；未校准不能标成实测。 |
| `LinearTileBackend` | `load_path` | `tuple[str, ...]` | 1（标识/枚举） | 外部到 scratch 的固定有向路径。 |
| `LinearTileBackend` | `store_path` | `tuple[str, ...]` | 1（标识/枚举） | scratch 到外部的固定有向路径。 |
| `LinearTileBackend` | `access_policy` | `Literal['scalar-ab-register-c/v1']` | —（结构/对象） | 每 MAC 各读 A/B；每 K slice 在寄存器累加 C。 |
| `LinearTileBackend` | `max_local_accesses` | `int` | request | 显式本地请求的宿主展开上限 [request]，非目标硬件预算。 |
| `LinearTileBackend` | `external_read_row_state` | `Literal['hit', 'closed', 'conflict'] \| None` | —（结构/对象） | DRAM每次load的条件行状态；非DRAM资源为None。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `LinearTileBackend` | 可替换的本地硬件适配；现阶段仅支持一个有明确复用语义的标量访问映射。 |
| `map_linear_tile(backend: LinearTileBackend, spec: LinearSpec, plan: LinearPlan, memory: LinearMemory, traffic: LinearTraffic)` | Packed A/B/C arenas: no A/B broadcast, scalar C register residency only within each K update. |

### [training.py](training.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `TrainingExperiment` | `workload` | `TrainingSpec` | —（结构/对象） | Chain dimensions and activation semantics. |
| `TrainingExperiment` | `hardware` | `LinearHardware` | —（结构/对象） | GEMM-only MAC/DMA assumptions and scratch capacity. |
| `TrainingExperiment` | `candidate` | `MappingCandidate` | —（结构/对象） | Same maximum tile/policy applied to each actual contraction shape. |
| `TrainingExperiment` | `backing_capacity_bytes` | `int` | B | Packed named tensors' separate backing-store budget [B]. |
| `TrainingExperiment` | `learning_rate` | `float` | —（结构/对象） | Plain SGD learning rate; finite >=0. |
| `TrainingExperiment` | `max_macs` | `int` | MAC | Full-step GEMM host work limit [MAC], not per-layer capacity. |
| `TrainingExperiment` | `atol` | `float` | value | Absolute output/gradient/update acceptance tolerance [value]. |
| `TrainingExperiment` | `rtol` | `float` | 1 | Relative acceptance tolerance [1]. |
| `TrainingExperiment` | `reference_backend` | `Literal['exact', 'pytorch']` | —（结构/对象） | Explicit optional reference, never dynamic import text. |
| `TrainingStudy` | `workload` | `TrainingSpec` | —（结构/对象） | Shared semantics and loss definition. |
| `TrainingStudy` | `hardware` | `LinearHardware` | —（结构/对象） | Shared declared resource capability and scratch. |
| `TrainingStudy` | `candidates` | `tuple[MappingCandidate, ...]` | —（结构/对象） | Explicit finite mapping list, including infeasible points. |
| `TrainingStudy` | `backing_capacity_bytes` | `int` | B | Shared named-tensor memory budget [B]. |
| `TrainingStudy` | `learning_rate` | `float` | —（结构/对象） | Shared plain SGD rate. |
| `TrainingStudy` | `seed` | `int` | uint64 | Training SHA256-index-v1 seed [uint64]. |
| `TrainingStudy` | `max_macs` | `int` | MAC | Full-step host functional/reference work bound [MAC]. |
| `TrainingStudy` | `atol` | `float` | value | Absolute numerical tolerance [value]. |
| `TrainingStudy` | `rtol` | `float` | 1 | Relative numerical tolerance [1]. |
| `TrainingStudy` | `schema_version` | `Literal['training-study/v1']` | —（结构/对象） | Study configuration version. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `TrainingExperiment` | One mapping has two distinct storage budgets and explicit numerical/reference settings. |
| `TrainingStudy` | A finite study resets every candidate to identical old weights/data; this is not sequential SGD across candidates. |
| `evaluate_training(params: TrainingExperiment, inputs: tuple[TrainingState, TrainingInputs])` | Compare the whole step; only the GEMM subset has target service estimates, while full-step time remains unknown. |
| `run_training_study(study: TrainingStudy, *, source_revision: str='unrecorded', reference_backend: str='exact')` | Freeze the actual reference environment in run identity and preserve failed candidates as independent attempts. |
| `summarize_training(records: tuple[RunRecord, ...])` | Reconstruct comparison rows from verified run records without rerunning training or importing an external framework. |

### [workload.py](workload.py)

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `run_study(suite: AttentionSuite, *, data_root: str \| Path, source_revision: str='unrecorded')` | Prepare actual input snapshots before the callback; preparation errors become records without invented input data. |
| `summarize_records(records: tuple[RunRecord, ...])` | Check semantic identity, complete roster and source consistency without regenerating inputs or executing the reference. |
| `write_study(records: tuple[RunRecord, ...], directory: str \| Path)` | Commit the immutable bundle roster only after all records are written; never overwrite previous evidence. |
| `read_study(directory: str \| Path)` | Read only local indexed bundles, rejecting omissions, duplicate identities and arbitrary paths; source data files are unnecessary. |

<!-- model-fields:end -->

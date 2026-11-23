# runner：独立调用与有限线性映射比较

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

<!-- model-fields:start -->

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

### [linear.py](linear.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `LinearHardware` | `operand_dtype` | `Literal['int8', 'float64']` | —（结构/对象） | Supported operand format; matching 64-bit accumulation/output assumed. |
| `LinearHardware` | `scratch_capacity_bytes` | `int` | B | Shared A/B/C scratch capacity [B]; >0. |
| `LinearHardware` | `compute_clock` | `ClockDomain` | Hz | MAC clock f_compute [Hz]; distinct from transfer clock. |
| `LinearHardware` | `mac` | `PipelineParams` | lane, cycle | MAC lanes P and service L/II [lane, cycle]; supplied assumptions, not calibration. |
| `LinearHardware` | `dma_clock` | `ClockDomain` | Hz | Single DMA channel clock f_dma [Hz]. |
| `LinearHardware` | `dma` | `DmaParams` | —（结构/对象） | Row-request DMA service parameters; external DRAM/NoC are not added implicitly. |
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

### [single.py](single.py)

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `run_experiment(spec: ExperimentSpec, configuration: P, inputs: I, execute: Callable[[P, I], tuple[R, tuple[Metric, ...]]])` | Snapshot explicit inputs, invoke a fresh copied boundary, and record success/failure without hidden stages. |

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

<!-- model-fields:end -->

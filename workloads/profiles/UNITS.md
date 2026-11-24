# profiles：有限 Attention 案例与宿主预算

`AttentionCase` 绑定名称、问题、完整 spec 与生成 seed 或 dataset；`AttentionSuite` 冻结完整唯一案例名单和共享预算。`prepare_attention` 仅生成/加载实际输入，不执行参考或硬件。无请求队列、统计到达过程和物理计量。

seed 是 uint64；选择 dataset 时 seed 必须为 None，生成版本 attention-input/v1 使用不同Q/K/V标签的SHA256有界值。expected_status 是预审夹具结果，不覆盖真实运行状态。suite_id/source_note 保留选择依据；当前默认10例明确为合成验证，不代表模型库或服务分布。

max_elements [element] 检查Q/K/V材料化总数；max_score_pairs [pair]、max_macs [MAC]、precision_digits [digit] 由参考消费，max_file_bytes [B] 由loader消费。这些是关键宿主预算，不映射为硬件资源。顺序为构造/严格配置 → 校验案例成员和输入规模 → prepare → 调用方选择参考或映射。完整参数关系见[kernels](../kernels/UNITS.md)，来源见[datasets](../datasets/UNITS.md)，[测试](../../tests/workloads/test_profiles.py)验证名单、类型、确定性、来源与预算。

## 真实任务有限协议

`retrieval.py`维护RetrievalVariant和RetrievalProfile：同一真实source、完整seed、train/validation每类配额、固定scale候选、数值变体、最低准确率与最大下降门槛。恰有一个unrounded baseline，coarse负对照expected_quality=False仍需执行成功和数值正确。query_tile、scratch/backing容量是本实验的显式映射参数，max_samples/file_bytes/MAC/score限制宿主规模。profiles不选择外部软件后端，NumPy选择由evaluation记录。来源、方程、完整12例与约束见[W5指南](../docs/mapping_and_quality.md)。

<!-- model-fields:start -->

### [attention.py](attention.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `AttentionCase` | `name` | `str` | 1（标识/枚举） | Unique case identifier within the suite. |
| `AttentionCase` | `spec` | `AttentionSpec` | —（结构/对象） | Complete mathematical task; names such as decode do not override its semantics. |
| `AttentionCase` | `purpose` | `str` | 1（标识/枚举） | Research/verification question and source assumption for this scenario. |
| `AttentionCase` | `seed` | `int \| None` | —（结构/对象） | attention-input/v1 uint64 seed; None iff a dataset is selected. |
| `AttentionCase` | `dataset` | `AttentionDataset \| None` | —（结构/对象） | Explicit local data provenance; mutually exclusive with seed generation. |
| `AttentionCase` | `expected_status` | `Literal['succeeded', 'failed']` | —（结构/对象） | Reviewed fixture expectation, never the actual outcome. |
| `AttentionSuite` | `suite_id` | `str` | 1（标识/枚举） | Workload-suite/revision identity. |
| `AttentionSuite` | `source_note` | `str` | 1（标识/枚举） | Provenance and representativeness boundary for the case selection. |
| `AttentionSuite` | `cases` | `tuple[AttentionCase, ...]` | —（结构/对象） | Complete ordered case list, including expected failures. |
| `AttentionSuite` | `precision_digits` | `int` | digit | Host Decimal reference precision [digit], 32..256. |
| `AttentionSuite` | `max_elements` | `int` | element | Maximum materialized input elements [element], not target memory capacity. |
| `AttentionSuite` | `max_score_pairs` | `int` | pair | Host full probability-matrix limit [pair]. |
| `AttentionSuite` | `max_macs` | `int` | MAC | Host reference visible-pair contraction limit [MAC]. |
| `AttentionSuite` | `max_file_bytes` | `int` | B | Maximum local dataset file bytes read/parsed [B]. |
| `AttentionSuite` | `schema_version` | `Literal['attention-suite/v1']` | —（结构/对象） | Versioned finite-suite semantics. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `AttentionCase` | One scenario is a task/input choice; differing shapes are not automatically comparable hardware speedups. |
| `AttentionSuite` | Fixed finite roster and budgets; no unrecorded sampling, arrival scheduler or implicit model-zoo presets. |
| `prepare_attention(case: AttentionCase, suite: AttentionSuite, *, data_root: str \| Path)` | Shared preparation enforces the same shape/materialization bounds for generated and file-backed inputs. |

### [retrieval.py](retrieval.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `RetrievalVariant` | `name` | `str` | 1（标识/枚举） | Unique numeric-policy label. |
| `RetrievalVariant` | `key_decimals` | `int \| None` | -2,12 | Decimal rounding places [-2,12]; None preserves standardized support values. |
| `RetrievalVariant` | `expected_quality` | `bool` | 1（布尔） | Reviewed quality-gate expectation, separate from execution status. |
| `RetrievalProfile` | `source` | `TabularSource` | —（结构/对象） | Original real dataset and exact byte/source metadata. |
| `RetrievalProfile` | `seeds` | `tuple[int, ...]` | uint64 | Complete unique finite split seed roster [uint64]. |
| `RetrievalProfile` | `train_per_class` | `int` | sample | Support and normalization samples per class [sample]. |
| `RetrievalProfile` | `validation_per_class` | `int` | sample | Scale-selection samples per class [sample]; all remaining rows are test. |
| `RetrievalProfile` | `scale_candidates` | `tuple[float, ...]` | 1 | Fixed positive RBF inverse-bandwidth grid [1], selected on validation accuracy. |
| `RetrievalProfile` | `variants` | `tuple[RetrievalVariant, ...]` | —（结构/对象） | Complete numeric ablation roster, exactly one unrounded baseline. |
| `RetrievalProfile` | `minimum_accuracy` | `float` | 1 | Held-out absolute accuracy requirement [1], fixed before execution. |
| `RetrievalProfile` | `maximum_accuracy_drop` | `float` | 1 | Allowed degradation from same-split unrounded baseline [1]. |
| `RetrievalProfile` | `query_tile` | `int` | sample | Query rows per fused shared-KV mapping block [sample]. |
| `RetrievalProfile` | `scratch_capacity_bytes` | `int` | B | Explicit analytic scratch reservation budget [B], not a measured device. |
| `RetrievalProfile` | `backing_capacity_bytes` | `int` | B | Explicit analytic original/temporary backing budget [B]. |
| `RetrievalProfile` | `max_samples` | `int` | sample | Local dataset materialization guard [sample]. |
| `RetrievalProfile` | `max_file_bytes` | `int` | B | Local source byte limit [B]. |
| `RetrievalProfile` | `max_macs` | `int` | MAC | Per-Attention reference/interpreter contraction guard [MAC]. |
| `RetrievalProfile` | `max_score_pairs` | `int` | pair | Per-reference probability storage limit [pair]. |
| `RetrievalProfile` | `schema_version` | `str` | 1（标识/枚举） | Standardization, RBF, split, selection and quality-gate protocol. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `RetrievalVariant` | Rounding changes stored support coordinates, not input storage dtype or inferred packed hardware capacity. |
| `RetrievalProfile` | Repeated held-out splits are paired comparisons, not independent population samples or a language-model workload. |

<!-- model-fields:end -->

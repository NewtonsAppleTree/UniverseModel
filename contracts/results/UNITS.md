# results：实验说明、指标与运行记录

ExperimentSpec 声明执行模式/版本/代码来源/假设；Metric 描述有单位和依据的数值；RunRecord 保存输入/输出快照与终态。它们不维护队列，不判定算法精度。

最关心 `mode`、`kind`、`clock_domain`、未知原因与内容身份：`H=hash(spec, configuration, inputs)`；host wall time 与 run_id 不进入输入身份。同一 name 的指标不可重复。simulated 指标仅允许 event 模式；cycle 必须标域。

使用：构造 Spec 与 Metric → producer 运行 → RunRecord → `to_dict/from_dict`。快照是 canonical JSON 字符串，读取视图可变但不反向修改记录；failed 不携带完整输出/指标。字段以生成表为准，测试见[工程测试](../../tests/integration/test_framework.py)。

<!-- model-fields:start -->

### [experiment.py](experiment.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `ExperimentSpec` | `experiment_id` | `str` | 1（标识/枚举） | Experiment identity; no physical unit. |
| `ExperimentSpec` | `implementation_id` | `str` | 1（标识/枚举） | Explicit adapter/model version; never a dynamic import path. |
| `ExperimentSpec` | `mode` | `Literal['functional', 'analytical', 'static_schedule', 'event']` | —（结构/对象） | Target result semantics. |
| `ExperimentSpec` | `source_revision` | `str` | 1（标识/枚举） | Code revision/source reference; 'unrecorded' means incomplete provenance. |
| `ExperimentSpec` | `assumptions` | `tuple[str, ...]` | 1（标识/枚举） | Applicability and coverage statements; immutable text. |
| `ExperimentSpec` | `schema_version` | `Literal['universal-experiment/v1']` | —（结构/对象） | Public schema ID. |
| `Metric` | `name` | `str` | 1（标识/枚举） | Metric identity within one run; unique, e.g. completion_time. |
| `Metric` | `value` | `int \| float \| None` | —（结构/对象） | Numeric observation/estimate; None denotes unknown, never zero. |
| `Metric` | `unit` | `str` | 1（标识/枚举） | Canonical unit token, e.g. second, byte, MAC, conversion; no implicit conversion. |
| `Metric` | `kind` | `Literal['counter', 'estimated', 'lower_bound', 'simulated']` | —（结构/对象） | Evidence/measurement basis. |
| `Metric` | `clock_domain` | `str \| None` | 1（标识/枚举） | Required for unit='cycle'; unrelated clocks cannot be summed. |
| `Metric` | `unknown_reason` | `str \| None` | 1（标识/枚举） | Mandatory iff value=None; omitted cost is not a complete total. |
| `RunRecord` | `run_id` | `str` | 1（标识/枚举） | Unique attempt identity; identical inputs may have different run_id. |
| `RunRecord` | `spec` | `ExperimentSpec` | —（结构/对象） | Frozen purpose, implementation revision, assumptions and mode. |
| `RunRecord` | `configuration_json` | `str` | 1（标识/枚举） | Canonical effective configuration snapshot; units remain in producer fields. |
| `RunRecord` | `inputs_json` | `str` | 1（标识/枚举） | Canonical input snapshot; this small boundary stores inline data. |
| `RunRecord` | `output_json` | `str \| None` | 1（标识/枚举） | Canonical producer output; None for a failed execution. |
| `RunRecord` | `metrics` | `tuple[Metric, ...]` | —（结构/对象） | Immutable observations with independent units and evidence kinds. |
| `RunRecord` | `status` | `Literal['succeeded', 'failed']` | —（结构/对象） | Execution status; does not assert functional validation. |
| `RunRecord` | `host_elapsed_s` | `float` | s | Host callback elapsed time [s]; never a simulated target metric. |
| `RunRecord` | `diagnostic` | `str \| None` | 1（标识/枚举） | Failure type/message; successful execution has no diagnostic. |
| `RunRecord` | `schema_version` | `Literal['universal-run/v1']` | —（结构/对象） | Public record schema ID. |
| `RunRecord` | `identity_hash` | `str` | 1（标识/枚举） | 只读派生属性；Experiment identity H(spec, effective configuration, inputs); seed/initial state must be explicit inputs. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `ExperimentSpec` | The experiment declares purpose, execution semantics, implementation revision and omitted mechanisms. |
| `Metric` | A metric carries one unit and evidence kind; unknown physical cost is value=None with a reason. |
| `RunRecord` | Immutable snapshots distinguish run success, target metrics and host wall time; identity excludes observations. |
| `RunRecord.identity_hash` | Experiment identity H(spec, effective configuration, inputs); seed/initial state must be explicit inputs. |
| `RunRecord.to_dict(self)` | Return a fresh JSON-owned view; editing it cannot mutate the immutable record snapshots. |
| `RunRecord.from_dict(cls, value: dict[str, object])` | Decode this exact version and rerun semantic checks; byte integrity alone is not schema validation. |

<!-- model-fields:end -->

# datasets：本地 Attention 数据来源与加载

`AttentionDataset` 保存来源声明、用途/限制、逻辑标签、相对路径和原始字节 SHA256；调用者拥有文件，`load_attention_dataset` 返回不可变 AttentionInputs。只依赖 contracts，不管理网络下载、模型注册或执行资源；无独立物理计量。

参数是 metadata、调用方的 root、完整 AttentionSpec 和 max_file_bytes [B]。路径必须是规范相对 POSIX 路径，解析目标不能越出 root；按上限加1字节读取以拒绝超限。原始 SHA256 包括换行/空白；文件的 spec_identity 绑定分组、因果位置、scale、shape 和 dtype。Q/K/V 只接受有限显式浮点及匹配长度。

顺序：校验清单 → 路径包含性 → 限量读 → 字节哈希 → 严格JSON/schema/任务身份 → shape。关键参数为文件字节预算与实际输入规模；profiles 再给 max_elements 限制。数据用途和来源仍是声明，kind=external 不等于真实代表性或授权已核实。格式与证据见[指南](../docs/foundation_usage.md)、[测试](../../tests/workloads/test_profiles.py)。

## 真实表格观测

`tabular.py`新增TabularSource/load_classification，读取末列类别、前列有限数值的本地CSV，保留feature/class顺序、单位名称、URL、署名、使用条件和原始SHA256。header若声明则严格匹配；不推断缺失值，路径/字节/样本预算先检查。返回contracts的不可变ClassificationData，划分与标准化另行完成。首份真实数据是[UCI Iris及许可来源](../../config/workloads/iris/README.md)，原值未修正；不代表其他任务分布。接口与反例见[W5指南](../docs/mapping_and_quality.md)及[测试](../../tests/workloads/test_retrieval.py)。

<!-- model-fields:start -->

### [attention.py](attention.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `AttentionDataset` | `dataset_id` | `str` | 1（标识/枚举） | Stable dataset/revision label, separate from workload and run identities. |
| `AttentionDataset` | `relative_path` | `str` | 1（标识/枚举） | Portable relative POSIX path within the caller-supplied data root. |
| `AttentionDataset` | `sha256` | `str` | 1（标识/枚举） | SHA256 of exact JSON bytes, including whitespace/newlines. |
| `AttentionDataset` | `source` | `str` | 1（标识/枚举） | Source revision/generation method or external attribution. |
| `AttentionDataset` | `kind` | `Literal['synthetic', 'external']` | —（结构/对象） | Distinguish a generated fixture from externally supplied data. |
| `AttentionDataset` | `split` | `Literal['train', 'validation', 'test']` | —（结构/对象） | Declared use; loader does not infer statistical independence. |
| `AttentionDataset` | `usage_terms` | `str` | 1（标识/枚举） | Source-provided usage information or explicit unknown status. |
| `AttentionDataset` | `limitations` | `str` | 1（标识/枚举） | Coverage and representativeness limits, retained in the experiment configuration. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `AttentionDataset` | Dataset metadata is a declared source boundary, not proof of representativeness, licensing or task quality. |
| `load_attention_dataset(dataset: AttentionDataset, root: str \| Path, spec: AttentionSpec, *, max_file_bytes: int=4194304)` | Check containment and byte identity before parsing strict JSON; the file binds data to the complete Attention spec. |

### [tabular.py](tabular.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `TabularSource` | `dataset_id` | `str` | 1（标识/枚举） | Dataset/revision label. |
| `TabularSource` | `relative_path` | `str` | 1（标识/枚举） | Normalized relative POSIX CSV path within caller data root. |
| `TabularSource` | `sha256` | `str` | 1（标识/枚举） | SHA256 of original CSV bytes, including original line endings. |
| `TabularSource` | `source_url` | `str` | 1（标识/枚举） | Original source URL/DOI; loading remains offline. |
| `TabularSource` | `attribution` | `str` | 1（标识/枚举） | Creator/donor/citation statement. |
| `TabularSource` | `usage_terms` | `str` | 1（标识/枚举） | Verified terms/source or explicitly unknown usage status. |
| `TabularSource` | `limitations` | `str` | 1（标识/枚举） | Source defects, scope and representativeness restrictions. |
| `TabularSource` | `feature_names` | `tuple[str, ...]` | 1（标识/枚举） | Ordered numeric CSV features; names declare measurement units. |
| `TabularSource` | `class_names` | `tuple[str, ...]` | 1（标识/枚举） | Exact accepted final-column labels, defining class index order. |
| `TabularSource` | `has_header` | `bool` | 1（布尔） | If true, one header row must exactly match feature names plus 'label'. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `TabularSource` | Source declarations describe attribution and limitations; they are not dataset representativeness claims. |
| `load_classification(source: TabularSource, root: str \| Path, *, max_file_bytes: int=1000000, max_samples: int=100000)` | Verify containment and bounded raw bytes before parsing numeric rows; no missing-value imputation is inferred. |

<!-- model-fields:end -->

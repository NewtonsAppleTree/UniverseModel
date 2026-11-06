# resolution：严格 dataclass 参数解析

`resolve_dataclass`/`load_config` 接收冻结参数类型、JSON object 与 dotted overrides。支持严格 scalar、Literal、optional、嵌套 dataclass 和 tuple；JSON array 变 tuple，float 归一为有限 binary64。类默认值 → 文件 → 调用覆盖；同一次覆盖按给定顺序，数组整体替换。

最关心未知/派生字段、bool/int 区分、错误路径与构造校验；关系式由 producer 的 derive/property 实现，解析器不复制公式。使用：装载 → 复制应用覆盖 → 逐字段转换 → `__post_init__`；输入树不被修改。测试见[工程测试](../../tests/integration/test_framework.py)。

<!-- model-fields:start -->

### [dataclass_config.py](dataclass_config.py)

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `apply_overrides(values: Mapping[str, object], overrides: Mapping[str, object])` | Apply explicit dotted overrides to a copied tree; mappings merge by path, sequences replace wholesale. |
| `resolve_dataclass(params_type: type[T], values: Mapping[str, object], *, overrides: Mapping[str, object] \| None=None, _path: str='configuration')` | Resolve declared init fields only, then run producer __post_init__; derived fields cannot be overridden. |
| `load_config(params_type: type[T], path: str \| Path, *, overrides: Mapping[str, object] \| None=None)` | Load a UTF-8 JSON object, apply invocation overrides, and construct the same producer-owned parameters. |

<!-- model-fields:end -->

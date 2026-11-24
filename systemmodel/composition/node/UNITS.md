# node：主机节点与设备视图

NodeSpec引用一个SystemTopology，其scope_id就是节点身份；boards为互不包含的纯容器子树，standalone_device_ids必须位于所有声明板卡之外。device_ids是二者去重复后按ID排序的派生视图，不是可配置设备数量。

构造先校验每块板卡，再检查设备唯一性及祖先重叠。identity_hash覆盖拓扑、来源和全部归属；外部列表复制为tuple，查询不修改参数。所有字段为身份/对象，不引入硬件时间或状态。

敏感条件为board/standalone放置、设备与内部资源区分。支持资源无需提升为设备；未绑定的model_id只是静态引用，后续适配必须另行校验实际chipmodel实例。验证见[节点测试](../../../tests/systemmodel/test_foundation.py)及[工程回读](../../../tests/integration/test_system_experiment.py)。

<!-- model-fields:start -->

### [model.py](model.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `NodeSpec` | `topology` | `SystemTopology` | —（结构/对象） | Authoritative resource/port/domain inventory; scope_id is the node ID. |
| `NodeSpec` | `boards` | `tuple[BoardSpec, ...]` | —（结构/对象） | Optional disjoint board subtrees; each remains independently validatable. |
| `NodeSpec` | `standalone_device_ids` | `tuple[str, ...]` | 1（标识/枚举） | Modeled devices outside every declared board, e.g. a host CPU. |
| `NodeSpec` | `schema_version` | `Literal['system-node/v1']` | —（结构/对象） | Static node inventory, not a scheduler or device executor. |
| `NodeSpec` | `device_ids` | `tuple[str, ...]` | 1（标识/枚举） | 只读派生属性；Return declared device IDs once, independent of board ordering; support resources are not promoted to devices. |
| `NodeSpec` | `identity_hash` | `str` | 1（标识/枚举） | 只读派生属性；Include topology provenance and all membership declarations in the node identity. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `NodeSpec` | Node membership refers to topology scope and existing instances; it does not instantiate a second hardware hierarchy. |
| `NodeSpec.device_ids` | Return declared device IDs once, independent of board ordering; support resources are not promoted to devices. |
| `NodeSpec.identity_hash` | Include topology provenance and all membership declarations in the node identity. |

<!-- model-fields:end -->

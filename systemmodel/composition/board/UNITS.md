# board：独立板卡归属校验

BoardSpec的board_id指向一个model_id=None的容器，device_ids指向其后代中的实际模型引用。只拥有不可变成员声明，所有资源仍在外部SystemTopology。source_ref给出声明来源；字段均为身份/版本，无独立时延、能量或面积。

构造BoardSpec → validate(topology)。同一板卡可在以自身为root的局部拓扑中独立验证，也可引用整节点库存；设备不能同时包含另一声明设备及其内部节点。卡数不乘任何共享容量，是否可达由端口图单独决定。

关键条件为祖先关系、非空唯一设备集合、模型身份存在。证据见[板卡/节点测试](../../../tests/systemmodel/test_foundation.py)，不验证所引用模型的功能、物理能力或供电条件。

<!-- model-fields:start -->

### [model.py](model.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `BoardSpec` | `board_id` | `str` | 1（标识/枚举） | Existing pure-container resource ID; the board adds no service capacity. |
| `BoardSpec` | `device_ids` | `tuple[str, ...]` | 1（标识/枚举） | Modeled CPU/accelerator/NIC package instances directly declared as board devices. |
| `BoardSpec` | `source_ref` | `str` | 1（标识/枚举） | Board assembly/profile reference or explicit manual assumption. |
| `BoardSpec` | `schema_version` | `Literal['system-board/v1']` | —（结构/对象） | Static device placement only. |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `BoardSpec` | A board declares its compute/device members and checks their physical containment against an independent topology. |
| `BoardSpec.validate(self, topology: SystemTopology)` | Every device belongs below this noncharging board container and refers to an actual model identity. |

<!-- model-fields:end -->

# registry：可选的显式模型构造

ModelRegistry 是软件基础设施，没有芯片面积、带宽或延迟。它只有 register/create/model_ids 三个入口，不扫描目录、不在 import 时执行注册、不加载配置字符串里的代码。

最关心模型身份、版本、错误诊断和实例隔离。model_id 建议包含语义版本，factory 是调用方提供的构造器；create 的关键字参数由具体模型校验。未知 ID 与重复注册拒绝，model_ids 返回稳定排序的副本。

使用顺序：创建独立 registry → 显式注册需要的少数类型 → create。直接导入并创建模型同样有效，注册表不是局部研究的必经路径。Factory 必须遵守实例所有权约定；注册表不会魔法复制 factory 返回的共享状态。

以后确有需求再加入能力/schema/成本 provider 元数据，当前不预建插件框架。

<!-- model-fields:start -->

### [models.py](models.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `ModelRegistry` | `_factories` | `dict[str, Callable[..., object]]` | 1（标识/枚举） | 本注册表独占的构造器映射；无物理单位。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `ModelRegistry` | 注册表只管理软件构造入口；重复身份拒绝，动态硬件状态由创建出的实例持有。 |
| `ModelRegistry.register(self, model_id: str, factory: Callable[..., object])` | 按显式 model_id 注册 callable；不解析或执行配置字符串中的代码。 |
| `ModelRegistry.create(self, model_id: str, **parameters: object)` | 将显式关键字参数交给所选构造器；字段与范围校验仍由模型负责。 |
| `ModelRegistry.model_ids(self)` | 返回稳定排序的名称副本；观察不暴露内部可变映射。 |

<!-- model-fields:end -->

# configuration：生产模块参数的统一解析

configuration 只依赖 contracts，不导入硬件实现。当前接口在[resolution](resolution/UNITS.md)：调用方提供自己的冻结 dataclass 类型，解析器负责 JSON/类型/显式覆盖，原类型负责物理范围和跨字段关系。完整演进见[设计](docs/design.md)。

关键参数是真正的有效值、类型、覆盖顺序与只读派生量；无独立物理计量。使用：冻结参数定义 → JSON/overrides → producer 校验 → 新冻结实例 → 独立调用。当前不解释字符串公式或模板/迁移，测试见[工程测试](../tests/integration/test_framework.py)。

<!-- model-fields:start -->



<!-- model-fields:end -->

# docs：系统规则、Unit 说明与证据

这是文档模块，无独立物理 Unit、参数或计算成本。职责是维护系统关系、字段语义、假设、验证和来源，不能用文档存在代替模型实现。

| 入口 | 维护对象 |
| --- | --- |
| [系统级设计](system_model_design.md) | 工作/状态/操作/资源/连接/物理条件的关系 |
| [Unit 设计](unit_model_design.md) | 类型/参数/状态/接口规则及仍需考虑的问题 |
| [候选单元清单](component_inventory.md) | 各硬件族的候选机制与归属 |
| [ADC 详细说明](adc_model.md) | ADC 数值边界与原始示例 |
| [全局规则](../../docs/development/model_rules.md) | 全仓库 class/def/字段/模块文档要求 |
| [实现状态](../../docs/STATUS.md) | 已验证能力、支持范围与未完成项 |

每个目录的 UNITS.md 保留手写职责、关键参数、使用顺序和覆盖边界；model-fields 标记内的字段/接口表从 Python 源码生成。修改代码后运行 `python tools/check_model_rules.py --write-docs`，再运行默认检查。不要手改生成区，也不要在多处独立维护默认值。

新公式必须有量纲和假设，新增机制必须说明它回答哪个研究问题。模型注释简短，长推导写在模块说明；术语与物理判断仍需审阅，自动检查只保证结构和同步。

<!-- model-fields:start -->



<!-- model-fields:end -->

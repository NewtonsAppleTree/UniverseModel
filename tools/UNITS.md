# tools：仓库检查与可重复验收

这里是宿主开发工具，没有硬件Unit或目标性能。工具只按固定入口读取代码/配置、运行检查和保存产物；模型的专业参数由各模块UNITS维护。

| 入口 | 输入、输出与边界 |
| --- | --- |
| [check_model_rules.py](check_model_rules.py) | 校验定义前注释、字段语义及实现目录UNITS；`--write-docs`同步生成区，不判断物理结论 |
| [check_structure.py](check_structure.py) | 核对modules.json、实际import、文档链接和文档源哈希 |
| [validate_chipmodel.py](validate_chipmodel.py) | `--output`新目录运行六组默认夹具；`--read`仅验证保存的完整哈希/bundle；案例数、预期失败名单是受审查的验收常量 |
| [extract_nangate_evidence.py](extract_nangate_evidence.py) | 固定SHA256的Liberty/LEF原始字节→两单元四个成本点；离线复现，不是通用库解析或独立物理校准 |

验收源码身份为HEAD加项目Python/config JSON/pyproject原始字节的组合SHA256，覆盖未提交实现；不包含docs、build和compiler第三方目录。保存的host耗时单位为s，只用于工程运行成本。哈希校验可检测损坏/遗漏，不提供来源认证。

调用顺序与完整证据范围见[chipmodel完成报告](../chipmodel/docs/completion.md)。输出目录拒绝覆盖，失败中间产物保留；完成标记为最后写入的`acceptance.json`。修改默认研究夹具时同步核查验收常量、业务测试、文档和STATUS。

# RTL 文档维护导航

本目录维护设计约定，没有生产实现或可执行接口。上层导航见[RTL UNITS](../UNITS.md)。

| 维护源 | 单一职责 |
| --- | --- |
| [design.md](design.md) | 研究问题、资源/软件所有权、范围和未来实施条件 |
| [interfaces.md](interfaces.md) | 端口采样、请求/响应、背压、复位、顺序和可见性 |
| [model_mapping.md](model_mapping.md) | 数值/布局转换、边沿与模型服务时间、资源与成本映射 |
| [verification.md](verification.md) | 可检验性质、参考独立性、结果分类、来源与证据门槛 |
| [unit_spec_template.md](unit_spec_template.md) | 将上述规则落实到一个具体Unit的填写清单 |

更改端口/复位/时间含义时先改接口并升级草案身份，再同步映射、验证和受影响的具体规格；改变数值公式时同步根目录参数清单。当前字段均为文档词汇，未来实际代码字段由代码及对应UNITS维护。用户仅授权本轮文档工作，候选实现任务不自动转为已启动任务。

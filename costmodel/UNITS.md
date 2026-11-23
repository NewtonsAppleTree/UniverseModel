# costmodel：带条件与来源的成本查询

本模块接收结构身份、PVT、成本项和动作粒度，不拥有硬件状态、队列或目标时间。当前可运行范围为[专业接口](interfaces/UNITS.md)和[精确查表](providers/UNITS.md)，研究与验证见[CH9指南](../chipmodel/docs/physical_evidence.md)。依赖仅限标准库与contracts。

使用顺序：建立CostSource → OperatingPoint/CostKey → 有来源的CostPoint/CostTable → query_cost → 保留已知/未知结果；check_reference单独报告来源再现或留出参考误差。不同证据类型与relative_uncertainty=None均保留；查询成功不等于已校准。

最敏感的条件是完整结构、PVT、动作语义/单位与覆盖边界。area为mm²/instance，leakage为W/instance，dynamic为J/明确动作单位。未知点返回None与原因，不插值/外推，不按工艺名称或电压比例缩放。实体唯一计量与背景积分由调用组合处理，不由此模块推定运行时长。

真实示例仅包含固定Nangate45来源的两个标准单元面积和标称漏电；不代表MAC、SRAM或整芯片成本。解析公式、通用Liberty/LEF解析、外部仿真器执行、拟合与统计不确定性尚未实现。依据与独立测试见[成本测试](../tests/costmodel/test_costs.py)和[来源提取工具](../tools/extract_nangate_evidence.py)。

<!-- model-fields:start -->



<!-- model-fields:end -->

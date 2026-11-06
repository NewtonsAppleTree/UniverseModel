# contracts：公共值与工程边界

本模块无硬件计量，不拥有模型状态。当前入口为[实验结果](results/UNITS.md)、[规范化与版本](versions/UNITS.md)、[指标单位](units/UNITS.md)。专业 payload 保留生产模块自己的 schema；资源/计划/事件契约见[设计](docs/design.md)。

关键约束是不可变身份、明确单位、执行模式/证据类型、未知成本与版本兼容。使用顺序：producer 对象 → 序列化/字段校验 → RunRecord → 下游保存；公式 `H=SHA256(canonical UTF-8)` 不构成物理正确性证明。验证见[工程测试](../tests/integration/test_framework.py)。

<!-- model-fields:start -->



<!-- model-fields:end -->

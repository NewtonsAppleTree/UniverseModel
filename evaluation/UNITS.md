# evaluation：显式实验装配

evaluation 可以装配任意已允许的主模块；它拥有实验流程，不拥有硬件资源或全局目标时间。当前单次入口在[runner](experiments/runner/UNITS.md)，将 producer callable 连接到公共记录；扫描/优化见[设计](docs/design.md)。

关键输入是研究模式、有效参数、数据/初态、模型来源和观察口径。无独立物理公式，目标指标由调用函数返回。使用：解析/校验 → 注入函数 → 单次运行 → 参考比较/保存。验证见[工程测试](../tests/integration/test_framework.py)。

<!-- model-fields:start -->



<!-- model-fields:end -->

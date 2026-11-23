# evaluation：显式实验装配

evaluation 可以装配任意已允许的主模块；它拥有实验流程，不拥有硬件资源或全局目标时间。当前单次入口在[runner](experiments/runner/UNITS.md)，将 producer callable 连接到公共记录；扫描/优化见[设计](docs/design.md)。

关键输入是研究模式、有效参数、数据/初态、模型来源和观察口径。目标指标由调用函数返回；线性实验装配已有 MAC/DMA 服务并报告资源下界，没有新的物理校准。使用：解析/校验 → 注入函数 → 单次运行 → 参考比较/保存。验证见[工程测试](../tests/integration/test_framework.py)与[线性实验指南](docs/linear_mapping.md)。

训练 step 已通过同一 runner 接入，见[训练指南](docs/training_step.md)。[calibration](calibration/UNITS.md) 增加可选 PyTorch CPU 功能参考；它目前提供数值交叉验证，没有物理性能/能耗校准。

<!-- model-fields:start -->



<!-- model-fields:end -->

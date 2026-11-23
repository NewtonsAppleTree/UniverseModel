# evaluation：显式实验装配

evaluation 可以装配任意已允许的主模块；它拥有实验流程，不拥有硬件资源或全局目标时间。当前单次入口在[runner](experiments/runner/UNITS.md)，将 producer callable 连接到公共记录；扫描/优化见[设计](docs/design.md)。

关键输入是研究模式、有效参数、数据/初态、模型来源和观察口径。目标指标由调用函数返回；线性实验装配已有 MAC/DMA 服务并报告资源下界，没有新的物理校准。使用：解析/校验 → 注入函数 → 单次运行 → 参考比较/保存。验证见[工程测试](../tests/integration/test_framework.py)与[线性实验指南](docs/linear_mapping.md)。

训练 step 已通过同一 runner 接入，见[训练指南](docs/training_step.md)。[calibration](calibration/UNITS.md) 增加可选 PyTorch CPU 功能参考；它目前提供数值交叉验证，没有物理性能/能耗校准。

数字Tile对照已接入现有Linear路径，由evaluation将compiler计划转换为chipmodel显式请求；不改变模块依赖方向。详情见[CH1–CH4基础指南](../chipmodel/docs/foundation_usage.md)。

CH5的[CIM研究入口](../chipmodel/docs/cim_bench.md)已接入公共记录，并使用workloads独立整数参考。实验层承担公平比较与来源，硬件层维持纯数值/分析与独立调用。

CH6的[计算能力对照](../chipmodel/docs/compute_capabilities.md)按CPU/GPU/NPU专业语义分组，检查单因素参数与固定预算/工作口径。完整案例、失败和未知限额进入公共记录，不将能力分析成功当成任务质量或物理可行性证据。

CH7外存/缓存实验入口见[experiments/runner](experiments/runner/UNITS.md)，将专业模型接入同一记录/回读流程，并使Linear/Tile可显式采用DRAM源读profile。证据区分功能轨迹、条件分析界与未知执行成本。

CH8的[组合实验](experiments/runner/UNITS.md)接入ChipAssembly，使用同一RunRecord/产物流验证位置、资源和顺序消融；目标必要界、未知执行/能量与宿主规模开销分开记录。

CH9的[物理条件实验](experiments/runner/physical.py)已接入条件成本与单节点热响应；完整来源/输入/反例/未知状态可保存回读，详见[指南](../chipmodel/docs/physical_evidence.md)。

<!-- model-fields:start -->



<!-- model-fields:end -->

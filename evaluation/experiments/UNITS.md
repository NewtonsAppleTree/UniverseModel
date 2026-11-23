# experiments：可独立运行的实验流程

当前实现为[单次 runner 与有限线性映射比较](runner/UNITS.md)。线性实验复用统一参数/输入/记录边界，显式列举同一任务下的候选并保留失败；一般 sweeps/优化与到达过程尚未实现，不隐式启动全系统。

关键关系是每次尝试独立、输入内容身份一致可比较、源码/初态变化改变解释。没有新的硬件计量或队列状态。接口与验证由 runner 及[工程框架](../../ENGINEERING_FRAMEWORK.md)维护。

数字Tile已通过[runner适配](runner/UNITS.md)接入相同记录接口，支持显式地址、共享bank、固定路径、容量失败与同输入资源敏感性。

CIM局部台架复用[runner](runner/UNITS.md)进行固定数据的差分位置比较、ADC资源/精度消融、失败留档及完整候选回读；不将局部整数质量解释成AI任务质量。

CH6计算能力实验通过ComputeStudy保存CPU阶段/GPU驻留/NPU服务的分组案例；资源或工作单因素变化自动检查，格式不支持和启动未知/不可行分别留档。接口与复现见[指南](../../chipmodel/docs/compute_capabilities.md)。

CH7新增[runner/memory.py](runner/memory.py)有限外存/缓存研究：按实际访问比较DRAM条件界、缓存回填/脏写回和NAND页服务/外部输出。复用RunRecord和artifact，不建立另一个执行引擎；来源、完整名单和未知成本由[runner](runner/UNITS.md)维护。

CH8新增[runner/assembly.py](runner/assembly.py)：固定工作的位置、资源及完整job顺序对照，保存共享账本/跨Die线路量与同指标摘要。完整案例回读及适用边界由[runner](runner/UNITS.md)维护。

CH9物理条件实验已接入[runner](runner/UNITS.md)：来源点、几何、PVT、观测窗口、热敏感性与未知成本保留在同一套实验记录中；不将来源再现等同于物理校准。

<!-- model-fields:start -->



<!-- model-fields:end -->

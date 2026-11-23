# experiments：可独立运行的实验流程

当前实现为[单次 runner 与有限线性映射比较](runner/UNITS.md)。线性实验复用统一参数/输入/记录边界，显式列举同一任务下的候选并保留失败；一般 sweeps/优化与到达过程尚未实现，不隐式启动全系统。

关键关系是每次尝试独立、输入内容身份一致可比较、源码/初态变化改变解释。没有新的硬件计量或队列状态。接口与验证由 runner 及[工程框架](../../ENGINEERING_FRAMEWORK.md)维护。

<!-- model-fields:start -->



<!-- model-fields:end -->

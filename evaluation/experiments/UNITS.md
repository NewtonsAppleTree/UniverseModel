# experiments：可独立运行的实验流程

当前实现为[单次 runner](runner/UNITS.md)。统一参数/输入/记录边界可供后续 sweeps 使用；候选生成、预算、到达过程、比较与失败样本由实验流程显式决定，不隐式启动全系统。

关键关系是每次尝试独立、输入内容身份一致可比较、源码/初态变化改变解释。没有新的硬件计量或队列状态。接口与验证由 runner 及[工程框架](../../ENGINEERING_FRAMEWORK.md)维护。

<!-- model-fields:start -->



<!-- model-fields:end -->

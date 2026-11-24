# src：线性映射的独立阶段

Attention沿[tiling](tiling/UNITS.md)→[memplan](memplan/UNITS.md)→[interpret](interpret/UNITS.md)独立接入；任务/硬件依赖分离，完整W4边界见[指南](../../workloads/docs/mapping_and_quality.md)。

当前 Unit 是 [tiling](tiling/UNITS.md) 的生产/校验、[memplan](memplan/UNITS.md) 的容量/流量、[interpret](interpret/UNITS.md) 的功能执行。其他 pass 尚未实现；无全局编译器状态、优化求解器或目标时钟。

接口顺序：LinearSpec + TileShape/策略 → LinearPlan → 容量校验/流量统计；实际输入 + 合法计划 → 解释执行。可以直接传手工计划，每个消费者会重新校验其前提。关键参数是块形状、C 驻留策略和 scratch 字节预算；相同任务应守恒 MNK 工作量与完整 K 归约。

代码只依赖 contracts 和 compiler 内部阶段，不读取 workloads 参考或硬件实现。独立手算与非法计划反例见[tests](../tests/UNITS.md)，跨模块精确参考验证由 evaluation 完成。

## 训练阶段组合

[sched](sched/UNITS.md) 新增固定训练配方的 lowering 和独立 backing 生命周期分析；[interpret](interpret/UNITS.md) 执行训练 step 与独立 SGD 更新。旧权重通过全部反向后才更新，转置实际材料化；通用图 pass 和事件调度仍未实现。

<!-- model-fields:start -->



<!-- model-fields:end -->

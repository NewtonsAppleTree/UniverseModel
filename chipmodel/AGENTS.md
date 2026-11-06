# chipmodel 的架构与实现约束

继承根目录 [AGENTS.md](../AGENTS.md) 和[全局模型规则](../docs/development/model_rules.md)。

- 以芯片架构与 AI 训练/推理架构的联合视角设计。先明确任务语义、数据驻留/移动、有限资源、因果时间、物理条件和验证证据，再定义 Unit。
- 保持极简：公式优先用纯函数，配置优先用冻结 dataclass；有独立行为或状态才建模型类。相同机制复用，不按名称复制类；不预建通用事件框架、插件框架或厂商特性全集。
- 本阶段实现参数、公式、必要的功能参考和局部组合。ISA 执行、DRAM 调度、背压/一致性和复杂误差机制没有验证需求时不加入。
- 训练 iteration/step、prefill TTFT、decode TPOT、吞吐/并发有不同约束。AI 算法、KV 布局、并行策略和调度分别归 workloads/compiler/runtime；chipmodel 接收映射后的工作量和显式资源请求，不绑定单一模型架构。
- 完美主义体现在量纲、边界、守恒、所有权与验证，不能变成类数量、抽象层级或注释篇幅。
- 系统关系以 [system_model_design.md](docs/system_model_design.md) 为入口；每次新增参数说明它改变哪个可观察结果、依赖哪个假设、由何种测试或来源支撑。

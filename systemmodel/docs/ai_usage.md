# S6：AI 任务、节点驻留与搬运方案比较

本包把已有Linear、训练、Attention的**实际输入与独立数值参考**接到节点容量和搬运分析。研究同一任务在相同资源预算下，已驻留、设备直传和经host中转分别需要什么空间、工作和服务条件；用明确参数干预解释瓶颈。遵循[项目使命](../../PROJECT_MISSION.md)，数值正确性、静态可行性和性能证据分别保存。

## 任务、接口与模型范围

`evaluation/experiments/runner/system_ai.py`提供AiTask/AiCase/AiStudy、task_evidence、map_task、analyze_ai和完整记录接口。专业计算继续由workloads/compiler执行；systemmodel不导入任务格式。AiTask可以替换Linear形状/精度、训练层宽与batch、Attention头数/长度/因果语义和seed，不固定某个网络模型。

- Linear：已有tile interpreter对独立精确参考检查输出。
- Training：既有MSE/SGD链，检查预测、loss、全部权重梯度、输入梯度和下一版本参数；学习率明确为本版0.125。
- Attention：既有GQA/KV语义、fused/shared映射，对高精度独立参考检查输出。

每个任务实际operands/state保存在输入快照中；完整task+inputs哈希绑定`MemoryObject.source_ref`。以显式连续packed-input抽象计量：Linear的A+B，训练的参数+X+target，Attention的Q+K+V，各按自身dtype字节数计算；不推断压缩或稀疏。任务不超过既有1,000,000 MAC/materialization保护范围。

编译层给出活跃backing峰值与独立compute-local scratch需求。节点保留完整packed输入，因此训练任务另为所有非initial tensor总字节预留workspace，不能借用编译计划中已释放的输入空间；Linear另加输出，Attention使用声明的backing tensor清单。记录分别保留compiler_backing_peak_bytes与实际保守预留backing_peak_bytes。输入与workspace分别按真实分配粒度取整；这只证明该预留方案的容量，不是动态allocator。scratch是单独声明的计算局部预算，不重复计入节点backing；其目标供数服务未知。resident仅需目标副本；direct另保留源副本；staged再加host完整中转副本。所有copy长度严格等于实际packed输入；三种方案使用同一物理backing/DMA预算。

已驻留方案的前提是输入已经在目标；direct/staged包含一次完整准备。因此此比较不能直接当作同一初态下的端到端加速比。interpreter计算数学内容，静态DMA声明不执行真实字节复制；源可用性、迁移完成和数值内容的硬件发布仍是假设。

## 十八例与手算

```powershell
python -m example.system_ai_demo --output .build/system-ai
python -m example.system_ai_demo --read .build/system-ai
```

每个小任务提供resident/direct/staged、direct带宽减半、direct启动cycle乘10，共15个成功候选；32×32×32 float64 Linear的三个方案在同一8192 B目标backing上均失败，共18例。默认scratch为4096 B、MAC-only ceiling为1e9 MAC/s，来源显式标为人工假设。

| 观察 | 手算与含义 |
| --- | --- |
| 4×8和8×4 float64 Linear | A+B=512 B，输出128 B，目标backing640 B，128 MAC |
| resident | 准备copy 0 B；已知MAC必要界128 ns，其余执行成本未知 |
| direct | 准备copy 512 B；共享root已知必要界512 ns |
| staged | 准备copy 1024 B；host写入后读取，已知必要界1024 ns |
| root bandwidth ×0.5 | direct对应共享服务时间翻倍，明确属于预算敏感性干预 |
| startup cycles ×10 | 小copy的DMA启动占比增大，报告DMA及依赖瓶颈 |

服务界为 `max(MAC数 / compute_capacity_macs_s, 准备DMA界)`。MAC服务绑定目标计算设备的人工MAC-only假设；内部访存、训练scalar/transpose、softmax等执行成本不完整，因此所有候选的target_execution_time/target_energy仍为None+原因。bottleneck_resource_ids同时比较资源工作和整copy依赖必要界，不把下界标成实际执行性能。

same-task与bandwidth_scale=startup_scale=1构成同预算策略比较；参数干预显式保留比例、修改后的hardware_identity和来源，不能混入同预算加速比。小任务是确定性正确性台架，不报告数据集accuracy、泛化质量或LLM服务性能。

## 验证与回读

测试独立核对三类任务数值、训练完整状态、输入/对象/字节绑定、512 B手算、驻留/直传/中转工作、单参数敏感性、失败保留与未知成本。保存回读只用已存actual对独立reference重验，并检查静态内存/已存DMA路径；不调用mapped interpreter、producer或新寻路。输入、输出、路径、工作、瓶颈或unknown→0的篡改均拒绝。

全模块统一验收：`python tools/validate_systemmodel.py --output .build/systemmodel-acceptance`，随后 `--read .build/systemmodel-acceptance`。该入口串联S0–S6六组默认研究、完整失败名单与源码/产物哈希；完整回归和打包证据由[STATUS](../../docs/STATUS.md)记录。动态执行、完整协议和实测标定按后续课题所需证据深化。

整体验收另补6种可替换任务的18个策略组合：INT8/float64尾块、单层/三层训练、identity激活、批量因果GQA及不等头数；实际输入字节、独立数值参考与保存回读均通过。统一入口固定完整成功/失败案例身份，并将每条RunRecord的来源绑定到总源码清单；结果见[整体验收报告](acceptance.md)。

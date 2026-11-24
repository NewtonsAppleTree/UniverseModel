# S4：CXL 能力、分层驻留与显式迁移

本包回答三个可独立检验的问题：给定相同对象需求和物理预算，分层放置是否解决本地容量不足；声明的 CXL 内存是否具有实际可用的模式、映射和请求路径；对象迁移时，源与目标共存需要多少额外预留与数据工作。它为后续 AI 权重、激活、KV 卸载研究提供静态边界，当前不绑定任务或证明任务质量、性能收益。

依据[项目使命](../../PROJECT_MISSION.md)、[架构参数](../../ARCHITECTURE_PARAMETERS.md)，接口分为 [CXL 能力](../io/cxl/UNITS.md)、[分层驻留与迁移](../memory/UNITS.md)、[实验记录](../../evaluation/experiments/runner/UNITS.md)。物理存储唯一归属；tier、decoder、NUMA 和地址视图只引用现有 backing。

## 独立调用

```python
from systemmodel.memory.tiering import analyze_residency, analyze_migration
from systemmodel.io.cxl.model import analyze_cxl_access
from systemmodel.memory.migration import analyze_cxl_migration, analyze_dma_migration

usage = analyze_residency(tiers, plan, phase=1)
access = analyze_cxl_access(cxl, plan, request)
transition = analyze_migration(tiers, migration, phase=1)
native = analyze_cxl_migration(tiers, migration, 1, cxl, copy_request)
# 兼容的非 CXL.mem 路径也可以接已有 S3：
dma_evidence = analyze_dma_migration(tiers, dma_migration, 1, dma, batch)
```

以上变量由调用者提供专业数据类型，不需要配置或完整任务链。TieredMemorySystem 将全部 backing 精确分到一层；local/cxl.mem/dma_only 是访问策略声明，不是速度排序，也不自动授予可达性。analyze_residency 在同一个逻辑 phase 汇总存活副本，不能将不同 backing 的历史峰值相加。未使用容量也保留，容量不等于主机可访问容量。

TierMigration 显式提供 before/during/after 三份不可变 MemoryPlan，以及 source/target allocation、copy/move 和来源。during 必须保留全部旧 allocation/view，仅新增同一完整对象的目标副本与视图。copy 的 after 保留两份；move 仅删除源及其视图，其余对象/分配/视图保持。三份均在同一逻辑 phase 验证，不是执行时间点，也不自动发布 after。`additional_reserved_bytes = during - before`，保留目标粒度造成的 padding。

原生迁移绑定准确对象、完整长度、phase、源/目标 allocation 和物理偏移：读用于 CXL→host，写用于 host→CXL；本地端点必须属于该 host，并与 host 地址域匹配。S3 适配另要求 CopyBatch 使用精确 during 快照和一条完整对象链；涉及 cxl.mem backing 时禁止用 PCIe posted write 冒充原生 CXL。当前不做自动放置/替换策略、分块迁移或写时复制。

## 可复现实验与手算

```powershell
python -m example.system_tiering_demo --output .build/system-tiering
python -m example.system_tiering_demo --read .build/system-tiering
```

默认[配置](../../config/experiments/system_tiering.json)固定 host 512 B、CXL 4096 B、两份 accelerator 各 1024 B 的预算。hot/cold/archive 分别为 256/256/512 B，存活期均为 `[0,3)`，观察 phase=1。基线只用 host，候选使用同一硬件已有 CXL；没有增大候选硬件预算。无内容计算、缓存命中率或质量结论。

| case | 可检验行为与结果 |
| --- | --- |
| expanded_residency | host 256 B + CXL 768 B；1024 B 需求可行 |
| local_capacity_failed | 同样 1024 B 全放 host，超过 512 B，预期失败 |
| native_read | 256 B 对齐读取，4 行，256 B 数据 |
| partial_read_1B | 非对齐 1 B 请求，1 行，64 B 数据，额外 63 B |
| promote | cold 提升到 host，move：总预留 1024→1280→1024 B；after 为 host 512/CXL 512 B |
| replicate | 同一 cold 执行 copy，after 保留 1280 B；host 512/CXL 768 B |
| demote | hot 移到 CXL，原生整行写 256 B；after 为 host 0/CXL 1024 B |
| dma_to_accelerator | hot 经已有 host DMA 到 accelerator，256 B；共享 root 的已知条件下界 256 ns |
| io_is_not_mem / cache_is_not_mem | 其他模式不能提供本包 mem 查询，预期失败 |
| masked_write_unsupported | 部分行写未覆盖，预期失败 |
| decoder_mismatch | S2 地址视图与 decoder 物理偏移不符，预期失败 |
| source_retired_early | during 提前删除源，预期失败 |
| reuse_source_too_early | before/after 单独可行，但 during 重用仍存活源的物理区间，预期失败 |
| wrong_copy_object | 用 archive 的访问冒充 cold 迁移，预期失败 |

共 15 例，7 成功、8 预期失败；失败也完整保留。容量、64 B 分配/行粒度与 **64 B decoder 粒度均为具名人工台架假设**；后者不是实际 HDM 硬件限制。原生读按完整行计量，完整 CXL FLIT/控制/返回服务未知；不能与 PCIe frame_bytes 直接相加。DMA 的 256 ns 只是 S3 已知必要服务下界，原生迁移下界为 `None + unknown_reason`；所有候选的目标执行时间和能耗仍未知。

## 证明、来源和限制

`test_tiering.py` 提供 17 项模型测试，包括同预算容量比较、相同 phase 汇总、迁移手算/不变性、复制与迁出、瞬时容量/生命周期、类型/模式/所有权、100 组独立内存行参考及 DMA 适配。`test_system_tiering_experiment.py` 提供 6 项实验测试：全名单、未执行 producer/未寻路的回读、来源/输入混用、容量/行/迁移/路径/DMA工作篡改和 unknown→0 篡改。

每份记录绑定全部硬件、模式/decoder、tier、全部候选与选定输入、源码身份和假设。回读校验已存路径并重分析静态声明，不替换路径；失败诊断作为原观察保留，不执行失败 producer。重新计算哈希不允许把伪造结果当作同一声明的有效输出。

本包不实现完整 CXL 协议/HDM 寄存器、多主机池化/交错、缓存一致性/原子/可见性、真实复制或自动策略。三状态容量可行是完成迁移的必要条件之一；after 仍以外部复制完成为条件。[S5](network_usage.md) 已接通内存到 NIC 的供数路径、共享资源及 cluster 端点适配；[S6](ai_usage.md) 已组合实际 AI 数值任务与节点方案比较。实际回归、版本和打包证据统一见[STATUS](../../docs/STATUS.md)。

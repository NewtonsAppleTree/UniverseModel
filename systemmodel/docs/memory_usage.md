# S2：静态内存、别名、生命周期与 NUMA

本包回答：给定相同物理存储预算与逻辑对象，候选放置能否驻留、哪个地址映射到哪份副本、源是否具备访问路径、属于本地还是远端 NUMA。它为后续驻留/卸载/搬运方案比较提供边界，遵循[项目使命](../../PROJECT_MISSION.md)，不把声明合法当作目标执行、AI 质量或性能证据。

## 独立调用

专业参数与字段见[memory/UNITS](../memory/UNITS.md)。以下例子使用固定研究输入，模型本身不依赖 configuration/evaluation。

```python
from configuration.resolution.dataclass_config import load_config
from evaluation.experiments.runner.system_memory import MemoryStudy
from systemmodel.memory.placement import analyze_placement
from systemmodel.memory.access import analyze_access, resolve_span

study = load_config(MemoryStudy, 'config/experiments/system_memory.json')
case = next(c for c in study.cases if c.name == 'local')
placement = analyze_placement(study.memory, case.plan)
span = resolve_span(study.memory, case.plan, case.request)
access = analyze_access(study.memory, case.plan, case.request)
assert placement.backings[0].peak_reserved_bytes == 320
assert span.physical_offset_bytes == 0
assert access.locality == 'local'
```

MemoryObject 只有需求，不分配物理存储。MemoryAllocation 预留一份完整副本，按 backing 粒度上取整。MemoryRegion 映射一份副本的逻辑子区间；不同地址 alias 不增容。begin/end_phase 为半开生命周期，end 等于另一份 begin 时可复用物理和地址空间；它是输入假设，不是经调度证明的完成顺序。对象的数值内容、写别名一致性和副本同步都未实现。

MemorySystem 引用现有 NodeSpec，保留 S0/S1 schema。每个 backing 唯一归属，且禁止父摘要与内部资源同时作为容量。映射从 target ingress 推导 domain；地址宽度仅约束范围，物理容量另校验。NUMA 对源端口 owner 与 backing 做精确成员查询，不从 controller、跳数或地址猜测。resolve_span 只验证完整放置并解映射；analyze_access 额外检查源端及完整请求路径，无“本地免费直达”。

## 十五例台架

两份物理池各 1024 B，粒度 64 B；两 CPU、两 controller 与显式 fabric 转发。cpu0 可访问两池，cpu1 只允许到 dram1。NUMA0 包含 cpu0/dram0，NUMA1 包含 cpu1/dram1。所有参数是具名人工假设，不是设备标定。

| 案例 | 可检验结果 |
| --- | --- |
| local | weights=160 B、activation=96 B；dram0 峰值 192+128=320 B，逻辑 256 B、padding 64 B；local |
| remote | 相同对象、生命周期、总硬件预算，weights 移到 dram1；cpu0 为 remote；两例都为 2 跳，不推定时延差 |
| alias | 额外映射 weights.alias；同一副本，仍为 320 B |
| replicated_copy | 增加一份 weights 副本；增加 192 B，峰值 512 B；此例改变副本需求，只验证计量规则 |
| lifetime_reuse | 下一份 weights 在原副本 end=3 后复用物理/地址；峰值仍 320 B |
| placement_only | 单独校验容量，无访问路径或 hop 指标 |
| physical_overlap | 总需求未超容量，但活跃物理区间重叠，失败 |
| rounded_capacity | 逻辑长度似可容纳，但取整后越过容量，失败 |
| address_overlap | 同一 domain 的同时地址映射冲突，失败 |
| exposed_padding | 映射超出逻辑对象，不能读取 padding，失败 |
| write_denied | read-only view 的写请求失败 |
| expired | 在 end_phase 访问，失败 |
| span_overflow | 请求超过 view 的最后一字节，失败 |
| unreachable | 放置合法，cpu1 到 dram0 未声明 forwarding，访问失败 |
| stale_memory | plan 绑定旧硬件/NUMA identity，失败 |

这些是有限边界对照；只有 local/remote 固定相同任务需求与物理预算，不能把整个 roster 当成同任务性能消融。逐 backing 峰值分别报告；不将不同时刻的峰值相加。

## 运行、回读与证据边界

```powershell
python -m example.system_memory_demo --source-revision <revision> --output .build/my-system-memory
python -m example.system_memory_demo --read .build/my-system-memory
python -m unittest discover -s tests/systemmodel -p "test_*.py" -v
python -m unittest discover -s tests/integration -p "test_system_memory_experiment.py" -v
```

输出目录必须不存在。每个 case 保存完整硬件/候选名单、plan/request、源码身份、假设、结果或真实失败；预期失败也保留，意外失败会令 CLI 返回非零。保存的静态计数不替代目标性能；时延与能量为 `None` 并附原因，host_elapsed_s 只表示宿主开销。

回读校验完整名单/来源/输入，重新做确定性区间与地址/NUMA分析，并且只检查保存的实际路径；不调用 producer、不重新寻路、不执行硬件。它不重新证明最少跳数，也不重新证明失败诊断；失败是已保存运行观察。bundle 字节完整性与语义检查可发现修改，但不是外部签名或防恶意重写的真实性认证。

正确性证据含手算、200 组独立有限字节/阶段 oracle、非法归属/权限/映射反例和回读篡改检测。后续 S3 接实际传输协议 profile、启动与粒度、DMA/staging 路径和共享工作账本；只有加入相应服务/调度证据后才讨论时间或能耗收益。当前没有 OS 分配器、page walk、NUMA 距离、缓存/一致性、read response、完整内存内容或执行完成事件。

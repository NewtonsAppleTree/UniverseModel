# S0/S1：节点资源与可达性首包

首包为后续多加速器AI放置、搬运和卸载研究建立静态硬件边界。它回答“资源属于谁、允许什么操作、是否存在显式路径、路径引用哪些共享服务”。全部能力可以在没有任务执行器、完整芯片或集群模型时独立调用。

## 对象、参数与边界

ResourceNode沿用chipmodel的单父归属及model_id。SystemTopology要求唯一纯容器root，各项inventory排序后冻结；同名ID不能覆盖资源。容器不收费，BandwidthConstraint引用已有model_id资源，owner必须匹配parent，不允许同时选择摘要和内部后代。芯片内部状态及端口仍由被引用模型维护。

AddressDomainSpec以domain_id/owner/address_bits表示字节地址命名空间。合法span满足`0≤address`、`length_bytes>0`、`address+length_bytes≤2**address_bits`；没有分配、物理容量或地址翻译。不同domain中的相同整数地址不自动表示同一数据。

SystemPortSpec明确egress/ingress、协议身份、copy/read/write权限和terminal domain。无domain的端口只能作为transit；只有同owner的显式PortForwarding允许中转，terminal不能当转发器。SystemLink连接不同owner，端口协议必须一致，一方向最多一条连接。不存在“同一主机所以能互访”的默认规则；read/write只检查静态权限，不建模请求/响应数据阶段。

find_path执行最少link跳数搜索，分支按link_id稳定排序；max_hops是宿主查询上限。指定link_ids时直接校验连续性/权限/目标。SystemPath保留topology身份、两个地址域、links、crossings、constraint_visits；多次真实跨越同一资源保留多次引用，distinct constraint_ids不代表容量求和。

## 独立调用

```python
import json
from pathlib import Path
from configuration.resolution.dataclass_config import resolve_dataclass
from systemmodel.composition.node.model import NodeSpec
from systemmodel.topology.query import PathRequest, find_path

raw = json.loads(Path('config/experiments/system_connectivity.json').read_text(encoding='utf-8'))
node = resolve_dataclass(NodeSpec, raw['node'])
node.boards[0].validate(node.topology)
path = find_path(node.topology, PathRequest(
    source_port_id='host.out', target_port_id='gpu0.in', operation='copy'))
assert path.link_ids == ('host_to_rc', 'rc_to_gpu0')
assert path.constraint_visits == ('host_bus', 'gpu0_bus')
```

configuration只是可选加载器；直接构造这些dataclass同样适用。BoardSpec可以针对以board为root的局部拓扑独立校验，NodeSpec再组合多板卡/standalone设备。各字段与单位由[UNITS](../UNITS.md)及子目录代码维护。

## 默认七例与证据

[配置](../../config/experiments/system_connectivity.json)描述一个host、两块独立卡、一个显式root-complex转发组件。所有profile为`manual:system-connectivity-fixture/v1`，不代表某个真实PCIe代际。host_bus声明16e9 payload B/s，两个设备支路各8e9 B/s；每条bus的两个方向共享同一条件容量。这些只作为唯一资源引用保留，首包不计算性能。

| 案例 | 预期结果 | 要检验的行为 |
| --- | --- | --- |
| host_to_gpu0 | 成功，2 links | host_bus与gpu0_bus各一次 |
| host_to_gpu1 | 成功，2 links | 引用同一host_bus及gpu1_bus，不按卡数复制主机带宽 |
| peer_declared | 成功，2 links | gpu0→gpu1有显式crossing，不经过host_bus |
| peer_reverse_denied | 失败 | 反向P2P未授权；不能隐式借host终端中转 |
| read_denied | 失败 | copy能力不授予远端read |
| hop_limit_failed | 失败 | max_hops=1不足以达到目标，预算未满足可达不等于全图不可达 |
| wrong_explicit_path | 失败 | 指定路线终点与请求不符 |

```text
python -m example.system_demo --output .build/system-connectivity
python -m example.system_demo --read .build/system-connectivity
python -m unittest discover -s tests/systemmodel -p "test_*.py" -v
python -m unittest discover -s tests/integration -p test_system_experiment.py -v
python tools/check_model_rules.py
python tools/check_structure.py
```

CLI默认source_revision='unrecorded'，正式实验需传`--source-revision`并留原始源码快照。每个case保留同一完整node/名单/来源与自身PathRequest，实际失败写诊断，不伪造输出。结构错误在配置/构造时拒绝，合法配置中的路径不可行则保存failed record。

回读核对产物字节、身份、完整名单、共同来源、原请求，并在保存拓扑上验证已存route/crossing/constraint_visits；不重新搜索、不调用硬件服务或执行器。它证明保存路径的声明合法性，不重新证明自动路径的最少跳数，也不提供签名认证或实际数据正确性。

## 验证范围与下一包

独立验证包括地址极限、归属/引用/模型选择反例、同共享上行的手算路径、物理图可有环与30组小图的独立排列穷举、调用纯性、完整成功/失败及篡改回读。query是否正确和资源声明是否真实是不同证据；profile目前只有手工假设。

首包的`target_execution_time`与`target_energy`均为None及原因。还没有物理内存容量、NUMA时延、PCIe分包、DMA执行、staging缓冲、CXL一致性、NIC服务、任务数值或物理校准。下一包S2补内存/容量与放置，S3再形成真实搬运账本与同任务直传/中转比较。完整路线见[开发计划](development_plan.md)。

2026-11-24本地验收：新增22项测试，全仓库447项中445通过、2项可选PyTorch跳过；规则/结构及空白检查通过。七例实际CLI保存/回读一致，106份wheel源码逐字节一致，隔离标准库解释器重新执行/回读七例一致。证据根目录`.build/systemmodel-foundation-20261124`保留源码快照、全部记录、回归日志和wheel审计；精确版本与哈希见[STATUS](../../docs/STATUS.md)。S0/S1完成不等于S2–S7完整模块计划已完成。

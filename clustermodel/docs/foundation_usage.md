# clustermodel 基础开发：运行、计量与验收

2026-11-23。C1–C3完成固定P2P分析基础：端点、链路/交换、路由、rank/group、账本、条件下界与记录。本轮继续按[覆盖矩阵](coverage.md)补齐广度；新leaf-spine/多路径/静态停用/流量总览见[横向指南](breadth_usage.md)。

## 1 直接运行

Python 3.10+，生产实现只用标准库，在仓库根目录运行：

```text
python -m example.cluster_demo
python -m example.cluster_demo --output data/runs/cluster-foundation --source-revision "<commit+workspace-snapshot-id>"
python -m example.cluster_demo --read data/runs/cluster-foundation
python -m example.cluster_demo --set traffic.messages=[]
python -m example.network_demo
```

输出目录必须尚不存在。`--read` 校验完整候选清单、每份 run 的哈希/身份与共同输入预算，然后从已保存结果重建表，不重新执行模型；与配置、输入、来源覆盖互斥。最后的独立 C1 示例仍得到 42 μs 孤立链路估计。

配置是 [cluster_placement.json](../../config/experiments/cluster_placement.json)，对应 [ClusterStudy](../../evaluation/experiments/runner/cluster.py) 冻结 dataclass。可替换整个图/候选/消息数组，派生字段、未知字段、可执行字符串和隐含到达语义均不接受。默认 source_revision 为 `unrecorded`，正式证据应填实际源码与工作区快照身份。

每个候选保存完整 roster、相同图/组/输入、数据及内容版本、路由策略版本、profile 来源、假设、指标和结果。缺端点、错误成员、本地未覆盖路径、不可达及 profile 越域在运行内部成为 failed 记录，其他候选继续；失败输出/指标为空，CLI 有失败时退出码1。JSON/schema 结构错误发生在运行前，直接诊断，不冒充已执行候选。

study 目录以 `index.json` 为最后提交标记，下辖 `run-0000` 等通用 `run.json + manifest.json` bundle。截断清单、混用不同实验预算/来源或缺失失败候选都会拒绝回读；不承诺断电事务或仿真恢复。

## 2 四节点独立验收

假设来自 [开发计划第4节](development_plan.md)：n0/n1 接 sL，n2/n3 接 sR；每 NIC 注入/接收与接入方向为25 GB/s，上行每方向12.5 GB/s，每交换内部100 GB/s。两个128 MiB消息同时就绪，理想分包无额外帧字节，启动/传播/处理显式为0。不是某款设备的实测参数。

| 观测／条件下界 | A：两消息跨分区 | B：各消息在分区内 |
| --- | ---: | ---: |
| 逻辑 payload | 268,435,456 B | 268,435,456 B |
| sL → sR 帧需求 | 268,435,456 B | 0 B |
| 全网链路帧字节 | 805,306,368 B | 536,870,912 B |
| 单 NIC 最大服务下界 | 5.36870912 ms | 5.36870912 ms |
| sL → sR 服务下界 | 21.47483648 ms | 0 ms |
| 总资源下界 | **21.47483648 ms** | **5.36870912 ms** |

程序与这些独立常数一致。A 的瓶颈资源 ID 为 `sL->sR`；B 同时达到接入方向与 NIC 限制。下界之比4只说明这组固定路径与声明容量的必要服务差异，不表示通信实际完成时间或训练加速比。

测试还验证：上行改25/50/100 GB/s后，A的资源界依次为10.73741824/5.36870912/5.36870912 ms，出现 NIC/接入平台；反向双流每方向10.73741824 ms，显式半双工共享介质合计21.47483648 ms；不同端口共享一个NIC时2D需求不被拆成两份带宽；降低交换内部容量可单独成为瓶颈。

## 3 独立调用和目录接口

```python
from configuration.resolution.dataclass_config import load_config
from evaluation.experiments.runner.cluster import ClusterStudy
from clustermodel.composition.cluster.model import ClusterSpec
from clustermodel.composition.cluster.analysis import analyze_traffic
from clustermodel.fabric.routing.paths import resolve_route, validate_route
from clustermodel.topology.graph import cut_capacity

study = load_config(ClusterStudy, "config/experiments/cluster_placement.json")
cluster = ClusterSpec(cluster_id="standalone", graph=study.graph,
                      placements=study.candidates[0].placements, groups=study.groups)
route = resolve_route(study.graph, "e0", "e2")
validate_route(study.graph, route)
cut = cut_capacity(study.graph, ("n0", "n1"), switch_ids=("sL",))
result = analyze_traffic(cluster, study.traffic)
assert route.link_ids == ("e0->sL", "sL->sR", "sR->e2")
assert result.total_link_wire_bytes == 805306368
```

可直接构造这些参数对象，不要求配置文件、runner、compiler、runtime 或 simulator。目录职责与精确字段见 [UNITS](../UNITS.md)。

| 目录 | 已实现的独立能力 |
| --- | --- |
| fabric/links | raw_line / effective_payload 二选一；精确尾包、孤立查询和未知帧量 |
| fabric/switches | 显式端口与 ingress→egress 连接、内部共享约束、必要处理延迟 |
| fabric/routing | 显式路径验证；最少物理 hop、按完整边 ID 序列破平局 |
| topology | 全图所有权/方向/帧基准校验、可达性、指定割；直连/单交换/两分区构图 |
| composition/groups | 唯一 rank 放置、非空有序组、跨组重叠、共享端点 |
| composition/cluster | 每消息、每链路、每容量资源的完整需求与独立下界 |

原 `direct-network-graph/v1` 只接受直连端点；交换图显式用 `routed-network-graph/v1`。不放宽旧版本为隐式交换图。图资源规范排序，组成员与显式路径顺序保留；显式有限环逐 crossing 计量。NIC 接收端不能中转，同节点消息因缺节点服务摘要明确拒绝。

## 4 数学与覆盖

资源账本 `Q_r=Σ_i q_ir`，条件资源时间界 `max_r(Q_r/C_r)`。容量按唯一物理资源定义，不能随 rank/group 数倍增。源注入和目标接收按各自边界计量；交换每次转发按 payload 或出口 frame 计一次；所有额外共享约束引用实际工作，不能加入物理链路流量总和。

`wire_bytes` 指 PHY 编码前帧字节。各 hop 使用其自己的分包 profile，允许分析异构表示；格式转换的实现、额外缓存和处理成本没有自动覆盖。effective_payload 的有效率已包含对应开销，不再扣分包效率；其非空帧量未知。任一已用链路缺帧量时总帧量为 None，但各已知分项仍保留；未用链路是明确0。

必要路径延迟界只累加传播与交换首数据处理延迟。单链路 startup 是孤立估计条件，不推断为多跳串行成本；整个消息的逐 hop 序列化可能重叠，不能机械相加。总通信界取资源、必要延迟、指定割三个独立下界的 max。指定割记录固定路径实际有向 crossing，重复过割重复计量；混合 payload/frame 或不兼容帧表示拒绝合并，不求全局 min-cut。

拟合有效率只支持条件模型下界，实测平均吞吐不能直接证明物理容量上界。当前没有队列/背压/公平性执行、目标内存可见、collective 数值、训练 step、推理 SLO、能量标定；完整能量保持未知，包括空工作场景的未覆盖漏电。

## 5 验证与后续交接

```text
python -m unittest discover -s tests/contracts -p "test_*.py" -v
python -m unittest discover -s tests/clustermodel -p "test_*.py" -v
python -m unittest discover -s tests/integration -p "test_*.py" -v
python tools/check_model_rules.py
python tools/check_structure.py
```

核心证据：[链路测试](../../tests/clustermodel/test_links.py)、[直连测试](../../tests/clustermodel/test_topology.py)、[集群测试](../../tests/clustermodel/test_cluster.py)、[实验回读测试](../../tests/integration/test_cluster_experiment.py)。包含手算、守恒、非均匀 profile、菱形路径、显式环、方向/所有权、共享NIC/交换/介质、重叠组、incast、空输入和失败保存。

C1–C3固定P2P分析、[横向基础](breadth_usage.md)及[收尾优化](completion.md)均已完成，[覆盖矩阵](coverage.md)的基础范围已验收。下一轮进入chipmodel；C4事件、C5完整AI/物理校准按后续研究证据门槛接入。

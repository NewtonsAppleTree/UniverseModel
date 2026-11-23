# 集群横向能力：拓扑、路径、可用性与流量

本指南说明已完成的跨场景独立接口：leaf-spine、多路径查询、静态停用视图、拓扑/逻辑流量总览，与[C1–C3分析](foundation_usage.md)组合使用。基础范围复核与优化已完成，见[完成报告](completion.md)；下一轮进入chipmodel。

## 1 六节点leaf-spine入口

```text
python -m example.cluster_demo --config config/experiments/cluster_leaf_spine.json --overview
python -m example.cluster_demo --config config/experiments/cluster_leaf_spine.json --output data/runs/cluster-breadth
python -m example.cluster_demo --read data/runs/cluster-breadth --overview
```

输出目录须尚不存在。`--overview`只选择显示已保存的观测，不改变实验身份；老记录没有这些观测时返回None，不重新执行新模型。当前成功记录新增network_overview、traffic_description、outage_view字段，原有消息/资源/下界字段仍可读取。源码来源默认unrecorded，正式实验应通过`--source-revision`提供实际快照身份。

[配置](../../config/experiments/cluster_leaf_spine.json)声明6个节点、3个leaf、2个spine。每个节点向其他5个节点各发1 MiB，共30条固定P2P消息；这是合成需求矩阵，没有实现collective数值或协议。接入/NIC为25 GB/s，leaf-spine每方向12.5 GB/s，交换内部100 GB/s，理想帧无开销，延迟显式为0。

| 独立参考 | 数值及意义 |
| --- | --- |
| 安装资源 | 6个节点、6个端点、5个交换机、17项共享容量约束 |
| 连线 | 12组物理端口连接、24条方向；双向存在仍受显式共享约束限制 |
| 同leaf消息 | 6条，每条2个物理hop |
| 跨leaf消息 | 24条，每条4个物理hop；每对源/目标有2条最短路径 |
| 逻辑流量 | 30 MiB = 31,457,280 B |
| 每节点发/收 | 各5 MiB = 5,242,880 B |
| 全网链路帧量 | (6×2+24×4) MiB = 113,246,208 B |
| 资源时间下界 | 0.67108864 ms；固定字典序路由选择s0，各使用中的leaf-spine方向承载8 MiB |

两条候选共用接入链路和NIC，路径总数不乘容量。停用s0之后重新选择路径会使用s1，本例字节和下界相同；同时停用s0/s1，跨leaf需求不可达并保存failed记录。这没有测量故障收敛或恢复时间。

## 2 可独立调用的接口

```python
from configuration.resolution.dataclass_config import load_config
from evaluation.experiments.runner.cluster import ClusterStudy
from clustermodel.composition.cluster.model import ClusterSpec
from clustermodel.composition.cluster.traffic import describe_traffic
from clustermodel.fabric.routing.paths import shortest_route_choices
from clustermodel.topology.inspection import inspect_network
from clustermodel.topology.scenarios import NetworkOutage, apply_outage

study = load_config(ClusterStudy, "config/experiments/cluster_leaf_spine.json")
cluster = ClusterSpec(cluster_id="survey", graph=study.graph,
                      placements=study.candidates[0].placements, groups=study.groups)
overview = inspect_network(study.graph, source_endpoint_ids=("e0", "e2"))
demand = describe_traffic(cluster, study.traffic)
choices = shortest_route_choices(study.graph, "e0", "e2", max_paths=1)
assert choices.total_shortest_paths == 2
assert choices.truncated
view = apply_outage(study.graph, NetworkOutage(
    source_ref="manual:spine-maintenance/v1", disabled_switch_ids=("s0",)))
surviving = shortest_route_choices(view.graph, "e0", "e2")
assert surviving.total_shortest_paths == 1
```

- `leaf_spine_network`接收leaf→端点分区、spine IDs、独立的leaf/spine内部容量和处理延迟、链路profile和来源。允许非均匀分区；每个端点恰好属于一个leaf，节点可有多个端点连接不同leaf并引用同一NIC约束。不会自动把同一rank分条带到多个NIC。
- `shortest_route_choices`先计算最短路径DAG及精确路径总数，再按完整link ID字典序只生成至多max_paths条路径；truncated说明候选未全部列出。返回Route采用explicit/v1，便于上层明确选择；不实现散列分流或动态负载均衡。
- `inspect_network`默认只给资源/连接库存；可达性只针对source_endpoint_ids显式给出的源查询。报告区分远端可达、远端不可达和同节点其他端点；后者不代表节点内部服务已实现。方向性不对称时保留这种差别。
- `describe_traffic`只验证逻辑引用，提供rank/节点/端点发收量、稀疏节点矩阵和声明组归属。未分组消息归None；组成员重叠不复制流量。即使存在本地或不可达需求也保留其原始字节，路由/profile可行性另由analyze_traffic判断。
- `apply_outage`返回原图哈希、来源、实际移除方向集合及新图。单链路ID仅停用该方向；节点/交换选择移除全部关联方向。保留安装端点、交换和约束声明，让原放置及不可达消息仍可审查；这些保留容量不表示设备正在服务。

## 3 停用场景进入实验记录

ClusterStudy新增可选`outage`，旧配置缺省为None。可在JSON加入：

```json
"outage": {
  "source_ref": "manual:spine-maintenance/v1",
  "disabled_switch_ids": ["s0"]
}
```

也可直接用Python冻结对象组合：

```python
from dataclasses import replace
from evaluation.experiments.runner.cluster import run_study, write_study

modified = replace(study, outage=NetworkOutage(
    source_ref="manual:spine-maintenance/v1", disabled_switch_ids=("s0",)))
records = run_study(modified, source_revision="<commit+workspace-snapshot-id>")
write_study(records, "data/runs/cluster-spine-outage")
```

停用在每个已留输入快照的候选内部应用。原始图、原始消息、停用条件和来源进入身份；成功结果保存新图总览和移除方向，错误选择/断路保留失败诊断。显式路径不会被重写；shortest-hop-lex/v1会在新静态图上重新查询。配置不能加入故障时刻、修复时长或其他未实现语义。

不同停用条件属于不同实验条件，不能拼成同一图预算的放置对照；现有回读检查会拒绝混用。子系统概率可靠性、修复、重传、协议收敛需要独立时间模型和证据。

## 4 广度验收之后怎样深化

[模型测试](../../tests/clustermodel/test_breadth.py)覆盖非均匀拓扑、多spine、12条路径只枚举1条、方向停用、节点停用、多轨NIC共享、组归属及需求守恒；[集成测试](../../tests/integration/test_cluster_breadth.py)覆盖来源/原图保存、失败回读、旧结果兼容和CLI总览。

```text
python -m unittest discover -s tests/clustermodel -p "test_*.py" -v
python -m unittest discover -s tests/integration -p "test_cluster*.py" -v
python tools/check_model_rules.py
python tools/check_structure.py
```

本轮基础覆盖已按[矩阵](coverage.md)逐项核对并完成收尾。后续课题深化时，先明确目标结论所缺证据：路径选择需要真实需求和共享资源对照，拥塞/尾延迟需要窗口/队列/生命周期语义，物理性能与能量需要有来源校准。完整AI数值与任务质量保留在相邻模块，集群提供可组合资源与通信证据。下一轮进入chipmodel。

# C1：独立链路与直连拓扑

2026-11-23。C1已实现只读端点/带宽契约、单向链路、直连端口图，以及配置/记录示例。它服务于后续AI通信路径的可检查资源基础；不是交换网络、collective或事件仿真。状态与后续门槛见 [STATUS](../../docs/STATUS.md)及[开发计划](development_plan.md)。

## 运行与保存

在仓库根目录使用Python 3.10+标准库：

```text
python -m example.network_demo
python -m example.network_demo --payload-bytes 1025
python -m example.network_demo --output .build/network-c1
python -m example.network_demo --read .build/network-c1
```

输出目录须为全新目录，已有记录不会覆盖；回读验证manifest、哈希与记录结构后输出相同摘要，不重新执行模型。`--read`不能和配置/输入覆盖一起使用。正式记录用`--source-revision`传入源码快照身份，默认unrecorded说明来源未完整记录。

参数在[network_link.json](../../config/experiments/network_link.json)。`--config`接受同一NetworkCase schema，未知/派生字段拒绝；`--payload-bytes`只覆盖输入长度。端点、容量、完整链路profile、source_ref/coverage都进入记录。没有配置中的动态import、代码或公式字符串。

## 可核对的默认结果

| 量 | 默认结果及范围 |
| --- | --- |
| 拓扑 | n0、n1两个NIC端口，分别声明正反两个物理方向；每方向200 Gbit/s |
| 速率/分包 | 编码效率1、4096 B最大payload、头尾0 B、对齐1 B，全为手工理想假设 |
| 输入 | 1,000,000 B，即十进制1 MB |
| 包数/帧量 | 245包；1,000,000 B PHY编码前帧字节 |
| 单链路序列化 | 40 μs |
| 固定延迟/孤立总时间 | 显式启动1 μs、传播1 μs；总计42 μs |
| n0的出向割 | 链路容量和25×10^9 B/s；尚未结合NIC或共享资源工作量 |
| 总网络能量 | None并保留原因；没有动作成本/执行时长依据 |

这个42 μs只计算所选链路。NIC注入/接收、软件launch、争用、有限窗口、目标内存可见均未被计入，不能称为端到端消息完成时间。cut是指定方向链路容量和，不是实际吞吐或全局最小割。

尾包独立测试采用1024 B最大payload、24 B头、8 B尾、64 B对齐：1025 B逻辑消息形成1088 B和64 B两帧，总1152 B。该结果使用精确整数计数，不依赖平均协议效率。

## 独立Python调用

以下代码使用示例的显式参数加载器；模型函数也可直接接收手工构造的LinkParams或NetworkGraph，无需实验runner。

```python
from configuration.resolution.dataclass_config import load_config
from example.network_demo import NetworkCase
from clustermodel.fabric.links.model import estimate_link
from clustermodel.topology.graph import get_link, reachable_endpoints, cut_capacity

case = load_config(NetworkCase, "config/experiments/network_link.json")
graph = case.configuration.graph
link = get_link(graph, "n0-n1")
estimate = estimate_link(link, 1_000_000)
print(estimate.isolated_time_s)
print(reachable_endpoints(graph, "n0.nic"))
print(cut_capacity(graph, ("n0",)))
```

字段维护在[公共端点](../../contracts/hardware/UNITS.md)、[links](../fabric/links/UNITS.md)、[topology](../topology/UNITS.md)。冻结图只包含引用和参数，不创建状态副本。有效payload分支禁止再填写线路/分包字段，非空查询的包数/帧量保持未知；profile越域在runner中成为failed记录，不生成成功指标。

## 验证与下一步

新增39项测试：公共契约6项、链路13项、拓扑13项、工程集成7项。覆盖手算/尾包/编码、零输入和profile边界、浮点溢出/下溢、稳定身份、物理端口冲突、双工/共享引用、禁止隐式转发、配置和保存/回读。默认运行不需要GPU或外部模拟器。

```text
python -m unittest discover -s tests/contracts -p "test_*.py" -v
python -m unittest discover -s tests/clustermodel -p "test_*.py" -v
python -m unittest discover -s tests/integration -p "test_network_experiment.py" -v
python tools/check_model_rules.py
python tools/check_structure.py
```

C1直连图使用direct-network-graph/v1。C2/C3现已实现显式交换能力、确定性路由、多流账本和四节点比较，见[基础指南](foundation_usage.md)；交换图使用routed-network-graph/v1。本C1示例仍只解释孤立链路，事件与AI执行按后续研究需求接入。

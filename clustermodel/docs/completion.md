# clustermodel 基础开发完成报告与交接

2026-11-23。本轮完成C1–C3、横向能力、规模优化与收尾验证，**下一轮进入chipmodel**。基础范围以[项目使命](../../PROJECT_MISSION.md)、[12维覆盖矩阵](coverage.md)和可检验的固定P2P研究需求确定。

## 1 逐目录交付

| 目录 | 已完成且可独立调用的能力 | 验收依据 |
| --- | --- | --- |
| fabric/links | raw_line/effective_payload、精确包头/尾包/对齐、孤立服务、profile域及未知帧量 | 1 MB/200 Gbit/s孤立42 μs；1025 B尾包案例1152 frame B |
| fabric/switches | 显式端口转发、交换容量/必要处理延迟、唯一owner | 缺连接不可转发；按出方向frame计量；内部共享瓶颈 |
| fabric/routing | 显式有限路径、确定性最少hop、最短路径精确计数和有界候选 | 环/重复过割、NIC禁止中转、方向失效及独立路径枚举参考 |
| topology | 直连/单交换/两分区/leaf-spine、owner有向割、库存/可达性、静态停用视图 | 非均匀leaf、多NIC、多spine；停用保留原需求和来源 |
| composition/groups | rank→节点/端点、有序通信组、重叠组及共享NIC引用 | 唯一身份、成员检查；共享引用不倍增容量 |
| composition/cluster | 固定P2P、逐消息/方向/资源/割账本、条件时间下界、流量总览 | 四节点放置对照、六节点矩阵守恒、共享反例、异构帧格式、空工作与失败诊断 |
| docs及各层UNITS | 接口、单位、范围、公式、复现步骤和后续研究触发条件 | 模型规则/结构/链接检查；字段由代码生成维护 |
| 外部工程接入 | 严格配置、有限放置比较、完整候选成功/失败记录、保存回读及wheel | 新旧记录回读；不同预算拒绝混合；损坏/重复/未知schema拒绝 |

所有接口保持标准库独立调用。公共端点/容量在contracts；节点内部资源归systemmodel，任务/collective归上层，事件引擎归simulator。没有新增无行为类型来填充目录。

## 2 本轮收尾优化

一次分析建立内部只读索引，复用同路径和同link/长度的不可变估算；多源可达性查询共享索引，构图校验提前汇总交换egress约束。指定割从方向账本归并工作量和实际过割次数。缓存随调用结束释放，不进入配置、资源身份或产物，不跨停用视图复用；每条消息的真实计费仍保留。

回读补齐快照候选清单的重复检查、run_id唯一性、配置schema与索引字段校验。旧记录缺可选outage或总览的兼容行为保持，读取只恢复已保存的观测。

收尾新增5项模型测试和2项工程测试。独立路径参考直接枚举原始端口连接，在12组确定性生成的完整/稀疏/单向失效图上验证360个端点对的路由、精确路径数和可达性；另验不同消息长度、显式备选路径、profile改动/越域和停用后恢复。既有测试继续覆盖frame约束、共享资源与重复过割。

## 3 宿主规模实验

[benchmark_cluster.py](../../tools/benchmark_cluster.py)使用显式合成leaf-spine和理想profile。每个阶段预热1次、计时3次，报告原始样本与中位数；分析内存另用tracemalloc单独测量，计时不含它的开销。记录Python/平台、参数、源码哈希及完整图/输入/分析输出/总览哈希，拒绝覆盖既有文件。

| 固定输入 | 优化前分析中位数 | 优化后分析中位数 | Python分配峰值变化 |
| --- | ---: | ---: | ---: |
| 64节点、8 leaf、4 spine、512条重复端点对消息 | 1.1663 s | 0.01816 s（约64.2倍） | 1,916,896 → 1,051,040 B（减少45.2%） |
| 32节点、4 leaf、4 spine、992条全互发消息 | 0.4780 s | 0.05125 s（约9.3倍） | 2,232,992 → 1,623,200 B（减少27.3%） |

这是同一Windows/Python 3.12.4环境的有界宿主实验，覆盖重复路径和不同端点对两类负载；不是真实网络加速、任意规模复杂度保证或完整进程RSS。每种输入的图、消息、完整分析结果和总览哈希优化前后相等。实际耗时受主机负载影响，所有样本与变更前源码快照保存在 `.build/cluster-closeout-20261123`；最终优化后数据为final-repeated.json、final-all-pairs.json。crossbar连接数仍为O(p²)，逐消息证据仍随消息和hop数增长。

```text
python tools/benchmark_cluster.py --output .build/my-cluster-benchmark/repeated.json
python tools/benchmark_cluster.py --leaves 4 --nodes-per-leaf 8 --pattern all-pairs --output .build/my-cluster-benchmark/all-pairs.json
```

## 4 验收与复现

最终全回归213项：211项通过、2项可选PyTorch测试因默认环境缺失而跳过；其中集群模型72项通过，网络相关合计103项通过。模型规则与结构检查通过，wheel内57份Python源码与工作区一致，并在隔离解释器中通过验证。详细测试分组、来源快照与回读结果由[STATUS](../../docs/STATUS.md)记录。

本轮产物 `.build/cluster-closeout-20261123` 保留单链路、四节点、leaf-spine、单spine停用和不可达失败五组记录，保存/回读一致；四组旧阶段记录也通过回读。两个spine停用的CLI退出1是预期失败，原需求仍在记录中。既有foundation/breadth产物保留为历史证据。

```text
python -m example.network_demo
python -m example.cluster_demo
python -m example.cluster_demo --config config/experiments/cluster_leaf_spine.json --overview
python -m example.cluster_demo --read .build/cluster-closeout-20261123/leaf-spine --overview
python -m unittest discover -s tests/contracts -p "test_*.py"
python -m unittest discover -s tests/clustermodel -p "test_*.py"
python -m unittest discover -s tests/integration -p "test_cluster*.py"
python tools/check_model_rules.py
python tools/check_structure.py
```

## 5 下一轮chipmodel的接续范围

下一轮先按chipmodel自身规则复核现有Unit、参数和验证，再梳理计算、存储、搬运/互连、控制与组合的依赖和独立调用路径；依据实际缺口选择首个可手算的局部组合台架，逐目录修正代码、UNITS和STATUS。设备状态与成本由所属Unit维护，经systemmodel端点/能力边界向集群组合，避免把摘要成本与内部细模型重复计入。

本轮集群基础不再有阻挡模块切换的待办。排队/credit/重传、执行可见性、真实collective、节点本地服务摘要和物理性能/能量校准仍是明确的研究扩展；其进入条件见[设计](design.md)与[覆盖矩阵](coverage.md)。当前结果是固定需求和声明容量下的分析证据，未知成本继续为None加原因。

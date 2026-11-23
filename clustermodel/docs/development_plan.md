# clustermodel 逐目录开发与验收计划

日期：2026-11-23。依据[项目使命](../../PROJECT_MISSION.md)、[模块设计](design.md)、[工程框架](../../ENGINEERING_FRAMEWORK.md)及[模型规则](../../docs/development/model_rules.md)。本次交付设计和开发拆分，没有新增可运行模型；阶段完成情况以 [STATUS](../../docs/STATUS.md)为准。

## 1 首批交付与范围

首批完成 C1–C3 后，用户应能独立查询一条链路、构建网络图、校验一条路径/一个通信组，或运行四节点通信分析并从保存记录重建对照表。全部使用 Python 3.10+ 标准库，保留直接传 Params/Input 的短路径。

首个问题：**固定节点、消息和网络资源，rank 放置如何改变共享上行负载与通信时间下界？** 先用手工 P2P 需求验证资源语义；AI collective、训练 step 和推理服务指标在后续有对应证据时接入。

阶段以依赖和验收划分，不承诺日历工期。C1–C3 无需 GPU 或外部模拟器；C4 根据争用证据需要选择外部后端或最小流级执行；C5 按课题进入训练或推理路径。

## 2 按文件夹推进

所有 `.py` 名称均为拟建文件，首次实现时才创建。各级 UNITS 已提供参数和边界草案，代码落地后以声明行与生成区为字段维护源。

| 顺序 | 目录与拟建文件 | 交付行为 | 进入/退出条件 |
| --- | --- | --- | --- |
| C0 设计 | clustermodel/docs、各层 UNITS | 边界、接口、公式、手算夹具及阶段门槛 | 设计链接和规则检查通过；不计作模型完成 |
| C1a 公共边界 | contracts/hardware/network.py | 只读端点和带宽约束，身份/单位/有限值校验 | 同步 contracts/hardware 与祖先 UNITS；不导入硬件 |
| C1b 链路 | clustermodel/fabric/links/model.py | 两种互斥计量基准、消息服务量、孤立时间 | 线路/payload 不重复扣开销；尾包、零值、双工测试 |
| C1c 拓扑 | clustermodel/topology/graph.py | 有向端口图、显式连接校验、可达性和指定割 | 两端点直连可独立分析；身份/方向/空割反例通过 |
| C2a 交换能力 | clustermodel/fabric/switches/model.py | 端口与内部共享容量，按路径生成约束需求 | 多端口不能绕过内部带宽；全双工计数口径明确 |
| C2b 路由 | clustermodel/fabric/routing/paths.py | 显式路径检查、最少跳确定性路由 | 路径连续且方向正确；等长路径稳定、不可达有诊断 |
| C2c 构图夹具 | clustermodel/topology/builders.py | 直连、单交换机、两分区网络的纯构图函数 | 与手工同图一致；不为 ring/fat-tree 等各建空类 |
| C3a 分组 | clustermodel/composition/groups/model.py | rank 放置、组内唯一、组间重叠和共享端点 | 多 rank 同 NIC 不增加容量；缺成员/端点被拒绝 |
| C3b 集群 | clustermodel/composition/cluster/model.py、analysis.py | 引用装配、路径账本、共享需求与下界 | 下述四节点实验、独立手算、失败和空输入通过 |
| C3c 工程接入 | evaluation/experiments/runner/cluster.py、example/cluster_demo.py、config/experiments/cluster_placement.json | 严格配置、有限放置对照、记录及回读 | 同输入预算、未知成本、失败记录可重建；不扩展通用 runner |
| C4 争用执行 | simulator/adapters、必要公共事件边界；按选型补 fabric 行为 | 一个固定版本后端或最小流级共享服务 | 生命周期、共享瓶颈、事件确定性、排空与外部范围对齐 |
| C5 AI 接入 | workloads/reference、compiler、runtime/communication、evaluation | 一个 collective 或激活/KV 路径，带来源计算/通信输入 | 数值与完整账本先成立，再评估任务性能及质量 |

当前第一项编码任务是 C1a–C1c：端点边界、单向链路和两端点图。不要等所有目录都填满才进行首次独立验证。C2/C3 接入时复用先前实例与公式。

跨目录测试拟放 `tests/clustermodel/`，公共边界与记录往返另放对应契约/集成测试位置。新增业务实现同步测试导航和 CI；不因本次文档新增预先创建空测试、空类或不可运行示例。

## 3 可独立验收的最小输入输出

| 调用 | 输入 | 输出及范围 |
| --- | --- | --- |
| estimate_link | 一个 LinkParams、payload B | packet/wire/service bytes、单链路无争用时间及覆盖 |
| validate_graph | 端点、交换端口、单向链路和共享约束 | 合法图或引用/方向/能力诊断 |
| resolve_route | 合法图、源/目标、显式路径或固定策略 | 单向边序列及经过约束；不分配动态带宽 |
| validate_groups | rank → node/endpoint 放置、group 成员 | 校验过的引用；组不是物理资源 |
| analyze_traffic | 集群图、放置、组与固定 P2P 消息 | 逐消息/链路/共享资源需求、指定割负载、时间下界 |
| 实验 adapter | 冻结配置与输入、版本/假设 | 专业 payload + Metric；runner 保存成功或失败记录 |

首批输入不含到达时间或动态依赖，不静默忽略这些信息；带时序的 trace 需显式降为静态投影并标注损失，或交给 C4。每条 P2P 消息长度为正；零字节通信控制消息不在首批范围，空消息集合是合法空工作。

## 4 四节点放置实验：独立手算基准

本节数值是**待实现验收的手算值**，不是实测、仿真输出或某型号参数。容量均为十进制 B/s；消息使用二进制 MiB。

网络：n0、n1 接交换机 sL；n2、n3 接 sR；sL 与 sR 之间有一条全双工上行。每个节点一条全双工接入和一个 NIC。所有方向均用显式边表示。

| 参数 | 夹具值与假设 |
| --- | --- |
| 每条接入方向、每 NIC 注入/接收容量 | 25×10^9 B/s（线路 200×10^9 bit/s） |
| 每条上行方向容量 | 12.5×10^9 B/s（线路 100×10^9 bit/s） |
| 每台交换内部共享容量 | 100×10^9 B/s；每消息经过该交换机按转发 payload 计一次 |
| 编码/包开销 | 理想线路：效率 1、最大 payload 4096 B/包、头尾 0 B、对齐 1 B，故本例 wire bytes = payload bytes |
| 延迟及流控 | 本例只验资源工作量下界；传播/处理延迟显式假设为 0，不推断真实设备延迟；不估队列/窗口 |
| 消息 | m0: rank0 → rank1；m1: rank2 → rank3；各 D=128 MiB=134,217,728 B，起点同时就绪 |
| 放置 A | rank0=n0、rank1=n2、rank2=n1、rank3=n3；两消息都由左向右跨上行 |
| 放置 B | rank0=n0、rank1=n1、rank2=n2、rank3=n3；两消息各在一台交换机内转发 |

同一实验只改变放置，固定消息语义、设备数、全部网络资源、路径规则和参数。B 仍有 NIC/接入/交换流量，没有经过上行不代表通信免费。

| 可手算结果 | 放置 A | 放置 B |
| --- | ---: | ---: |
| 逻辑 P2P payload 合计 | 268,435,456 B | 268,435,456 B |
| 左→右上行需求 | 268,435,456 B | 0 B |
| 全网各方向链路字节合计 | 6D = 805,306,368 B | 4D = 536,870,912 B |
| 单 NIC 最大注入/接收时间界 | 5.36870912 ms | 5.36870912 ms |
| 上行时间界 | 21.47483648 ms | 0 ms |
| 总资源时间下界 | 21.47483648 ms | 5.36870912 ms |

两者下界比为 4，不能称为实测加速比或完整训练加速比。报告必须能指向达到 max 的约束 ID 和对应消息；共享交换容量也必须进入计算，即使本例不成为瓶颈。

## 5 测试与敏感性矩阵

| 类别 | 独立案例与预期 |
| --- | --- |
| 量纲 | 200 Gbit/s = 25 GB/s；1 MB 在孤立链路上序列化为 40 μs，加显式 2 μs 启动/传播合计为 42 μs |
| 尾包 | D=1025 B、最大 payload=1024 B、每包头尾合计32 B、对齐64 B：两包分别1088/64 B，总1152 B；不使用平均包效率近似 |
| profile | raw 与 effective payload 字段混配被拒绝；缺/越域 profile 保留原因；无法推导 wire bytes 时保持未知 |
| 身份/方向 | 重复节点/端口/边/约束 ID、悬空引用、错向/断开的路径、端点中转均失败；合法拓扑环通过 |
| 确定性 | 打乱输入资源顺序不改变同一策略的路径与账本；等长路径按规范化边 ID 顺序打破平局 |
| 共享 | 两消息共享一个25 GB/s NIC，合计需求为2D，下界至少10.73741824 ms；不能按端口或 group 数倍增 |
| 双工 | 两个 D 消息反向跨上行，每方向界10.73741824 ms；显式半双工共同约束下合计界21.47483648 ms |
| 交换瓶颈 | 降低内部共享容量并手算转发需求，确认即使各端口很快仍受内部资源限制 |
| 组 | 组内重复 rank、缺 rank/端点失败；两个组合法共享成员；成员列表顺序有语义，不能擅自重排 |
| 退化/失败 | 单节点空消息返回零网络工作；本地消息无节点摘要拒绝；不可达不是无限数/零成本；正需求跨空割不可行 |
| 守恒 | 每消息源注入=目标接收 payload；按路径长度累计链路字节，约束负载不额外加入物理流量总和 |
| 敏感性 | A 的上行改25/50 GB/s，资源界应为10.73741824/5.36870912 ms；之后继续增上行不突破端点限制 |
| 消融 | 固定路由/放置分别解除共享 NIC、交换内部或上行限制，作为标注的理想对照；不用消融参数冒充现实配置 |
| 记录 | 冻结输入、假设和版本进入身份；读回重建对照；错误候选留档；能量未知不得变0；宿主时间独立 |

纯整数/字节用精确比较；时间使用与单位和数量级相匹配的容差或有理参考，不复制生产公式生成“期望值”。增加带来源真实消息分布前，先通过这些反例。

## 6 后续执行与 AI 验收门槛

C4 先调查 ASTRA-sim、SimAI、ns-3 在固定路由、多 NIC、共享容量、消息就绪、计算规约、网络粒度和生命周期方面的表达能力，形成选型记录。仓库已有资料调查不等于本机可运行。选择一个后端完成 P2P、双流共享、双工、incast、重叠组与不可达诊断；记录版本、输入转换和遗漏语义。

事件模型必须满足目标时间不倒退、请求只完成一次、资源不超容量、源释放/远端交付/目标可见的顺序、背压重试、旧 epoch 与同时间事件确定性。关闭 trace 不改变结果，停止后正确排空；缺参与者与临时拥塞分别诊断。比较有效分析下界与执行结果，低于下界先找遗漏工作和单位错误。

C5 的 collective 先验证数值与每 rank 字节，包含 p=1、p=2、尾分片、异构注入和规约成本。完整训练固定模型/数据/精度/优化器/global batch，才比较 step time 和扩展；改变算法时补 time-to-quality。推理固定请求轨迹、长度分布与质量/SLO，再比较 TTFT/TPOT/goodput，失败和未完成请求进入统计。

物理性能校准需匹配设备和软件栈的 P2P/collective 测量，可参考 NCCL microbenchmark；记录算法/协议、rank/NUMA/NIC 绑定、预热、重复次数和统计口径。拟合与留出样本分离，报告残差、误差区间及无收益条件。没有设备时继续完成静态与外部仿真范围，不能把二者吻合当作实机验证。

## 7 每批完成定义

每批都应有独立入口、参数/字段前置及行尾注释、目录和祖先 UNITS、边界/反例测试、STATUS 证据入口。物理未知、失败和未覆盖机制明确记录。C3 同步测试导航与 CI；C4/C5 另保存协议、外部版本和实验数据来源。

当前文档检查命令：

```text
python tools/check_model_rules.py
python tools/check_structure.py
```

实现测试和示例后，新增验收命令（目前尚不可运行）：

```text
python -m unittest discover -s tests/clustermodel -p "test_*.py" -v
python -m unittest discover -s tests/integration -p "test_*.py" -v
python -m example.cluster_demo
```

首批完成标志是四节点实验和所有独立入口有可重建证据；不是文件夹数量增加，也不意味着已完成事件、AI 质量或物理校准。

## 8 本次设计检查记录

2026-11-23：`python tools/check_structure.py` 通过（13个模块、146个Markdown文件、4份Word来源哈希）；四节点表、带宽敏感性及尾包数值通过独立有理数算术复核。本批无业务模型变更，因此没有把算术复核称为模型测试通过。

`python tools/check_model_rules.py` 本次未通过：compiler/src/interpret、contracts/workload、evaluation/experiments/runner、workloads/kernels、workloads/reference 的UNITS生成表待同步，compiler/src/sched和evaluation/calibration缺UNITS。检查时这些集群目录之外的路径有正在新增的训练代码；本批保留其工作区内容，没有跨任务重写。该结果只记录检查当时的工作区状态，后续以重新运行结果为准。

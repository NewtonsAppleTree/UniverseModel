# 实现状态

## 2026-11-23 chipmodel 开发任务梳理

当前进入chipmodel。[开发任务与验收计划](../chipmodel/docs/development_plan.md)已按“研究什么、怎样建模、如何证明”完成23份源码及各子目录的现状核对，明确CH1–CH10的研究问题、交付位置、依赖、证据和进入条件。首个实现包为CH1基础契约/下界修复 → CH2 SRAM访问与容量绑定 → CH3搬运路径账本 → CH4数字Tile对照；CH5复用这些基础推进CIM局部台架。CPU/GPU/NPU、外存、Die/Package及物理证据均有独立后续任务。

额外探针确认两项待修问题：接受整数工作量2^53+1 B和初始额度2^53 B、速率1 B/s时，组合资源界返回0而精确包络式为1 s；ActionEstimate.dependencies接受字符串后拆成字符。两项均列入CH1，尚未修复。图/数据路径/源读与目标写的资源绑定仍属CH2–CH4待实现范围。

本次现有chipmodel测试44项通过，chipmodel_demo运行通过：24 MAC、20 B输入、24 B输出、88 B槽预留、孤立阶段4/8/4 cycles，局部依赖下界16 ns。示例未覆盖SRAM/DRAM访问时序、背压与物理成本。源码哈希、环境、探针与示例结果保存在 `.build/chipmodel-planning-20261123`。本次交付是任务设计与文档同步，模型Python实现保持原状；后续能力不能以本次测试通过视为已完成。

模型规则检查通过62个实现目录；结构检查通过13个模块、59份模块Python、157份Markdown及4份Word来源哈希，diff空白检查通过。顶层参数清单已标注CH2拟采用的word访问与RW共享关系为规划，未新增实际配置字段。

## 2026-11-23 clustermodel 基础开发完成与收尾优化

本轮完成clustermodel基础范围，**下一轮进入chipmodel**。[完成报告及交接](../clustermodel/docs/completion.md)逐目录列出已实现能力、优化、验收与下一轮接续安排；[覆盖矩阵](../clustermodel/docs/coverage.md)中的基础范围均已落实。C1–C3与横向能力共同支持独立链路/拓扑/路由/组查询、固定P2P账本、静态停用、流量总览及可回读实验。事件队列、节点内服务、真实collective和物理校准仍按课题证据需要扩展。

收尾优化：查询使用当前不可变图的内部索引；一次分析复用相同路径和link/消息长度估算，多源可达性共享索引，构图预先汇总交换egress约束，指定割从方向账本归并。缓存不跨调用或图，保持输入/输出schema、资源身份、确定性选路和每次真实过割计费。回读补快照候选清单自身的重复、run_id唯一性、配置schema与索引字段检查，保留旧记录可选字段兼容。

新增7项测试（模型5、工程2），其中独立原始端口路径枚举验证12组图的360个端点对。最终全回归运行213项：211项通过、2项可选PyTorch测试因默认环境未安装而跳过。分组为contracts 6、clustermodel 72、chipmodel 44、workloads 16、compiler 17、integration 58（其中2项跳过）；网络相关累计103项通过。模型规则覆盖62个实现目录；结构检查通过13模块、59份模块Python、156份Markdown及4份Word来源哈希。本地验证不表示远端CI已执行。

Windows/Python 3.12.4宿主基准预热1次、测量3次：64节点/512条重复端点对消息的分析中位数1.1663→0.01816 s；32节点/992条全互发消息0.4780→0.05125 s；Python分配峰值分别降低45.2%/27.3%。完整图/输入/分析结果/总览哈希优化前后相等。这里只度量模型程序开销，不是目标网络加速或物理证据；脚本与限制见[完成报告](../clustermodel/docs/completion.md)。

单链路、四节点放置、leaf-spine、单spine停用、双spine不可达五组CLI记录均保存/回读一致，四组历史记录回读通过。原有手算结果保持：42 μs孤立链路；四节点21.47483648/5.36870912 ms资源界；六节点113,246,208 frame B和0.67108864 ms资源界。双spine停用保留原需求与失败原因。

本地产物位于 `.build/cluster-closeout-20261123`，保存源码、基准、测试、案例和wheel验证记录。来源为`b47550e9f39c93cacc8faeb01cff6f0f046a2705+python-config-sha256:b7191129cb93a37c264a0277e7102a17f30688d1dd280984dd7fb323c85a51d7`，覆盖94个仓库Python、实验JSON和pyproject文件，排除文档/构建产物。`.build/cluster-closeout-wheels`中的wheel构建通过，57份打包Python源码与工作区相同，并在`python -I`隔离解释器中通过路由、分析、静态停用、runner和回读验证。本轮没有修改chipmodel实现。

## 2026-11-23 clustermodel 广度复核与横向扩展（历史批次）

按用户要求，本轮重点继续为clustermodel，采用“先全面覆盖，再细化机制”的顺序。新增[12维覆盖矩阵](../clustermodel/docs/coverage.md)，逐项列明研究用途、模块责任、可运行基础与深化条件；不把固定P2P示例的完成等同于全部集群能力已实现。

本批补充四组可独立调用的横向能力：[leaf-spine、拓扑库存/方向可达性、静态停用视图](../clustermodel/topology/UNITS.md)，[最短路径精确计数及有界候选](../clustermodel/fabric/routing/UNITS.md)，[rank/node/endpoint/group和节点矩阵需求总览](../clustermodel/composition/cluster/UNITS.md)。实验配置可保存共享outage来源与原图，成功payload新增总览；CLI的--overview只显示保存观测，旧记录缺新观测时不重算。

六节点、三leaf、双spine的30条1 MiB合成P2P需求验证：逻辑量31,457,280 B，各节点发送/接收各5 MiB；链路帧量113,246,208 B；固定字典序路由资源界0.67108864 ms。跨leaf有两条最短路径，共享接入/NIC，不把路径数乘容量。停用一个spine后在新静态图查询可保留一条路径，本例工作量/界不变；两个spine停用后保留原始需求并保存不可达失败。没有故障收敛/恢复时延或概率可靠性结论。

新增24项测试（模型18、工程6）通过，网络相关测试累计96项。本轮相关回归为clustermodel 67项通过、integration 56项运行（54项通过、2项可选PyTorch因环境缺失跳过）；其他模块历史验证见下方，不把其旧结果称为本批重跑。模型规则覆盖62个实现目录，结构检查通过13个模块、59份模块Python实现、155份Markdown及4份Word来源哈希。

已保存基线、单spine停用与不可达三组记录，成功/失败回读一致，并验证上一阶段旧bundle可读取。产物位于 `.build/cluster-breadth-20261123`，含source_snapshot.json与validation.json；来源为`b47550e9f39c93cacc8faeb01cff6f0f046a2705+python-config-sha256:93c441970815f4a83071074f0f5f4980cc7f906f4aa43c430da06c68a91b9eec`，覆盖92个Python、实验JSON与pyproject文件，排除文档/构建产物。wheel位于 `.build/cluster-breadth-wheels`，13份相关源码与工作区一致，在隔离解释器中验证拓扑、多路径、静态停用和分析。CI加入leaf-spine保存/回读，本地验证不代表远端CI运行。

```text
python -m example.cluster_demo --config config/experiments/cluster_leaf_spine.json --overview
python -m example.cluster_demo --read .build/cluster-breadth-20261123/baseline --overview
python -m unittest discover -s tests/clustermodel -p "test_*.py" -v
python -m unittest discover -s tests/integration -p "test_cluster*.py" -v
python tools/check_model_rules.py
python tools/check_structure.py
```

本轮未进入chipmodel。后续深度按证据缺口选择：节点内部资源/本地服务由systemmodel补边界，collective数值与任务语义由上层提供，动态队列/可见性由事件后端验证，物理性能/能量由校准支持。当前静态模型明确保留未知量与未覆盖机制，见[横向指南](../clustermodel/docs/breadth_usage.md)。

## 2026-11-23 clustermodel C1–C3基础阶段记录

已完成[链路/交换与固定路由](../clustermodel/fabric/UNITS.md)、[端口图/指定割/构图](../clustermodel/topology/UNITS.md)、[rank/group与集群分析](../clustermodel/composition/UNITS.md)，以及[四节点配置、比较与保存回读](../clustermodel/docs/foundation_usage.md)。C1直连schema继续可用，交换图显式采用routed-network-graph/v1；NIC、交换、共享介质各有唯一owner/容量，没有第二份NIC或事件引擎。

固定同资源预算与两条128 MiB消息：跨分区A的帧量805,306,368 B、资源界21.47483648 ms；分区内B为536,870,912 B与5.36870912 ms。上行需求268,435,456/0 B，NIC最大界均为5.36870912 ms。独立常数验证一致，4倍是条件下界之比，不是训练或实测加速。

每消息保留路径、逐hop profile与各容量约束需求；交换每次crossing计一次，重复过割逐次计量，多rank/端口/组共享同一NIC容量。必要传播/处理界与资源/割界取max，不叠加完整消息逐hop序列化。未知帧量/完整能量保持None与原因。同节点服务摘要未接入；相关需求明确失败。当前不覆盖争用执行、目标内存可见、collective数值、完整AI质量或物理校准。

本次新增33项C2/C3测试（模型23、工程10），连同C1共有72项网络相关测试。此次全回归运行182项：180项通过，2项可选PyTorch测试因默认环境未安装而跳过；分组为contracts 6、clustermodel 49、integration 50、chipmodel 44、workloads 16、compiler 17。两个规则检查通过：62个实现目录，13个模块、56份模块Python实现、153份Markdown和4份Word来源哈希。CI加入cluster保存/回读，本地通过不等同远端CI已执行。

wheel已构建，并核对10份相关模型/adapter源码与工作区一致；在隔离解释器中从解包wheel运行四节点配置得到相同下界。实际CLI保存/回读结果完全相同，产物位于 `.build/cluster-foundation-20261123`，wheel位于 `.build/cluster-foundation-wheels`。产物保存`source_snapshot.json`，代码来源为`b47550e9f39c93cacc8faeb01cff6f0f046a2705+python-config-sha256:f533ac8de52de0a8acf35020ba182f65dbcfec279d360f36f136f9d50a6cb037`；快照覆盖86个仓库Python、实验JSON与pyproject文件，不包含文档与构建产物。

```text
python -m example.cluster_demo
python -m example.cluster_demo --read .build/cluster-foundation-20261123
python -m unittest discover -s tests/clustermodel -p "test_*.py" -v
python -m unittest discover -s tests/integration -p "test_*.py" -v
python tools/check_model_rules.py
python tools/check_structure.py
```

本节保留C1–C3阶段验收记录。后续横向能力与收尾优化已完成，最新交付状态见本文开头。

## 2026-11-23 集群C1历史记录

完成[公共端点与共享容量](../contracts/hardware/UNITS.md)、[单向链路](../clustermodel/fabric/links/UNITS.md)、[直连拓扑](../clustermodel/topology/UNITS.md)。冻结/版本/单位/来源、raw_line与effective_payload互斥、精确尾包、profile范围、未知线量、端口归属与双工连接、直接可达查询和指定有向节点割已实现。交换机/内部转发、自动路由、rank/group、共享业务需求账本与事件执行尚未实现。

[C1示例](../clustermodel/docs/c1_usage.md)复用严格配置、通用runner及本地bundle。默认1 MB消息在显式200 Gbit/s方向上的序列化40 μs，加启动/传播各1 μs得到孤立链路42 μs；该时间不含NIC、共享排队、软件launch或目的内存可见。总能量未知；输入/有效参数/来源和失败记录可保存/回读。

本批新增39项测试通过（contracts 6、links 13、topology 13、integration 7）。完整integration回归运行40项，其中38项通过、2项可选PyTorch测试因默认环境未安装而跳过。57个实现目录的模型规则检查及结构/允许依赖/链接/4份Word来源哈希通过，wheel构建通过并核对三个C1模型源码与工作区一致；CI已加入契约/集群测试和network示例保存/回读，尚不代表远端CI结果。核对时源码基线为`b47550e`加当前工作区；示例source_revision默认unrecorded。

```text
python -m example.network_demo
python -m example.network_demo --output .build/network-c1
python -m example.network_demo --read .build/network-c1
python -m unittest discover -s tests/contracts -p "test_*.py" -v
python -m unittest discover -s tests/clustermodel -p "test_*.py" -v
```

C1完成时的下一步为C2交换与路由；现已完成C2/C3，以上数字保留为当时范围。最新能力与验证见本文开头和[基础指南](../clustermodel/docs/foundation_usage.md)。

## 2026-11-23 训练实现补充

在 `5ebefa1` + 当前工作区完成 [Linear 训练 step 与短链](../evaluation/docs/training_step.md)：float64、无 bias、Linear/ReLU/identity、mean MSE、全部 dW/dX 与 plain SGD。梯度绑定旧权重版本/内容身份，更新返回不可变新状态；显式转置、保存激活和命名张量生命周期进入独立 backing 容量检查，GEMM scratch 另计。

默认两层案例三个合法方案均通过精确有理数参考与 PyTorch 2.5.1+cpu autograd/SGD 对照：120 MAC，另有 58 次辅助算术、16 次比较/选择各、34 个转置元素；backing 峰值 568 B，GEMM payload 1392/1680/1840 B，辅助逻辑 payload 1448 B。超 scratch 候选保留失败记录。完整 step 时间/能耗未知，GEMM 子集下界不作为训练加速比。

最新验证：默认标准库环境 108 项通过、2 项可选 PyTorch 测试跳过；在固定 PyTorch 环境这两项另行通过，共 110 项不同测试具备通过记录。52 个实现目录的规则检查及结构/依赖/链接/4 份 Word 源哈希通过；下方集群设计批次曾观察到的训练 UNITS 缺失/生成区未同步已在本批补齐。CI 已加入训练保存/回读和独立 PyTorch job，本地通过不表示远端 CI 已执行。开发/验收见[训练计划](development/training_step_plan.md)。

训练功能对照不等同于性能/成本校准，也不代表 Megatron/DeepSpeed、分布式训练或收敛实验已经实现。clustermodel 的当前模块安排与下方独立设计记录保留。

```text
python -m example.training_demo
python -m example.training_demo --output .build/training-study
python -m example.training_demo --read .build/training-study
```

## 既有设计更新与线性首批记录

C0历史设计记录（2026-11-23）：细化 [clustermodel设计](../clustermodel/docs/design.md)、[开发验收](../clustermodel/docs/development_plan.md)及10个UNITS目录；当时仅修改文档，未新增集群模型。当前C1–C3实现证据见本文开头；下方2026-11-20代码记录保持原范围。

本设计批次检查：结构检查通过；模型规则检查发现其他训练开发路径的UNITS缺失/生成表待同步，见[检查记录](../clustermodel/docs/development_plan.md)。未将历史业务测试通过记录扩展为当前整个工作区已通过。

核对日期：2026-11-20。代码基线：`5ebefa1` + 本轮工作区；新增首个线性算子功能/分析实验与 27 项测试，复用原 chipmodel 和通用工程接口。2026-11-06 的 `6b36384` 核对是此前基础能力记录。

同日早先文档更新：新增根目录[项目使命与顶层要求](../PROJECT_MISSION.md)，同步仓库入口、开发约束、总览与架构导航；Word 构建器为围栏代码块增加同页约束，保持短文本图完整。该文档批次没有新增模型；后续实现见下表和本轮验收记录。

调研与路线更新：2026-11-20，基于 `5ebefa1` 核对缺口，新增[开源调研](reference/open_source_landscape.md)、[102 个候选的横向对照](reference/open_source_comparison.md)、[数据快照](reference/data/open_source_snapshot_2026-11-20.json)与[研究开发路线](RESEARCH_ROADMAP.md)。取得 101 个仓库元数据并核对 README、核对 44 篇代表论文的引用记录；ONNX Runtime 已核对官网，仓库数据待复核，仍保留收录。GitHub 热度与学术影响并列、同模块多候选比较；尚未运行外部项目或复现论文。

语料补充：已核对 AI 编译课程解读、端侧框架截图与训练候选，形成[软件语料审阅](reference/ai_software_corpus_review.md)。新增 25 个仓库和 14 篇论文记录已计入上述总数；优先补充 PyTorch/Megatron/DeepSpeed/TorchTitan 与 TVM/IREE/tpu-mlir/端侧框架调查。两个 Optimus 按用户方向仅保留历史参考；外部框架适配、运行时和训练执行能力仍未实现。

**已具备 chipmodel 基础模型、通用工程短路径与首个可比较的线性算子实验。** workloads → compiler → 功能参考/MAC-DMA 分析 → evaluation/artifacts 已贯通，并保留独立调用。完整图编译、训练、真实设备/事件执行、一般搜索器与 UI 仍待实现。当前不包含 RTL，也不将分析时间界当作实际仿真时间。

## 能力与证据

| 能力 | 状态 | 验证或阅读入口 |
| --- | --- | --- |
| 模块目录与允许依赖 | 13 模块清单、依赖 DAG 与实际 Python import 检查 | [modules.json](architecture/modules.json)、[检查脚本](../tools/check_structure.py) |
| 架构及公共语义 | ExperimentSpec/Metric/RunRecord、canonical JSON v1 与窄范围 LinearSpec/Inputs/Plan 可用；一般硬件/图计划/事件 schema 仍为提案 | [工程框架](../ENGINEERING_FRAMEWORK.md)、[公共值入口](../contracts/UNITS.md)、[公共契约](interfaces/contracts.md) |
| 通用独立运行 | 同一 JSON/显式覆盖与注入接口可独立运行 ADC、DMA；记录模式、假设、单位、未知值、输入身份和失败诊断 | [运行入口](../evaluation/experiments/runner/single.py)、[通用示例](../example/universal_demo.py) |
| 线性工作负载与独立参考 | 正整数、row-major GEMM/MatVec；INT8/INT64 与 float64，稳定输入生成、逻辑工作量、精确整数/有理数参考、显式容差 | [workloads](../workloads/UNITS.md)、[工作负载测试](../tests/workloads/test_linear.py) |
| 映射与功能执行 | output_stationary/reload_partials；尾块、覆盖/归约顺序/C 生命周期检查，三缓冲容量、逐行外部流量、功能解释 | [compiler](../compiler/src/UNITS.md)、[编译测试](../compiler/tests/test_linear_mapping.py) |
| 线性实验比较 | 复用 MAC/DMA 服务，给出条件化资源下界；同输入有限候选、保留容量失败、能耗未知、独立数值质量、保存/回读 | [指南与手算结果](../evaluation/docs/linear_mapping.md)、[集成测试](../tests/integration/test_linear_experiment.py) |
| 独立组件与局部仿真 | 各子模块可独立查询；已有局部资源/操作组合示例；公共事件驱动器与 BenchSpec schema 尚未实现 | [系统级设计](../chipmodel/docs/system_model_design.md)、[局部示例](../example/chipmodel_demo.py)、[事件接口提案](interfaces/component_protocols.md) |
| ADC 功能与分析 | 显式参数/单位/公式校验、均匀 offset-binary 电压量化、越限标记、无争用批次时序；无背压或电路成本 | [模型说明](../chipmodel/docs/adc_model.md)、[Python 实现](../chipmodel/compute/cim/periphery/adc.py)、[运行示例](../example/adc_demo.py) |
| 计算与 CIM | CPU μop 能力、GPU 静态驻留、GEMM 工作/MAC 服务、位串行动作、电导阵列/TIA、DAC、保持限制、最终位权累加；无 ISA 或动态调度 | [compute 参数入口](../chipmodel/compute/UNITS.md) |
| 存储与搬运 | SRAM/buffer/cache 几何、DRAM 组织/接口、隔离行读、NAND 几何/串行时延、DMA 服务与 TMA 布局；无缓存命中、刷新、FTL 或队列状态 | [memory](../chipmodel/memory/UNITS.md)、[control](../chipmodel/control/UNITS.md) |
| 互连与物理条件 | 无争用 NoC 路径、D2D 分包/编码、同层矩形校验、一阶热 RC；不覆盖协议状态机、多节点热或电路校准 | [interconnect](../chipmodel/interconnect/UNITS.md)、[packaging](../chipmodel/packaging/UNITS.md) |
| 系统组合与创建 | 身份/归属/静态端口兼容检查、摘要/细节计量选择、操作 DAG 和资源供给包络下界、显式小型注册表 | [composition](../chipmodel/composition/UNITS.md)、[registry](../chipmodel/registry/UNITS.md) |
| 仓库开发规则与参数文档 | 根目录/模块 AGENTS.md；chipmodel 全部 27 个目录与其他实际实现目录/祖先，共 49 个 UNITS.md 检查范围；字段/接口表从代码生成 | [规则](development/model_rules.md)、[总入口](../chipmodel/UNITS.md)、[检查工具](../tools/check_model_rules.py) |
| 顶层设计参数查阅 | 已整理计算/存储/互连、物理条件与 AI 工作量的候选参数、单位、公式和来源边界；不新增模型能力 | [参数清单](../ARCHITECTURE_PARAMETERS.md)，含 DDR/HBM/Flash、CIM 与原材料修正 |
| 训练/推理场景架构 | trainingArch/inferArch 已有 README 与 UNITS 参数入口，复用 13 个基础模块；未实现独立分析器、调度器或执行器 | [训练](../trainingArch/README.md)、[推理](../inferArch/README.md) |
| 张量区域与编译规约设计 | 已实现线性矩形 tile/顺序归约；一般 ROI/indexing map、attention/context 归约和图 pass 仍为提案 | [区域契约](interfaces/tensor_regions.md)、[编译设计](../compiler/docs/tiling_and_reduction.md)、[审阅统计](reference/layout_roi_review.md) |
| 异构结构示例 | 可检查引用；不可作为执行配置 | [示例说明](../example/specs/README.md)、[结构 JSON](../example/specs/heterogeneous_topology.json) |
| 配置与 UI | 严格 JSON → 冻结嵌套 dataclass、默认/文件/调用覆盖、producer 构造校验可用；无模板继承、公式解释器、YAML、迁移或 UI | [配置入口](../configuration/UNITS.md)、[配置设计](../configuration/docs/design.md)、[UI 设计](../ui/docs/design.md) |
| 未实现的编译/硬件机制 | 完整 IR/图划分/自动求解/lowering 未实现；细化 CPU/GPU、协议/一致性、PHY 等按研究问题加入 | [单元覆盖清单](../chipmodel/docs/component_inventory.md)、[Unit 类与参数设计](../chipmodel/docs/unit_model_design.md) |
| runtime 与 simulator | 无可运行的请求执行和事件引擎 | [运行时设计](../runtime/docs/design.md)、[仿真器设计](../simulator/docs/design.md) |
| clustermodel | 固定P2P基础与leaf-spine、多路径查询、静态停用/可达性、需求总览可用；本轮先广度后深度 | [覆盖矩阵](../clustermodel/docs/coverage.md)、[横向指南](../clustermodel/docs/breadth_usage.md)、[Unit](../clustermodel/UNITS.md) |
| 实验与产物 | 单次/有限候选与小数据本地 bundle 可用；run.json + 最终 manifest，拒绝覆盖，读取重做哈希/身份/结构校验；无一般搜索器、blob/轨迹、checkpoint 恢复 | [实验入口](../evaluation/UNITS.md)、[产物入口](../artifacts/UNITS.md)、[产物规范](interfaces/artifacts.md) |
| Python 工程打包 | pyproject 声明 Python 3.10+ 与 13 模块查找范围；wheel 构建通过，新增 workloads/compiler 实现，运行代码无外部依赖 | [pyproject.toml](../pyproject.toml)、[工程使用](../ENGINEERING_FRAMEWORK.md) |
| 文档构建 | 已有四个维护中的 Word 构建配置 | [构建清单](tools/documents.json)、[构建脚本](tools/build_docx.py) |
| 自动验证 | 本地 87 项通过：44 chipmodel + 9 workloads + 9 compiler + 25 integration（原 16 + 新 9）；CI 已纳入四组测试、规则/结构、模型/通用/线性示例、保存回读与 wheel | [测试说明](../tests/README.md)、[GitHub 工作流](../.github/workflows/structure.yml) |

结构检查只证明目录、允许依赖/实际 import、链接、示例引用和 Word 来源一致；规则检查只证明注释结构和参数文档同步。业务测试验证已声明的功能/分析语义，不构成电路精度或性能校准。通用 runner 不推进目标时间；BenchSpec、一般图计划与事件格式仍是提案。source_revision 默认 unrecorded，输入快照/哈希不等于完整源码可复现。

线性默认案例 M/N/K=5/4/7、INT8、64 B scratch：三项合法候选流量 314/954/370 B，资源时间下界 348/588/460 ns，数值均通过；整块映射需要 223 B，容量失败留档。生命周期/尾块/手算、浮点消减反例、带宽/容量敏感性、格式能力及产物回读已验收；开发记录见[计划](development/linear_experiment_plan.md)。

## 现在能运行的命令

在仓库根目录运行：

```text
python tools/check_structure.py
python tools/check_model_rules.py
python -m unittest discover -s tests/chipmodel -p "test_*.py" -v
python -m unittest discover -s tests/workloads -p "test_*.py" -v
python -m unittest discover -s compiler/tests -p "test_*.py" -v
python -m unittest discover -s tests/integration -p "test_*.py" -v
python -m example.adc_demo
python -m example.chipmodel_demo
python -m example.universal_demo --case adc
python -m example.universal_demo --case dma --set inputs.payload_bytes=64
python -m example.linear_demo
python -m example.linear_demo --output .build/linear-study
python -m example.linear_demo --read .build/linear-study
python docs/tools/build_docx.py --document overview
```

业务检查/示例使用 Python 3.10 及以上的标准库；最后一条需要 [文档依赖](tools/requirements.txt)。修改字段或定义说明后，用 `python tools/check_model_rules.py --write-docs` 刷新 UNITS.md 生成区。示例中的频率/服务参数是显式假设；`example/specs` 下的 JSON 仍不是可执行配置。通用示例使用独立的 `config/experiments/universal_*.json` schema。

## 下一步和更新规则

长期目标按[项目使命](../PROJECT_MISSION.md)执行；近期优先级与验收统一见[研究开发路线](RESEARCH_ROADMAP.md)，本节保留下一步摘要，具体课题另有实验材料，不写入使命正文。

本轮重点保持clustermodel：先按[覆盖矩阵](../clustermodel/docs/coverage.md)检查12个维度的基础能力、外部边界和验证证据，再按具体研究问题深化队列/窗口、策略/任务依赖或物理校准。已补leaf-spine、多路径、静态可用性与需求矩阵。chipmodel留到后续轮，本轮未修改其实现。

既有线性路径的后续任务保留：Linear 前向/反向/更新及短算子链、梯度与状态版本、固定版本 PyTorch 功能对照、Timeloop/Accelergy及ZigZag/SCALE-Sim共同可比案例、带来源条件成本和误差报告。按实际复现决定适配，接口规则见[工程框架](../ENGINEERING_FRAMEWORK.md)。

CIM array + DAC/ADC + 缓冲仍是后续局部台架：先验收精确整数 MatVec、数值/静态时序/字节/动作账本，再做 GEMM ROI 和单层训练/推理资源账本。本轮未实现 run_cim_matvec，71-cycle 与 lane 扩展时间仍是台架验收方案；步骤见[局部仿真规划](architecture/composable_simulation.md)与 [B/C 门槛](architecture/validation.md)。

BenchSpec 等新对象与计划生产者字段目前属于提案，现行公共契约的修订清单见上述规划第 10 节。代码级功能/事件模型先行，周期、RTL 与电路校准按[精度选择](architecture/instruction_and_fidelity.md)的触发条件加入。

每次能力发生变化，更新对应行、核对日期、代码基线和证据入口；部分可用时写明支持范围及尚未通过的验证。新增模块或改变依赖还要更新 [modules.json](architecture/modules.json)，该清单只记录结构信息。其他文档引用本页，不另行维护完成状态；参考资料的“首版建议”不等于已实现功能。其他变更的维护位置见[文档维护规则](README.md)。

# 实现状态

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

最近设计更新：2026-11-23，按当前逐模块开发顺序细化 [clustermodel 设计](../clustermodel/docs/design.md)、[逐目录开发与验收](../clustermodel/docs/development_plan.md)及10个目录的 UNITS。首批为静态端点/资源图、固定路由、通信账本和时间下界；本批仅修改文档，未新增集群 Python 模型、事件执行或校准证据。下方2026-11-20代码核对记录保持其原范围。

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
| clustermodel | 逐目录设计、参数与手算验收方案已细化；端点/链路/图/组/通信分析及执行均未实现 | [Unit 导航](../clustermodel/UNITS.md)、[C1–C5开发计划](../clustermodel/docs/development_plan.md) |
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

当前先推进 clustermodel 的独立分析路径：C1 公共端点/链路/图 → C2 交换容量/路由 → C3 资源组/集群账本/实验回读。首个编码批次是只读端点边界、单向链路和两端点图，不等待完整 Node 或事件引擎；四节点放置对照的手算值仅作为待实现验收。C4 争用执行与 C5 AI场景按证据需求进入，详见[开发计划](../clustermodel/docs/development_plan.md)。

既有线性路径的后续任务保留：Linear 前向/反向/更新及短算子链、梯度与状态版本、固定版本 PyTorch 功能对照、Timeloop/Accelergy及ZigZag/SCALE-Sim共同可比案例、带来源条件成本和误差报告。按实际复现决定适配，接口规则见[工程框架](../ENGINEERING_FRAMEWORK.md)。

CIM array + DAC/ADC + 缓冲仍是后续局部台架：先验收精确整数 MatVec、数值/静态时序/字节/动作账本，再做 GEMM ROI 和单层训练/推理资源账本。本轮未实现 run_cim_matvec，71-cycle 与 lane 扩展时间仍是台架验收方案；步骤见[局部仿真规划](architecture/composable_simulation.md)与 [B/C 门槛](architecture/validation.md)。

BenchSpec 等新对象与计划生产者字段目前属于提案，现行公共契约的修订清单见上述规划第 10 节。代码级功能/事件模型先行，周期、RTL 与电路校准按[精度选择](architecture/instruction_and_fidelity.md)的触发条件加入。

每次能力发生变化，更新对应行、核对日期、代码基线和证据入口；部分可用时写明支持范围及尚未通过的验证。新增模块或改变依赖还要更新 [modules.json](architecture/modules.json)，该清单只记录结构信息。其他文档引用本页，不另行维护完成状态；参考资料的“首版建议”不等于已实现功能。其他变更的维护位置见[文档维护规则](README.md)。

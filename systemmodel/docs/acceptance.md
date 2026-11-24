# systemmodel S0–S7 整体验收报告

验收日期：2026-11-24。依据[项目使命](../../PROJECT_MISSION.md)、[开发计划](development_plan.md)和[模型规范](../../docs/development/model_rules.md)，对本轮基础范围重新核查、运行、保存与回读。

**结论：S0–S7 基础范围通过整体验收。** 本次发现并修复两处统一验收器缺口，新增9项回归测试。默认环境555项测试中553通过、2项可选PyTorch测试跳过；这2项随后在既有PyTorch环境中通过，555项均已有本轮通过证据。六组81个默认案例、历史记录回读及隔离wheel验证通过。已声明范围内没有遗留验收阻断项；完整协议、动态执行和实测性能属于后续研究深化。

## 1 逐包验收

| 包 | 支持的研究问题与建模边界 | 本轮核对的证据 | 结论 |
| --- | --- | --- | --- |
| S0 边界与契约 | 资源、地址域、权限与成本归属；标准库公共接口 | 不可变身份、精确整数、非法声明、所有权与重复计量反例；contracts及foundation测试 | 通过 |
| S1 板卡、节点与拓扑 | 显式有向路径、端口/域跨越、共享约束与P2P可达性 | 30组独立穷举路径；7例保存/回读，3成功、4预期失败 | 通过 |
| S2 内存与NUMA | backing容量、对象/副本/视图、半开生命周期与NUMA位置 | 200组逐字节/阶段参考；15例，6成功、9预期失败；容量取整、别名、权限与过期反例 | 通过 |
| S3 PCIe与DMA | conventional posted-write、整copy依赖、staging与唯一服务工作 | 160组独立分包参考；14例，7成功、7预期失败；字节守恒、共享服务与启动/带宽敏感性 | 通过 |
| S4 CXL与分层内存 | 显式模式/decoder、同phase容量、完整对象三状态迁移 | 100组独立行参考；15例，7成功、8预期失败；瞬时双份容量、对象绑定与模式反例 | 通过 |
| S5 NIC与集群组合 | 有限buffer、TX/RX供数、注册/权限、唯一NIC预算与local消息 | 12例，4成功、8预期失败；源/目标数据版本/offset绑定、共享NIC、同节点零fabric工作、保存路径回读 | 通过 |
| S6 AI任务与瓶颈解释 | Linear/训练/Attention实际输入、独立数值参考、节点容量和准备工作 | 默认18例，15成功、3容量失败；另18个可替换任务/策略组合；独立PyTorch autograd/SGD验证 | 通过 |
| S7 工程与完整验收 | 失败保留、全名单、来源、不可变产物、规则、依赖和打包 | 81例完整run/read；176份产物；555项测试；wheel隔离81例；新验收器反例 | 通过 |

六组共 **42成功、39预期失败**。39项失败均保留实际诊断，本轮逐项核对为容量、生命周期、权限、路径、迁移或绑定约束的拒绝；这些是负向研究案例，不是测试套件故障。保存回读保留历史失败诊断，不重新执行失败案例来伪造历史证据。

## 2 发现、修复与复验

| 发现 | 修复前复现 | 修复与验证 |
| --- | --- | --- |
| 总报告来源未绑定各条实验记录 | 在临时副本中替换source.json的文件哈希及聚合身份，同步外层报告并重算产物哈希，旧验收器仍接受原来源的81条记录 | [统一工具](../../tools/validate_systemmodel.py)重算保存的源码清单摘要，读取每个不可变index/run manifest，核对全部成功与失败记录的source_revision；混合来源、重标顶层来源均拒绝 |
| 成功案例身份未固定 | 将一个成功案例改名，保留总数与失败名单，旧check_rows仍接受 | 固定六组成功及失败案例身份；替换、缺失、重复、未完成、异常成功/失败均拒绝 |

新增[验收器测试](../../tests/integration/test_systemmodel_acceptance.py)8项，覆盖上述缺口、源码清单不一致、文件增加/缺失/字节改动、内层manifest、只读回放与已有目录保护。摘要哈希只能证明保存内容内部一致，不构成外部签名或硬件实测认证；回读也不要求当前工作区仍等于历史源码。

[AI组合测试](../../tests/integration/test_system_ai_experiment.py)另增1项：6个不同任务各跑resident/direct/staged，共18组合。覆盖INT8尾块及INT64输出、float64非整tile、单层与三层训练、identity激活、批量因果GQA和不等头数。输入分别为16/160/88/184/608/208 B，准备工作严格对应0/1/2倍输入；数值独立参考与保存回读一致。这18组合在测试内部执行，不额外计入默认81例。

本轮仅修改统一验收工具和测试，未改动硬件/AI生产模型。新旧默认案例的输出、状态、预期及诊断全部一致；源码变化导致记录identity_hash按设计变化。上一轮完整验收包仍可被加强后的工具读取，原有176份产物哈希不变。

## 3 测试与工程证据

每个discover组使用独立进程，避免同名测试模块污染。

| 测试组 | 数量 | 默认环境结果 |
| --- | ---: | --- |
| contracts | 8 | 全通过 |
| clustermodel | 72 | 全通过 |
| costmodel | 7 | 全通过 |
| chipmodel | 141 | 全通过 |
| systemmodel | 79 | 全通过 |
| workloads | 47 | 全通过 |
| compiler/tests | 20 | 全通过 |
| integration | 181 | 179通过，2可选PyTorch跳过 |
| 合计 | 555 | 553通过，2跳过 |

默认解释器为Python 3.12.4。既有`.build/torch-crosscheck`环境使用PyTorch 2.5.1+cpu、float64；其中2项autograd/SGD及外部记录来源测试通过，补齐默认环境的跳过项。它们提供CPU数值参考，不提供目标系统性能或任务数据集质量证据。环境提示未安装NumPy，但这两项验证不调用NumPy，执行成功。

模型规则、模块依赖/结构、文档链接与Git空白检查另行运行，日志保存在下述证据目录。未将宿主运行耗时纳入目标性能，也未恢复GitHub Actions。

wheel：`.build/systemmodel-review-wheels/UniverseModel-0.1.0-py3-none-any.whl`，SHA256：

```text
322b4e8098481f5de43187049f138749460bb1e4c4dad7fbda0fb6a476e07154
```

121份打包Python文件的完整名单与原始字节均匹配工作区。`python -I`从独立解包目录导入68份项目模块，在标准库依赖范围重新执行全部81例并回读工作区记录，结果一致；配置由仓库提供。验收CLI、示例与测试仍是源码仓库工具，不声称wheel独自携带这些入口和数据。

## 4 来源、保存与复现

本地证据目录：`.build/systemmodel-review-20261124`。其中保存轮初`before.json`、最终代码`source.json`、8组测试日志、`acceptance/`完整实验、规则/结构日志、修复前后探针、历史兼容核对、wheel审计、PyTorch环境、Git索引保护、远端CI只读状态和最终`validation.json`。这是本地运行产物，文档中的结果和来源摘要用于仓库内长期查阅。

来源覆盖233份Python/config/pyproject，包含尚未提交的实际文件字节：

```text
cea6acc6b56883321280c8764c879fef6bb79482+python-config-sha256:ce9e5cb99c5c1fe4074bd240261b10287d63f960fd209644eda0b1131166852c
```

相比轮初232份来源文件，修改`tools/validate_systemmodel.py`及AI组合测试，新增验收器测试；其余230份保留。文档同步更新。原有未提交修改保留，未stage/commit/push，Git索引不变。CI工作流401630842只读查询仍为`disabled_manually`。

从仓库根目录执行，输出目录须不存在：

```powershell
python tools/validate_systemmodel.py --output .build/systemmodel-acceptance-new
python tools/validate_systemmodel.py --read .build/systemmodel-acceptance-new
python tools/check_model_rules.py
python tools/check_structure.py
git diff HEAD --check

# 逐组独立运行；目录依次使用tests/contracts、tests/clustermodel、tests/costmodel、
# tests/chipmodel、tests/systemmodel、tests/workloads、compiler/tests、tests/integration。
python -m unittest discover -s tests/systemmodel -p "test_*.py" -v

# 既有可选PyTorch环境；默认安装不要求该依赖。
.build/torch-crosscheck/Scripts/python.exe -m unittest discover -s tests/integration -p test_training_experiment.py -k PyTorchTrainingTests -v
```

## 5 验收结论的适用范围

本轮证明静态资源/容量/访问/搬运声明的正确性、服务必要下界的计算，以及合成AI算子/梯度/状态的数值正确性。NIC导出的容量只计一次；独立scratch与节点backing分开；保留packed训练输入时另留全部非initial tensor空间，不能复用编译器已释放输入的峰值。源、策略、预算干预和未知成本均保留。

不据此主张完整PCIe/CXL/RDMA协议、动态争用/重叠/一致性、真实复制和完成发布、数据集accuracy、端到端加速比或总能耗。原生CXL服务时间、scalar/softmax及内部供数等未知成本保持明确未知。resident假设输入已经在目标，不能与direct/staged直接构成同初态的端到端性能比较。

后续按具体研究问题选取runtime/simulator执行机制、实测标定或真实任务质量门槛。无需为“基础验收完成”提前实现这些独立课题。

# 实现状态

## 2026-11-23 workloads完成审计与数值/回读修复

W0–W6既定任务已经完成，本次按使命复核后补齐真实边界缺陷，详情见[收尾审计](../workloads/docs/completion_audit.md)。9个均匀key、同类one-hot V的合法Attention输出出现`1.0000000000000002`，此前被概率有效域拒绝；现在概率端点/行和使用明确1e-9容差，原始观测与argmax不变，log-loss限制在显式floor与1之间，避免负loss。越界/行和错误及独立数值不合格仍被检出。

mapping/retrieval新implementation v2保存参考输出，NumPy另存Attention与直接RBF实际输出；回读从观测重算数值比较与外部分类质量，核对计划/行所有权、资源守恒/边界、选参计数、训练标签/类配额、任务维度/scale/one-hot V、预测变化与记录指标。任务配置/bundle保持v1，历史implementation v1实际回读通过；其缺失参考输出，不能宣称重新计算数值误差。回读不生成输入、不拟合/执行模型或外部参考，不提供第三方认证或完整物理性能证据。

新增6项测试，全回归425项：423通过，2项可选PyTorch因未安装跳过；NumPy 2.2.6实际通过。分组contracts 6、clustermodel 72、costmodel 7、chipmodel 141、workloads 47、compiler 20、integration 132。统一27例保留23个执行成功、4个预期执行失败以及成功中的3个质量负对照。规则通过68个目录，结构通过13模块、103份模块Python、177份Markdown及4份DOCX来源哈希，旧示例/空白检查通过。

证据在`.build/workloads-audit-20261123`，保留新验收、分组日志、before/validation、完整wheel核对；原交付证据未覆盖。189份来源文件的身份为`1455a22188ee47fd9a3785f7bcc6d79c2f61c508+workloads-sha256:af021af31756357ce21b418281fe4821b9fb625e35516dddec4ffa3a9e0dadcb`。仅改动6份既有源码/测试、新增1份检查源码，Git索引不变。wheel为`.build/workloads-audit-wheels/UniverseModel-0.1.0-py3-none-any.whl`，SHA256 `15d4398530eef50e2ec990f7ac14f25cd2608049bb3773ea8de309659325b830`；100份打包源码字节一致，隔离解释器导入97份项目模块并执行/回读完整27例，与工作区一致。以上为本地验收，远端CI未执行。

## 2026-11-23 workloads W0–W6规划完成与统一验收

已继续完成[workloads任务规划](../workloads/docs/development_plan.md)中剩余W4、W5及完整W6；研究范围、全部独立接口、来源与后续课题条件见[完成报告](../workloads/docs/completion.md)，实际公式/用法见[映射与真实质量指南](../workloads/docs/mapping_and_quality.md)。W0–W6均有实现和对应证据，不把后续context分割、完整LLM、通用autograd、目标时序或器件成本列为已覆盖。

W4新增公共Attention query-block计划、独立区域/顺序校验，QK/softmax/AV的binary64功能解释、shared/expanded KV与fused/spill中间结果、命名数据域和scratch/backing分离。相同任务/硬件预算的5方案中4个数值校验成功、1个容量预期失败：fused_q1/spill_q1/fused_q2/expanded_q1的外部payload分别2400/3936/1760/3680 B，共同有效工作180 MAC。实际copy和四次score中间传输显式计量；MAC服务要求float64非FMA签名，DMA串行服务与softmax动作分开。MAC/DMA子集下界不能作为完整Attention时间，标量/存储/争用和完整能量仍未知。

W5选择真实UCI Iris的RBF Attention分类，取得原始CSV/说明/API元数据，保留Fisher署名、DOI、CC BY 4.0页面声明及SHA256。150行4项cm测量、3类各50例；原来源第35/38行与历史文章的差异保留未改。每seed按类90/30/30划分，标准化只拟合train，scale0.25/1/4只在validation选择，test只用于报告。Q/K的距离等价式与one-hot V可独立调用，模型状态包含实际来源/划分/统计/支持值。key_decimals为数值简化，仍使用float64存储，没有低bit容量或硬件加速主张。

3个split×4个变体均执行成功且数值通过；基线测试正确数为28/29/27，各30例，所选scale4/1/1。1位/12位支持坐标舍入在这些划分上不改变准确率；−2位负对照各10/30，被任务质量门槛拒绝但保留为成功执行记录。实际NumPy 2.2.6提供batched Attention与独立直接RBF距离两种表达，后者对高精度参考最大绝对误差`6.661338147750939e-16`。保存逐例概率/真值/预测、confusion、accuracy、显式log-loss floor/裁剪、验证选参表及配对基线；精确计数比处理质量阈值。重复split使用同一原始数据，不作独立样本显著性或LLM/服务代表性外推。

W6新增[统一验收工具](../tools/validate_workloads.py)，固定基础10例、映射5例、真实质量12例，共27例；4个预期执行失败与3个成功执行但低质量的负对照全部保留。原始Python/config/数据/来源进入版本身份，bundle字节、完整名单、共同条件、输入/模型身份与指标一致性验证后提交报告。回放不读原始数据、不执行拟合/参考、不要求NumPy；分类指标可从已存概率和真值重建。CI增加标准库与固定NumPy可选环境，本地结果不代表远端CI已运行。

本轮新增24项测试：compiler 3、workloads 7、integration 14；涉及独立高精度参考的3项验证放在integration，保持compiler不得依赖workloads的约束。全回归419项，417通过、2项可选PyTorch跳过；NumPy测试实际通过。分组contracts 6、clustermodel 72、costmodel 7、chipmodel 141、workloads 46、compiler 20、integration 127。规则通过68个实现目录；结构通过13模块、102份模块Python、176份Markdown和4份DOCX来源哈希；旧chipmodel_demo、空白检查均通过。

证据根目录`.build/workloads-completion-20261123`：acceptance/保存完整27例、source.json、三个summary和report.json；references/保存UCI数据、说明、元数据及许可页面原始字节。source.json覆盖188份Python/config/数据/来源文件，身份为`1455a22188ee47fd9a3785f7bcc6d79c2f61c508+workloads-sha256:79a4ebeda1de3dee081990b0892b96c047b5b497defa99a56916ee4189dac66d`。validation.json、各组日志及wheel_audit.json保存工程检查；前包证据保留，既有source中只扩展workloads/reference/attention.py的数值比较接口。

wheel位于`.build/workloads-completion-wheels/UniverseModel-0.1.0-py3-none-any.whl`，SHA256 `c958e5d6fe79181a4d8495fad84b962adf7effa8bffaba8badac5d676bd714a0`。99份打包Python名单/原始字节一致；python -I从解包目录导入96份项目模块，显式提供NumPy 2.2.6依赖，完整27例及保存/原记录回读与工作区一致。示例/配置/来源数据继续从仓库提供，公共契约与默认模型没有新增第三方必需依赖。

## 2026-11-23 workloads W1–W3基础与首包W6验收完成

按[项目使命](../PROJECT_MISSION.md)完成任务梳理与首包开发，顺序见[W0–W6计划](../workloads/docs/development_plan.md)。复用GEMM/MatVec和Linear训练短链，补充Attention任务/独立参考、逻辑KV、有限profiles与本地数据来源；公式、接口、适用域和复现命令见[基础指南](../workloads/docs/foundation_usage.md)。workloads仍只依赖contracts，公共契约只用标准库；没有为了目录完成率创建空模型。

| 包 | 已交付行为 | 证据与边界 |
| --- | --- | --- |
| W1 Attention | MHA/GQA/MQA，Q/K/V维度、显式scale、因果query_start；矩形/有效配对与softmax动作独立计数，唯一KV按Hkv计 | 手算、60组独立float算法、GQA显式复制等价、极值；已投影Q/K/V，不包含完整Transformer/量化/反向 |
| W2 逻辑KV | 不可变快照，按每个batch/head的token轴追加，形状/容量/源内容身份校验；绑定resident KV与query | 多batch/head整段prefill与逐token/分块等价；允许纯函数分支，无物理page/淘汰或并发版本仲裁 |
| W3 数据与profile | 有限完整案例、生成seed/算法版本或本地原始SHA256数据、spec身份、来源/用途/限制；宿主预算先检查 | 篡改/语义/路径/大小反例；当前全为合成验证，未建立真实模型/请求分布代表性 |
| W6 首包工程 | 严格配置、实际输入/准备错误、参考输出或失败、未知目标成本、保存与只读回放；文档/CI/wheel | 完整名单/来源/输入身份和bundle字节检查；运行成功及回读一致性均不等于AI质量或性能结论 |

数值参考用Fraction保留QK/scale与行最大值差，再用独立局部Decimal上下文做exp/归一化/AV，观察值最终转binary64。精度默认80有效位，可选32–256；它不模拟硬件逐指令舍入。概率与输出可下溢为零，AV使用内部高精度概率，故保存的概率舍入为零时输出仍可能保留其大V贡献。极值证据检验数值算法，不表明这些输入有物理可行性。参考预算只限制宿主验证规模，逻辑字节不是真实搬运或峰值分配。

[默认配置](../config/experiments/attention_workloads.json)共10例：prefill MHA/GQA/MQA、短/长decode、cross Attention和本地手算数据7例成功；host_limit_failed、dataset_hash_failed、reference_limit_failed 3例按预期失败。前两种准备失败保留完整配置/来源/诊断、实际data为None；参考规模失败保留实际Q/K/V。手算文件每个query head输出(1,2,3)、(3,4,5)；相同B/Hq/Sq/Skv/D/Dv的MHA/GQA/MQA逻辑KV分别640/320/160 B。不同案例是任务形状验证，不作同预算硬件排名。target_execution_time/target_energy始终None+原因，无“参考与自身比较通过”的质量标记。

新增27项测试：workloads 20、integration 7。全回归395项中393通过、2项可选PyTorch因默认环境未安装跳过；分组contracts 6、clustermodel 72、costmodel 7、chipmodel 141、workloads 39、compiler 17、integration 113。规则通过68个实现目录，结构通过13模块、88份模块Python、173份Markdown和4份DOCX来源哈希；空白及旧chipmodel_demo通过。CI已加入workload_demo保存/回读，本地验收不代表远端CI已运行。

本地证据在`.build/workloads-foundation-20261123`：source.json保存160份Python/config/pyproject原始字节哈希及环境，study/与summary.json保存10例及回放摘要，study_audit.json记录完整结果；各组日志/JSON、validation.json和wheel_audit.json保存工程核对。源码身份为`1455a22188ee47fd9a3785f7bcc6d79c2f61c508+python-config-sha256:15de7235391f3303024a92e3884535ab586aa8bb71fc34d89ff409c646f5e30f`，包含未提交代码，不包含文档与构建产物。

wheel位于`.build/workloads-foundation-wheels/UniverseModel-0.1.0-py3-none-any.whl`，SHA256为`b8becf824376d9c689583d865402150a7916beb6bbdcb396ec2a84174a04eca0`。86份打包Python的完整名单和工作区字节一致；python -I仅从解包目录加载83份实际项目模块，完整10例/旧记录回读与工作区一致，另验证多KV head追加与decode手算。示例/配置仍由仓库提供，不包装为数据下载服务。

下一包为**W4：Attention映射、非矩阵工作与KV布局接入**。需补计划/格式、真实搬运、scratch生命周期与同任务方案比较，再接chipmodel资源；W5按课题补真实模型/数据与任务质量，目标时延、能效、服务代表性和物理可行性仍需各自证据。首包完成不表示整个workloads目标全部实现。

## 2026-11-23 chipmodel完成范围复查与文档补漏

针对“是否还有本阶段应完成的工作”复查实现、CH1–CH10验收计划及分包指南，未发现新的已知必补功能项，但确认六份专业文档仍有过时描述。已修正CH9待办、wheel不可用、完整CIM MatVec待实现及实验记录尚未接入的表述；Unit设计中的早期实现示例明确标为历史范围，并区分基础交付与声明并发/背压时所需的证据。

本次仅修改文档，生产Python、配置和测试源码与上一批146文件的原始字节哈希一致；当前HEAD已经更新，历史实验仍保留运行时提交身份。检查范围为模型规则、结构/链接、空白、源码字节复核及当前Git状态记录，证据在`.build/chipmodel-doc-followup-20261123`。368项回归和104案例仍引用上一批实际运行结果。动态执行、状态化DRAM/缓存时序、CIM器件误差/编程、多CIM协作及物理校准仍按[完成报告](../chipmodel/docs/completion.md)的研究触发条件进入，不能由基础完成状态推定已覆盖。

## 2026-11-23 chipmodel CH10统一验收与基础收尾完成

本轮按[项目使命](../PROJECT_MISSION.md)完成chipmodel基础阶段的横向覆盖审查、数值/输入契约修复、统一验收和文档收尾。CH1–CH10基础均已交付；研究问题、独立/组合入口、证据及后续触发条件见[完成报告](../chipmodel/docs/completion.md)，专业边界继续由各目录UNITS和分包指南维护。候选清单中的全部硬件机制不作为本阶段必填项。

本轮确认并修复：串行链路巨大wire-bit计数的中间浮点溢出；热RC长时间冷却丢失稳态温度；CIM阵列求和/TIA乘加的中间溢出和微小贡献丢失；TensorLayout/CIM直接输入误接收字典键或惰性序列。有理中间量只在输出边界转换，带符号电气输出非零下溢明确失败；合法list/tuple保持冻结、广播及非连续布局语义。新增9项数值/契约测试，含逐包枚举、70组Decimal热参考、50组TIA乘加参考及subnormal反例。极值为数值审计，不表示物理可行参数。

新增[统一验收工具](../tools/validate_chipmodel.py)及4项防退化测试。六组默认夹具的完整案例数与预期失败名单固定受审查；主比较沿用各CLI的正确性/质量门槛，保存源码身份、完整bundle、摘要、命令和host耗时，最后提交验收报告。回读先核对完整原始字节哈希，再从记录重建摘要；不重新执行模型或改写历史版本。CI使用同一入口，文档已修正停留在CH6的当前状态和已实现缓存/成本查询的过时说明。

验证结果：

- 全仓库七组共368项：366通过、2项可选PyTorch测试跳过。分组为contracts 6、clustermodel 72、costmodel 7、chipmodel 141、workloads 19、compiler 17、integration 106（含2跳过）。
- 六组104案例全部保存/回读一致：数字Tile 24、CIM 7、compute 16、memory 21、assembly 16、physical 20；82分析成功、22预期失败全部保留。CIM `adc_2bit`虽分析成功，质量门槛未通过且最大绝对误差62，作为精度消融明确保留；不计作任务质量成功。
- 模型规则通过66个实现目录；结构检查通过13模块、81份模块Python、169份Markdown和4份DOCX源哈希。旧chipmodel示例及空白检查通过。
- wheel中79份Python与工作区原始字节一致；`python -I`仅从解包wheel导入59个项目模块，含所有36个chipmodel实现；六组104案例的输出/指标/身份/失败及保存回读与工作区一致。示例和配置仍从checkout提供，不宣称wheel安装示例CLI。

证据根目录：`.build/chipmodel-closeout-20261123`。`studies/source.json`覆盖146个实际Python/config/pyproject文件；`studies/acceptance.json`、`validation.json`、`audit.json`及`wheel_smoke_audit.json`保存完整明细。源码身份：

`2d6e4c5daa542b98a6d536a9fc4e62e03272d1fe+python-config-sha256:1cead179b93189d94a589fe1dc15c09f5343c911d00868fa92d1503d26a366ec`

wheel SHA256：`751c4c9614a33186a95ffd829cbdf9f0190dc607743c9949a1be122522e41add`。CH7–CH9既有修改与证据保留，Git索引未改变。本地通过不等于远端CI已经运行。

当前边界：标准库功能/分析及显式局部静态策略基础已完整验收；没有完整ISA、动态队列/可见性/一致性、多CIM同步或经实测校准的整芯片PPA。热输入仍为外部总功率，Nangate仍只覆盖两个单元的面积/库标量漏电。CIM有理算术增加宿主运行成本，大规模后端按研究精度另选。后续工作由具体课题所需的任务质量、真实执行、跨模块组合或物理校准证据触发，不把未知成本补成零。

## 2026-11-23 chipmodel CH9物理条件与成本证据基础完成（历史批次）

已按[项目使命](../PROJECT_MISSION.md)和[开发计划](../chipmodel/docs/development_plan.md)完成CH9基础接口、物理账本、真实来源再现及独立验证。研究问题、模型关系、原始来源、限制和复现命令见[物理证据指南](../chipmodel/docs/physical_evidence.md)。CH1–CH9基础已接通，CH10的实验/兼容/文档要求随各包落实；具体器件校准与联合物理可行性仍需研究课题的外部证据。

| 范围 | 已实现与证据 | 保留边界 |
| --- | --- | --- |
| 条件成本查询 | costmodel首次实现结构/PVT/metric/action/unit精确查询；原工件SHA256、版本、提取方法、类别、覆盖和误差未知状态随点返回 | 不插值/外推、不按nm/V自动缩放；没有相应profile就返回None |
| 唯一物理计量 | 静态面积/漏电选择完整覆盖且摘要/后代互斥，单PVT摘要与叶子一致；动态按真实叶子活动，ΣnE与P*T分开 | 模型范围以输入与来源声明为限；缺点、缺活动或缺窗口使完整成本未知，保留已知子集 |
| 几何与热 | 实例/子树绑定layer/Rectangle，逐层包含/不重叠；外部总功率分段驱动固定RC，记录峰值/供能及阈值判断 | 面积/温度只是必要条件；无布线/时序签核、空间热点、多Die热耦合、PDN或PVT反馈 |
| CH8组合接入 | 参数结构哈希、SRAM逐bank读写、MAC、DMA cycle、DRAM burst byte、D2D wire bit按原账本接入；共享RW供给不合并能量读写动作 | 不把通用MAC/SRAM匹配到标准单元数据；DRAM行命令/刷新/写及容量模型缺口保留；不推断真实时长 |
| 研究记录 | 四组20案例：17分析成功、3预期失败；完整来源/输入/未知状态保存回读；热敏感性单数值改动 | 其中12个成功案例的modeled_energy未知；分析成功不等于几何/热条件满足或器件已校准 |

已从OpenROAD-flow-scripts固定提交`82ac25be57125cc724388ef89f01ce65f9ba3dcc`核对Nangate45的Liberty和LEF。原库为typical/TypTyp、1.1 V、25 °C、漏电单位1nW。INV_X1的LEF尺寸0.38×1.4 μm、面积0.532 μm²、库标量漏电14.353185 nW；NAND2_X1为0.57×1.4 μm、0.798 μm²、17.393360 nW。离线工具验证两个原文件SHA256、PVT/单位，以Decimal确认LEF尺寸乘积与Liberty面积相等后生成4个条件点，重新提取与保存表完全一致。

两单元显式无切换、假设1 s窗口的模型面积1.33 μm²、漏电31.746545 nW、能量31.746545 nJ；窗口翻倍为63.49309 nJ。移除窗口或加入没有动作能量profile的10次INV切换，总能量保持未知；INV改成1.0 V也不会自动缩放。分配边界缩到1 μm²时，面积必要条件失败，但程序分析成功。所有数值仅覆盖这两单元的库标量与指定条件，没有MAC/SRAM、芯片功耗或实际输入状态加权漏电主张。

合成代数案例验证动态3 J与背景0.375 W×2 s=0.75 J分开累计；叶子和显式摘要均为3.75 J，缺少一个动态点或窗口时总量未知。该案例仅验证公式/计量，不是器件成本。CH8共享两Tile的64 MAC、16次word读和D2D的500 wire bit均保留；两份原CH8分析与上一包保存结果一致，真实标准单元表无法给出这些结构的成本，补假设窗口后仍未知。

热情景为R=2 K/W、C=5 J/K、Ta=T0=300 K，10 W加热10 s再零功率冷却10 s：峰值312.642411 K、末温304.650883 K、外部供能100 J。R/C/加热功率分别翻倍后，峰值315.738774/307.869387/325.284822 K；R和功率翻倍违反315 K情景阈值。功率、RC和阈值是合成条件，未与标准单元查询结果耦合；供能是外部输入积分，不作为另一份芯片预测能耗相加。

本包新增27项测试（costmodel 7、chipmodel 12、integration 8）。50组随机RC/初态/功率使用80位Decimal指数独立参考，另有半时间常数、分段/冷却、摘要/PVT/几何/时长反例、数值范围、原始工作量守恒和完整记录检查。全仓库回归355项：353通过、2项可选PyTorch因默认环境未安装而跳过；分组contracts 6、clustermodel 72、costmodel 7、chipmodel 132、workloads 19、compiler 17、integration 102（其中2跳过）。规则通过66个实现目录；结构检查通过13模块、81份模块Python、167份Markdown及4份Word来源哈希；diff空白检查和旧chipmodel_demo通过。CI已加入costmodel组与physical_demo保存/回读，本地结果不代表远端CI运行。

本地证据位于 `.build/chipmodel-physical-20261123`。source.json记录143份Python、所有config下JSON及pyproject的逐文件哈希、环境与工作区状态；源码身份为 `2d6e4c5daa542b98a6d536a9fc4e62e03272d1fe+python-config-sha256:fc7f192faca5f9b53b99cb29f99651bfe8724806274492051a20affefd4372cc`。该身份包含未提交源码，不含文档/构建产物；上一包130份源文件与Git暂存区保持不变。validation.json及各组日志保留回归；physical/、physical_summary.json和studies_audit.json保存20案例，assembly_origins.json保存CH8输入/分析/物理活动；references/保存两个原工件及来源元数据，source_table_reextracted.json与source_reproduction.json记录4个点再现、零提取误差和“无独立器件校准”的明确状态。

wheel为 `.build/chipmodel-physical-wheels/UniverseModel-0.1.0-py3-none-any.whl`，SHA256 `01209c9dc466bc4686ba4003d8d30c7a08656d7c171fcc73d0b2340d885c8537`。79份打包Python与工作区逐字节一致；python -I从解包目录加载33个实际依赖模块，完整20案例/回读、4个成本查询和两个CH8适配对照与工作区一致。audit.json、wheel_smoke_audit.json及构建/运行日志保存验证细节。

本包只有来源再现与解析模型的独立正确性证据，尚无独立器件留出校准误差。check_reference禁止把同一工件或假设参考当留出，但不能代替研究者证明方法独立性。真实执行时间、完整AI任务能效、MAC/SRAM动态成本、布局可布通及多Die联合物理可行性继续保持未证实，不把未知填成零。

## 2026-11-23 chipmodel CH8 Tile/Die/Package组合完成（历史批次）

承接CH7，已按[项目使命](../PROJECT_MISSION.md)完成CH8的共享资源与跨Die组合。研究问题、专业接口、公式、边界、独立调用和复现命令见[组合指南](../chipmodel/docs/assembly.md)。下一包为**CH9：物理条件与成本证据**，按明确来源和研究主张补充物理条件；当前不把分析下界作为真实执行时间。

| 范围 | 已实现与证据 | 适用边界 |
| --- | --- | --- |
| Tile/Die/Package | TileBinding引用唯一资源清单；单Die可独立调用，多Tile共享SRAM、MAC与DMA工作统一计量，容量和初始credit不倍增 | 数字Tile工作组合；没有新建容器成本、事件引擎或多CIM执行器 |
| 归属与边界 | 每个memory/route域明确属于Die或外部边界；NoC留在Die内，跨界串行link显式方向/归属；相同时钟域的频率必须一致 | 支持同构NoC多hop或单串行link；混合bridge路径、CDC同步成本和协议状态未实现 |
| 任务与时间 | 完整job依赖、并发scratch预留检查、累计SRAM/MAC服务与全局资源包络；工作不因分到不同Tile而丢失 | 整体界取必要约束最大值，无动态释放、部分可见性、可行调度或任务数值执行主张 |
| 摘要与展开 | 从同一冻结分析投影resource-envelope-lower-bound/v1；叶子/Die/Package容量与贡献一致，完整覆盖且禁止祖先重叠 | 摘要不是新成本provider；不把各scope时间相加为执行时间 |
| 实验与来源 | 五组16案例：12分析成功、4预期失败；位置、单参数资源、顺序消融分开；全名单保存/回读 | 合成参数；失败、假设、输入、版本和未知成本保留，没有器件校准或AI质量收益主张 |

固定两份32 MAC、各8次4 B读，集中在一个Tile或分给两个Tile时整体下界均16 ns：单bank共享读服务仍是限制。只将共享读端口1→2后为8 ns；只将SRAM时钟1 GHz→500 MHz后为32 ns。每job改为64 MAC的独立对照中，固定硬件和工作，分工使下界32→16 ns；再加完整job先后依赖，界回到32 ns。共享容量始终只登记一次。

两个17 B请求共用一个1 Gb/s D2D方向，每请求两packet、每packet 4 B协议、8b/10b编码：总计34 B payload、16 B协议及500 wire bit，必要界500 ns。lane 1→2后为250 ns；固定延迟2→20 ns时仍为500 ns。独立双向请求分别使用各自线路，单向250 bit加2 ns固定延迟得到252 ns，不能把两个方向当同一份500 bit需求。CH7外部DRAM接入反例/正确路径也通过：地址15读取2 B产生32 B burst需求，外存与两个SRAM容量只累计一次，row状态/写成本仍保留条件和未知。

本包新增18项测试（chipmodel 12、integration 6），包括45组随机配置的整数组数/Fraction换钟独立参考、共享MAC的L/II、容量与依赖反例、方向流量守恒、摘要一致性及保存回读。全仓库回归328项：326通过、2项可选PyTorch因默认环境未安装而跳过；分组contracts 6、clustermodel 72、chipmodel 120、workloads 19、compiler 17、integration 94（其中2跳过）。规则通过62个实现目录；结构检查通过13模块、75份模块Python、162份Markdown及4份Word来源哈希；diff空白检查和旧chipmodel_demo通过。CI新增assembly_demo保存/回读，本地结果不代表远端CI已运行。

规模观测固定2048 B共享SRAM，每Tile一个32 MAC、8次4 B读job；各规模是独立基线，工作和MAC资源数量同时增加，不构成同工作加速比。结果如下：

| Tile / job数 | 实际MAC / 读次数 | 必要服务界 | 宿主run_study耗时 | tracemalloc峰值 |
| --- | --- | --- | --- | --- |
| 2 | 64 / 16 | 16 ns | 0.0284 s | 128641 B |
| 8 | 256 / 64 | 64 ns | 0.0561 s | 321023 B |
| 32 | 1024 / 256 | 256 ns | 0.2560 s | 1029763 B |

每规模只测一次；宿主耗时含记录序列化、不含保存/回读，并开启tracemalloc，峰值是Python跟踪分配而非进程RSS。它们仅说明本机模型开销，没有跨平台、统计性能或硬件伸缩性主张。所有规模的配置、记录、手算界和回读一致性均已保存。

本地证据位于 `.build/chipmodel-assembly-20261123`：source.json覆盖130份Python/实验JSON/pyproject的逐文件哈希、环境与工作区状态；源码身份为 `2d6e4c5daa542b98a6d536a9fc4e62e03272d1fe+python-config-sha256:3af216841994c736beb8ae044a88f0c8168461b13ce8dafccbee46b8b54aedc4`，包含未提交源码，不含文档/构建产物。validation.json及分组日志保存回归；assembly/、assembly_summary.json、comparison_metrics.json、scale_2/8/32对应配置和记录、studies_audit.json保留实验与回读结果，capture_studies.py保存生成与观测方法。

wheel位于 `.build/chipmodel-assembly-wheels/UniverseModel-0.1.0-py3-none-any.whl`，SHA256为 `5173c080fe778dd56c76c08f47a625c06cccc71d6ce9b15c3ac73092bc561f74`。73份打包Python与工作区逐字节一致；python -I从解包目录加载25个实际依赖模块，完整16案例和32 Tile规模案例与工作区结果一致，保存/回读通过。audit.json、wheel_smoke_audit.json及构建/运行脚本和日志保留细节。

实际执行时间、数据可见性/一致性、跨域同步、物理面积/能耗及多Die热条件仍未知；CH9将围绕这些具体证据缺口推进，不把未知成本填成零。

## 2026-11-23 chipmodel CH7外存与缓存接入完成（历史批次）

已按[项目使命](../PROJECT_MISSION.md)和[开发计划](../chipmodel/docs/development_plan.md)完成CH7。研究问题、资源/状态边界、公式、独立参考和复现命令见[外存与缓存指南](../chipmodel/docs/memory_access.md)。本包完成DRAM读profile与搬运/Linear接入、cache实际访问轨迹及NAND页缓冲/外部输出；下一包为**CH8：Tile/Die/Package组合**。

| 范围 | 已实现与证据 | 适用边界 |
| --- | --- | --- |
| DRAM | 组织/CK/数据时钟/MT/s/burst绑定、行块混合进制地址、单行拒绝越界或span拆分、未对齐burst覆盖；24种映射排列与逐byte参考 | 显式hit/closed/conflict条件；无自动open-row更新、连续命令队列/刷新或完整时序合法性 |
| Cache | 精确LRU/write-back/write-allocate、逐行hit/miss、有序回填/脏写回、显式flush和快照恢复；60组随机轨迹对照独立时间戳oracle | 所有miss含整行写均读入整行；无数据值、lookup时序、MSHR、一致性或物理替换成本 |
| NAND | 单die单完整页缓冲，阵列页读取与外部data/OOB列输出/命令分项，重复页复用和恢复；手算/范围/未知成本验证 | 串行分析策略；读profile不承担program/erase，未实现写状态、FTL/GC/ECC或多die并行 |
| 组合 | Cache回填→DRAM；DRAM源→搬运/Tile，rank共用每channel唯一burst预算；Linear load显式行条件，输出与scratch/MAC保持不变 | 目标写服务未知，条件界不宣称实际执行；容量/summary与内部服务不重复计费 |
| 研究记录 | 三组21案例，固定资源访问对照与单参数资源消融分开；17分析成功、4预期边界失败，成功项含1个NAND成本未知 | 保存完整profile、访问、初态、策略、来源/假设和失败；分析成功不等于任务质量或物理结论成立 |

合成DRAM夹具为64 B行、16 B burst、1 GHz CK、4 GB/s/channel；地址15读取2 B需要32 B传输，hit/closed/conflict为12/15/20 ns。rank 1→2使容量512→1024 B，接口仍4 GB/s；channel 1→2增加总峰值，但仅使用一个channel的单行请求时间仍为12 ns。跨行地址63长度3 B拆成1+2 B，closed条件界11 ns；单行入口拒绝同一请求。

32 B、两set单路cache的0/32/0/32四次1 B访问产生4 miss、64 B回填与16 ns读子集界；同预算改成0/16/0/16后为2 miss、32 B回填与8 ns。增加一路也得到32 B回填，但容量增到64 B，属于额外资源消融。写0/32/0产生48 B回填、32 B逐出写回及16 B尚未写回；显式flush后写回总量48 B，DRAM写时间仍未知。

NAND夹具页data/OOB为32/4 B，tR=10 μs、输出1 MB/s、命令2 μs/request；同页两次总输出7 B为1次阵列读、21 μs串行时间。只翻倍输出速率后为17.5 μs，第二次访问换页则为31 μs。以上均为合成条件和指定策略的分析值，无器件性能校准主张。

相同Linear/Tile输入与计划替换外存后，数值输出、scratch服务和MAC分析一致；154 B逻辑外存读产生1264 B完整burst需求，唯一DRAM读总线贡献为316 ns。原profile与DRAM配置的整体下界均为348 ns，说明更细的外存粒度计量不必然改变最终瓶颈。目标写服务、DRAM调度、实际任务执行时间及面积/能耗仍未知。

新增24项测试（chipmodel 18、integration 6）。全仓库回归310项：308通过、2项可选PyTorch因当前默认环境未安装而跳过；分组contracts 6、clustermodel 72、chipmodel 108、workloads 19、compiler 17、integration 88（其中2跳过）。模型规则通过62个实现目录；结构检查通过13模块、71份模块Python、161份Markdown和4份Word来源哈希；HEAD diff空白检查和旧chipmodel_demo通过。CI新增memory_demo保存/回读，本地结果不代表远端CI已执行。

本地证据位于 `.build/chipmodel-memory-20261123`。source.json记录122份Python/实验JSON/pyproject的逐文件哈希、环境和工作区状态，源码身份为 `2d6e4c5daa542b98a6d536a9fc4e62e03272d1fe+python-config-sha256:537aa7239dfaa03102536c8e0ceb683c659d65d95113b60d89b2ba2c12d8c6fc`，包括本轮未提交源码、不包括文档/构建产物。validation.json与各组日志保存回归证据；memory/、memory_summary.json、linear_baseline/、linear_dram/及studies_audit.json保存完整研究和回读一致性。

wheel为 `.build/chipmodel-memory-wheels/UniverseModel-0.1.0-py3-none-any.whl`，SHA256为 `ecd8f51f0cc4a79d155b6c007fed9e8776924a84251e1ae8459b13253bac8952`。69份打包Python与工作区逐字节一致；python -I从解包目录加载34个实际依赖模块，完整21案例及Linear对照与工作区结果一致，保存/回读通过。audit.json、wheel_smoke_audit.json和构建/运行日志保留细节。

## 2026-11-23 chipmodel CH6计算能力与瓶颈解释完成（历史批次）

已按[项目使命](../PROJECT_MISSION.md)和[开发计划](../chipmodel/docs/development_plan.md)完成CH6。研究问题、独立接口、公式、适用域、反例与复现命令见[计算能力指南](../chipmodel/docs/compute_capabilities.md)。本包扩展CPU/GPU/NPU的能力解释，并将NPU格式检查接入现有数字Tile；下一包为**CH7外存与缓存接入**。

| 范围 | 已实现能力与证据 | 保留边界 |
| --- | --- | --- |
| CPU | 显式同类μop身份、每阶段速率、精确并列瓶颈、有限工作发起跨度；60组逐cycle槽枚举与大整数边界 | 跨度不含阶段延迟/依赖；程序执行时间未知，不宣称IPC或ISA执行 |
| GPU | 各项SM驻留容量、单block启动违反项、限额缺失状态、尾warp槽与有效线程比例；80组逐block消耗枚举 | 固定padded-warp-block-quantum/v1规则；True只表示本模型静态可容纳，occupancy不等于吞吐 |
| NPU | 操作/操作数/累加/输出签名匹配，区分FP16/BF16及融合/非融合；逻辑/实际/额外MAC、尾批和L/II服务 | 只描述已声明服务能力，不执行数值舍入/溢出验证；依赖反馈、实际执行与能耗未知 |
| Tile组合 | 显式能力与工作请求双向匹配；Linear按任务语义生成签名；mac_analysis复用已计费MAC服务 | 旧两侧未声明的调用仍可使用原账本，但不声称已验证格式能力；无新增隐式转换服务 |
| 研究记录 | 四组16案例，基线/资源/工作消融/边界分开；单数值改动与固定另一侧自动检查；完整名单保存/回读 | CPU/GPU/NPU各自解释专业指标，不作跨架构统一性能排名；分析成功不等于任务质量或设备可行 |

CPU夹具为25μop：稳态2 μop/cycle、retire限制，有限跨度下界12 ns；执行端口8→16无收益，提交宽度2→8后迁移到issue限制、3 μop/cycle与8 ns跨度下界。GPU的256线程/64 register/thread/16 KiB shared/block同时受register/shared约束为4 blocks；只翻倍其中一项仍为4 blocks。33/64线程案例具有相同0.5 occupancy，有效线程槽比例分别33/64和1。

NPU夹具为逻辑7、实际9 MAC，P=4/L=3/II=2：12发起槽、3尾空槽、7 cycles孤立服务；P增至8后是16槽、7尾空槽、5 cycles。增加padding至实际12 MAC填满槽但有效工作比例下降，不能据填槽率宣称收益。数字Tile的同输入140 MAC、314 B流量对照中，MAC lanes翻倍使孤立服务35→18 ns，整体资源下界仍348 ns；开启格式解释前后输出、地址/bank账本、资源贡献和下界一致，无重复计费。正确选择binary64 profile的MatVec继续通过独立数值参考。

本包新增20项测试（chipmodel 12、integration 8）。全仓库回归286项：284通过、2项可选PyTorch因当前默认环境未安装而跳过；分组contracts 6、clustermodel 72、chipmodel 90、workloads 19、compiler 17、integration 82（其中2跳过）。模型规则通过62个实现目录；结构检查通过13模块、68份模块Python、160份Markdown及4份Word来源哈希；diff空白检查和旧chipmodel_demo通过。CI已加入compute_demo保存/回读；本地结果不等同远端CI执行。

本地证据目录为 `.build/chipmodel-compute-20261123`。`source.json`保存115份Python/实验JSON/pyproject的逐文件哈希与环境；源码身份为 `5ede4cf19dc57271c020ff15a14df74f7b677245+python-config-sha256:deb59761e2691e894092ab4c3fa4d7de581cd7c6bdbdd7c8defc161c36ced02e`，包含未提交工作区源码，不包含文档/构建产物。`validation.json`与分组日志保存测试；`compute/`、`digital_tile/`、`cim/`及对应summary和`studies_audit.json`保存三组实验及回读一致性。

计算能力16案例为13次分析成功、3次不支持操作/格式的失败；成功结果另含1个GPU已知启动不可行和1个限额未知。数字Tile六组24次为18成功/6容量失败；复跑CIM七候选为5次执行成功（4次数值验证通过/1次质量失败）、2次保持失败。所有案例均保存，不过滤失败或未知状态。

wheel位于 `.build/chipmodel-compute-wheels/UniverseModel-0.1.0-py3-none-any.whl`，SHA256为 `7b68df5ef04da3128d365b13abfd72586dbb10da2d3e1062ea059bff68a80565`。66份打包Python源码与工作区逐字节一致；`python -I`从解包目录导入39份实际依赖模块，验证完整计算能力对照/回读、数字Tile同输入供数反例以及CIM汇总一致性。`audit.json`、`wheel_build.log`、`wheel_smoke.py`和`wheel_smoke.log`保留验证细节。

本包没有程序/kernel执行、厂商GPU分配特例、混合CPU端口调度、脉动/tensor执行或器件校准主张。能力档位需真实来源后才可用于具体硬件结论，执行时间/物理成本缺口继续显式保留。CH7按实际访问问题接续DRAM组织/地址/profile、NAND服务与传输边界及缓存行为。

## 2026-11-23 chipmodel CH5完整CIM局部台架完成（历史批次）

已按[项目使命](../PROJECT_MISSION.md)与[开发计划](../chipmodel/docs/development_plan.md)完成CH5。研究问题、生产接口、参数关系、策略边界、对照结果和复现命令见[CIM台架指南](../chipmodel/docs/cim_bench.md)。本包支持固定输入/权重下的差分位置、ADC共享、量化精度与保持可行性研究；下一包为**CH6计算能力与瓶颈解释**。

| 层次 | 已实现能力 | 证据与边界 |
| --- | --- | --- |
| 独立数值链 | 电导切片/差分编码→DAC→完整矩形阵列→TIA→ADC→码值重建/移位累加；保留非零Gmin、尾slice、最终error/saturate/wrap | 独立整数参考、80组随机矩阵×两种求差位置、不同矩形/单列/尾批、手算电流/电压/ADC；无符号输入，未引入噪声/线阻/漂移 |
| 局部组合 | 唯一资源owner和模型选择、逐资源动作账本、独立时钟/L/II、MUX、外部保持/内部ADC在途/码值/累加容量 | Fraction日历保留跨phase发起约束；逐样本TIA捕获→ADC接收年龄；精确期限边界与L<II反例；每行需持续驱动DAC |
| 性能口径 | 分开输出资源服务下界、串行phase策略依赖界与该策略分析时间 | ADC增多而数字瓶颈不变、ADC降频后的瓶颈迁移；无事件执行、跨phase流水或器件时序主张 |
| 研究记录 | 同输入完整七候选、独立功能验证、资源/精度消融、失败记录、源码/输入/电导初态/数值和时序轨迹 | 保存/回读一致；拒绝混来源/预算/输入、重复或遗漏候选；回读不执行模型，运行成功与数值质量分开 |

默认夹具为 `x=(3,5)`、`W=((1,-2,5),(-3,4,-1))`，独立精确结果 `(-12,14,10)`。基线为6 MAC、4个2×3阵列、48个物理权重bit、6个phase、12次DAC更新、12次阵列读与72次cell动作。ADC前模拟求差为18次转换/36次数字操作，资源下界36 ns，串行策略时间108 ns；相同预算的ADC后数字求差保持相同输出，转换/数字操作为36/72，资源下界72 ns、策略时间168 ns。

ADC lanes从2增至4时，数字资源下界仍36 ns，策略时间降至102 ns；ADC时钟降至250 MHz时，ADC界44 ns成为限制，策略时间198 ns。ADC降至2 bit时程序成功但输出为 `(50,58,54)`，最大误差62且没有ADC越量程，明确判为质量失败；保持槽6→2和有效期20→1 ns分别触发容量/年龄失败。七候选共5次执行成功（4次数值验证通过、1次质量失败）和2次执行失败，均保留记录。上述时间仅适用于声明的分析策略与服务假设。

新增28项测试：chipmodel 17、workloads独立整数参考3、集成8。全仓库回归266项：264通过、2项可选PyTorch因当前环境未安装而跳过；分组contracts 6、clustermodel 72、chipmodel 78、workloads 19、compiler 17、integration 74（其中2跳过）。模型规则通过62个实现目录；结构检查通过13模块、67份模块Python、159份Markdown及4份Word来源哈希；diff空白检查和旧chipmodel_demo通过。CI已接入CIM保存/回读；本地验证不等同远端CI结果。

本地证据位于 `.build/chipmodel-cim-20261123`：`source.json`覆盖110份Python/实验JSON/pyproject并保存环境和逐文件哈希；`validation.json`与各组日志记录回归；`study/`、`study_summary.json`和`study_audit.json`保留完整实验；`audit.json`、`wheel_build.log`、`wheel_smoke.py`及`wheel_smoke.log`记录打包验证。源码身份为 `5ede4cf19dc57271c020ff15a14df74f7b677245+python-config-sha256:f33f483bbb85dbc1fbaf8bac79f53763616b6237cda0753fbc71526e97869535`；该快照包含未提交工作区源码，不含文档与构建产物。

wheel位于 `.build/chipmodel-cim-wheels/UniverseModel-0.1.0-py3-none-any.whl`，SHA256为 `206cf38a3cd4e9bffb365f8542d681ecd7dc25f6ee67df7799e05d0efcbabf37`。65份打包Python源码逐字节匹配工作区；`python -I`从解包目录导入24份实际依赖模块，独立数值/资源分析、七候选与保存/回读通过，汇总与工作区实验完全一致。

读取能耗、权重编程时间/能耗保持 `None + reason`；权重与输入已驻留，外部搬运、DAC负载、器件误差与物理可行性仍需按研究证据补充。数值中间累加使用Python整数，不代表已实现无限位宽硬件。本包没有实现既有71-cycle流水提案，也不宣称AI任务质量收益或实机加速。CH6接续CPU/GPU/NPU的能力与限制解释，复用本包和数字Tile证据；CH7–CH9仍按课题需要开发。

## 2026-11-23 chipmodel CH1–CH4首包完成（历史批次）

已按[项目使命](../PROJECT_MISSION.md)与[任务计划](../chipmodel/docs/development_plan.md)执行首包，实际接口、参数关系、研究比较和复现命令见[基础指南](../chipmodel/docs/foundation_usage.md)。本包完成基础契约、SRAM访问与容量绑定、显式搬运账本、数字Tile/Linear适配；不表示chipmodel全部后续研究任务已完成。

| 任务 | 实现与证据 | 当前边界 |
| --- | --- | --- |
| CH1 契约与下界 | 修复G1/G2；需求/credit用Fraction中间量，2^53+1−2^53保留1 s；直接/JSON一致；序列、身份、成员、图、依赖、单位与模型选择检查 | 输出binary64近似，溢出/正值下溢报错；无区间算术或调度器 |
| CH2 SRAM/预留 | 显式SramAccess，逻辑B与word服务分开，逐bank读写计量；独立R/W或共享RW、L/II、显式byte-enable；BufferReservation检查共同backing区间 | 无存储内容/动态队列/槽生命周期/预留别名，混合专用与共享端口未支持 |
| CH3 搬运账本 | 源读、串行DMA通道、显式有向路径、目标写；唯一owner、工作单位、协议计数与共享资源贡献；NoC导出packet/flit/service bytes | 同构同钟NoC、单D2D或显式直达；异构bridge、可见性、背压未实现；外存可为未知服务边界 |
| CH4 数字Tile | 独立DigitalTile/TileWork；合并本地/DMA访问并校验预留；evaluation从Linear计划生成显式地址；INT8/INT64与小型binary64/MatVec参考，固定预算和单因素敏感性 | 本地策略scalar-ab-register-c/v1；计算/搬运理想重叠仅用于下界，训练Tile地址适配明确拒绝，能耗未知 |
| CH10 工程落实 | 严格配置、实际输入/计划/地址/来源/假设记录、失败样本、六组完整名单保存/回读；UNITS/参数清单/入口及CI同步 | 本地验证不等同远端CI或物理性能证据 |

5×7×4、140 MAC的同输入实验：2×2×3驻留/重载部分和方案均通过整数参考，预留均44 B，外部流量分别314/954 B，条件下界348/588 ns，当前均受DMA约束。1×2×3方案预留25 B、370 B、460 ns；完整tile需223 B而预算64 B，作为失败记录保留。MAC lanes加倍不能突破DMA界；降低MAC/SRAM时钟或固定容量改成单bank显示瓶颈迁移。六组共24次运行，18成功、6容量失败，保存与回读结果一致。

新增25项测试（17芯片模型、8数字Tile集成）。全仓库回归238项：236通过，2项可选PyTorch因当前默认环境未安装而跳过；分组contracts 6、clustermodel 72、chipmodel 61、workloads 16、compiler 17、integration 66（其中2跳过）。独立证据包括60组有理包络参考、逐byte枚举word/bank、共享端口、17 B双hop和D2D手算、路径/owner/容量反例、本地标量访问、敏感性与完整候选回读。模型规则通过62个目录；结构检查通过13模块、63份模块Python、158份Markdown及4份Word来源哈希；diff空白检查通过，旧chipmodel_demo仍通过。

本地证据保存在 `.build/chipmodel-foundation-20261123`：source.json（101份Python/实验JSON/pyproject来源）、validation.json及分组日志、comparison/的完整记录、comparison_summary.json、audit.json与wheel_smoke.log。源码身份为 `5ede4cf19dc57271c020ff15a14df74f7b677245+python-config-sha256:e9d94fefd3716412e0f0aaee822062fc687ee25e7ca8e7b82d097f63c1c1debf`。wheel构建成功，61份打包Python源码与工作区一致；`python -I`隔离导入通过G1、数字Tile三成功/一容量失败与bank计量验证。

下一包为**CH5 CIM完整局部台架**：串接数字码→DAC→电导阵列→TIA→ADC→累加，统一动作与资源身份，验证编码、ADC共享及保持约束。CH6–CH9继续按研究问题和证据需要进入；本包不宣称事件完成时间、AI任务质量提升、器件性能或物理能耗结论。

## 2026-11-23 chipmodel 开发任务梳理（执行前历史记录）

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
| 计算与 CIM | CPU阶段瓶颈/有限跨度、GPU驻留/启动/尾warp、NPU显式格式/尾批与Tile供数解释；完整CIM数值/资源/保持台架；无ISA或动态调度 | [compute参数](../chipmodel/compute/UNITS.md)、[CH6证据](../chipmodel/docs/compute_capabilities.md) |
| 存储与搬运 | SRAM/buffer/cache 几何、DRAM 组织/接口、隔离行读、NAND 几何/串行时延、DMA 服务与 TMA 布局；无缓存命中、刷新、FTL 或队列状态 | [memory](../chipmodel/memory/UNITS.md)、[control](../chipmodel/control/UNITS.md) |
| 互连与物理条件 | 无争用 NoC 路径、D2D 分包/编码、同层矩形校验、一阶热 RC；不覆盖协议状态机、多节点热或电路校准 | [interconnect](../chipmodel/interconnect/UNITS.md)、[packaging](../chipmodel/packaging/UNITS.md) |
| 系统组合与创建 | 身份/归属/静态端口兼容检查、摘要/细节计量选择、操作 DAG 和资源供给包络下界、显式小型注册表 | [composition](../chipmodel/composition/UNITS.md)、[registry](../chipmodel/registry/UNITS.md) |
| 仓库开发规则与参数文档 | 根目录/模块AGENTS.md；chipmodel全目录与其他实际实现目录/祖先，共62个实现目录检查范围；字段/接口表从代码生成 | [规则](development/model_rules.md)、[总入口](../chipmodel/UNITS.md)、[检查工具](../tools/check_model_rules.py) |
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

当前clustermodel及chipmodel CH1–CH10基础均已完成，chipmodel已通过[统一验收](../chipmodel/docs/completion.md)。后续按[计划](../chipmodel/docs/development_plan.md)和具体研究主张补充执行、器件校准与联合物理证据；动态队列/可见性和物理有效性仍不能由分析下界或来源再现替代。

既有线性路径的后续任务保留：Linear 前向/反向/更新及短算子链、梯度与状态版本、固定版本 PyTorch 功能对照、Timeloop/Accelergy及ZigZag/SCALE-Sim共同可比案例、带来源条件成本和误差报告。按实际复现决定适配，接口规则见[工程框架](../ENGINEERING_FRAMEWORK.md)。

CIM array + DAC/ADC + 缓冲的完整局部台架已在CH5完成，数值/动作/资源与保持证据见本页历史批次及[CIM指南](../chipmodel/docs/cim_bench.md)。GEMM ROI、单层训练/推理资源账本和71-cycle流水提案仍未由该台架实现；后续按[局部仿真规划](architecture/composable_simulation.md)与 [B/C 门槛](architecture/validation.md)选择所需证据。

BenchSpec 等新对象与计划生产者字段目前属于提案，现行公共契约的修订清单见上述规划第 10 节。代码级功能/事件模型先行，周期、RTL 与电路校准按[精度选择](architecture/instruction_and_fidelity.md)的触发条件加入。

每次能力发生变化，更新对应行、核对日期、代码基线和证据入口；部分可用时写明支持范围及尚未通过的验证。新增模块或改变依赖还要更新 [modules.json](architecture/modules.json)，该清单只记录结构信息。其他文档引用本页，不另行维护完成状态；参考资料的“首版建议”不等于已实现功能。其他变更的维护位置见[文档维护规则](README.md)。

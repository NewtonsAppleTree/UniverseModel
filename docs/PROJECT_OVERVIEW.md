# UniverseModel 项目总览

UniverseModel 把一项芯片架构研究组织为：定义要完成的工作和硬件方案，生成合法执行计划，在有限资源上执行，检查结果并解释性能与成本。本文是项目的总阅读入口，集中说明目录分工、软件与物理层级、输入输出、数据格式和任务调用路线。

**当前状态是架构规范与工程骨架。** 已完成目录、设计文档、结构示例和检查工具；下文的模块输入输出与调用路线是后续实现约定。13 个业务模块尚未形成可运行的编译、仿真、实验或图形界面，chipmodel 当前不包含 RTL。实际可用工具见第 9 节。

快速定位：第 1 节看整体；第 2、3 节查职责和数据；第 4、5 节查实验与任务路线；第 6、7 节看参数修改和解耦；第 8、9 节查目录与完成状态。

## 1 先理解整个项目怎样工作

用户提供两类内容：一类是“要算什么”，例如矩阵运算、神经网络图或请求序列；另一类是“用什么算”，例如数字引擎、CIM 阵列、存储和互连。evaluation 组织一次实验，把两类内容交给各模块处理。

```text
用户的研究问题与配置草稿
        ↓
evaluation 组织实验
        ├─ configuration 解释并冻结参数
        ├─ workloads 提供任务语义、输入和参考
        └─ 硬件模型提供资源、连接、能力和行为
        ↓
compiler 决定任务和数据放在哪里、怎样切分与搬运
        ↓
runtime 派发请求 ↔ 硬件组件维护资源与完成效果
        └──────── simulator 推进事件与目标时间
        ↓
evaluation 比对参考、计算指标、比较方案
        ↓
artifacts 保存证据，ui 经 evaluation 展示和解释
```

图中箭头表示信息推进；执行阶段是反复交互的循环。artifacts 从准备阶段就开始保存配置和来源，最后提交完成清单。contracts 为所有阶段定义共同的数据语义，costmodel 为硬件行为、编译选择和评估提供有条件的成本依据。

先记住六个问题：workloads 说明“算什么”；硬件模型说明“有什么资源”；compiler 说明“怎样安排”；runtime 说明“现在提交什么”；simulator 说明“何时发生”；evaluation 说明“结果是否正确、方案是否更好”。

### 软件职责层级

这些层是阅读分组，用于定位责任。依赖关系并不是只能从上一层调用下一层；允许的代码依赖以 architecture/modules.json 为准。

| 职责层 | 单元 | 在项目中的作用 |
| --- | --- | --- |
| 使用与实验组织 | ui、evaluation | 接收研究意图，组织实验与比较，展示结果 |
| 工作描述与执行策略 | workloads、compiler、runtime | 定义工作，生成计划，按运行状态派发 |
| 目标硬件 | chipmodel、systemmodel、clustermodel | 表达物理资源、连接和局部行为 |
| 时间与观测 | simulator | 推进事件、统一时间、收集计数与诊断 |
| 公共基础与证据 | contracts、configuration、costmodel、artifacts | 统一语义、解释参数、提供成本、保存来源 |

### 目标硬件的物理层级

| 模型单元 | 负责的物理范围 | 组合关系 |
| --- | --- | --- |
| chipmodel | Engine/Array、Core/Tile、Die、Package | 计算、存储、NoC、D2D 和封装内组合 |
| systemmodel | Board/Card、Node | 组合芯片或封装，加入主机内存、节点 I/O、DMA 和 NIC |
| clustermodel | Cluster、节点间 Fabric | 组合节点，加入跨节点链路、交换机和路由 |

包含方向为 Cluster → Node → Board/Card → Package → Die → Core/Tile → Engine/Array，可按研究范围省略可选层级。CPU、GPU、NPU、CIM 是计算类型；3D、双裸片是组织方式；HBF 是 High Bandwidth Flash 存储能力。它们不处在同一个分类维度。

单芯片研究可只装配 chipmodel；研究主机搬运或同节点多卡时加入 systemmodel；研究多机通信时再加入 clustermodel。多核留在 chipmodel，不因为核多就属于集群。3D CIM 需要分别说明阵列层数、裸片堆叠和逻辑层位置。

## 2 十三个主模块的输入处理与输出

下面的对象名是公共语义名称，具体字段和文件形式见第 3 节。模块交换的是对象和引用；无需把每个模块实现成独立服务，也无需每次交互都先写文件。

### 公共语义和参数依据

| 单元 | 接收什么 | 完成什么处理 | 交给谁及交付物 |
| --- | --- | --- | --- |
| contracts | 开发时定义的字段、单位、能力与协议规则 | 定义公共类型、身份、版本、错误及状态含义 | 全部模块使用的契约；自身不运行实验 |
| configuration | 参数定义、config 文件、模板引用、实验覆盖 | 展开实例，统一单位，计算派生值，校验并冻结 | evaluation 及参与模块使用 ResolvedConfig；ui 使用字段元数据、差异和错误定位 |
| costmodel | 动作与结构、精度、电压频率等条件、校准来源 | 查询公式、表格或外部模型，给出成本及适用范围 | compiler、硬件模型、evaluation 使用 CostProfile / Estimate |

configuration 回答参数最终是多少、为什么；costmodel 回答这些条件下某项动作或结构代价是多少。成本可以是服务时间、能量、面积等，不只指采购价格。资源争用形成的实际等待由硬件行为和事件执行决定。

### 三个硬件范围

| 单元 | 接收什么 | 完成什么处理 | 交给谁及交付物 |
| --- | --- | --- | --- |
| chipmodel | 芯片与封装配置、成本接口；运行中的计算和搬运 Request | 组合引擎、阵列、存储和互连，维护本地队列、占用与数据效果 | 装配阶段输出 HardwareSpec 和组件接口；执行阶段输出接收状态、完成事件和计数 |
| systemmodel | 节点配置、chipmodel 实例、节点路径请求 | 组合板卡和节点，处理主机内存、地址域、DMA、PCIe/CXL 与 NIC 资源 | 节点级 HardwareSpec、路径能力、系统请求结果和计数 |
| clustermodel | 集群配置、systemmodel 节点、通信请求 | 连接节点端口，处理链路、交换、路由和共享网络资源 | 集群级 HardwareSpec、网络能力、通信事件和链路计数 |

硬件模块有两个不同阶段：装配时回答“资源有哪些、支持什么”，运行时回答“请求是否能接受、何时产生何种效果”。HardwareSpec 是只读描述，组件实例持有动态状态。NIC 由 systemmodel 拥有，clustermodel 引用它的端口，不再复制一张 NIC。

### 工作定义与执行策略

| 单元 | 接收什么 | 完成什么处理 | 交给谁及交付物 |
| --- | --- | --- | --- |
| workloads | 算子或图描述、shape、精度、数据集或生成规则 | 定义完整工作和输入，提供独立正确性参考 | compiler 使用 WorkloadSpec；执行使用输入引用；evaluation 使用参考与质量规则 |
| compiler | WorkloadSpec、HardwareSpec、成本接口、映射策略 | 划分、切块、放置、内存规划、目标操作转换和静态调度 | runtime 使用 PlacementPlan、ExecutionPlan；必要时附 CommunicationPlan |
| runtime | 计划、动态策略、已发生的完成或背压通知 | 管理软件队列与 stream，派发就绪操作，推进集合通信 | 硬件组件接收 Request；simulator 接收所需回调；评估使用策略记录 |

compiler 决定静态安排及约束，runtime 根据当前状态决定实际提交。compiler 可以估计时间，却不能取消真实资源竞争；runtime 只能使用已发生的信息。AllReduce 等集合通信算法主要在 runtime 展开，clustermodel 提供它使用的网络资源。

### 时间推进与实验结果

| 单元 | 接收什么 | 完成什么处理 | 交给谁及交付物 |
| --- | --- | --- | --- |
| simulator | evaluation 注入的组件和 runtime、计划、初态、时间与观测设置 | 推进事件和目标时间，调用组件与策略，汇总计数和终止诊断 | evaluation 使用 SimulationResult、输出 DataRef 和计数；artifacts 保存可选 TraceEvent |
| evaluation | 研究目标、负载、配置或候选集合、质量门槛与比较协议 | 装配实验，调用编译和执行，验证数值，校准、扫描和比较 | 用户或 ui 获取验证报告、指标、方案差异及适用结论；artifacts 保存证据 |
| artifacts | 各模块的版本化对象、文件引用和运行状态 | 序列化、校验、写入、索引和维护来源链 | evaluation 获取 ArtifactManifest 与可定位引用，再向 ui 提供结果；数据进入 data/runs |
| ui | configuration 的字段定义；evaluation 的状态、结果和可视数据 | 编辑草稿，展示拓扑、映射、时间线与比较 | configuration 接收参数修改；evaluation 接收实验意图；用户看到解释后的结果 |

evaluation 负责组织，不接管硬件内部状态。artifacts 负责保存，不判断数值是否正确。ui 通过 configuration 和 evaluation 使用能力，不直接导入每一种硬件模型或访问其私有队列。

## 3 交换的数据和格式

### 对象格式与文件格式分开

对象格式规定字段含义、单位、版本和合法状态；文件格式规定如何保存这些对象。JSON 文件能被解析，只说明语法可读，仍需校验字段、引用、容量与能力。下面明确区分当前文件和后续格式建议，尚未实现的 schema 不视为现有 API。

| 数据类别 | 跨模块的表达 | 文件与保存约定 |
| --- | --- | --- |
| 用户配置 | 草稿、模板、覆盖项和参数定义 | config 下的 JSON/YAML 是后续输入形式；当前只有目录规划 |
| 已解析参数与规格 | 不可变的版本化对象 | UTF-8 JSON，统一单位并规范化后计算哈希 |
| 编译中间表示 | compiler 私有 IR 及 pass 结果 | 内部格式随实现选择；对外导出公共计划 |
| 执行计划 | 放置、缓冲、操作、依赖和通信对象 | plans 下的版本化 JSON 是首版建议 |
| 请求与事件 | 内存中的类型对象，经接口或事件队列传递 | 需要留轨迹时建议 JSONL，一行一个记录；无需逐事件同步落盘 |
| 张量与大数据 | DataRef 加独立内容引用 | 首个 Python 闭环可用 NPY/NPZ；大规模格式以后按需求选择并记录编码 |
| 指标与验证 | 值、单位、范围、状态和来源对象 | 权威结果用 JSON；CSV 可作比较导出，不能丢掉单位和口径 |
| 来源与校准材料 | 版本、获取位置、条件和内容哈希 | manifest 加原始材料；表格可为 CSV/JSON，外部格式通过适配器读取 |

已存在的机器可读文件包括 architecture/modules.json、tools/documents.json，以及 ../example/specs/heterogeneous_topology.json。最后一个明确标为不可执行结构示例，不是可运行配置。

### 公共对象各自携带什么

| 信息对象 | 关键内容 | 生成方与使用方 |
| --- | --- | --- |
| ResolvedConfig | 完整有效值、单位、实例、覆盖来源、派生版本和哈希 | configuration → 装配与参与模块 |
| HardwareSpec | 资源与端口、物理包含、连接、能力、地址域、时钟和约束 | 硬件装配 → compiler、runtime、evaluation |
| WorkloadSpec | 操作图、shape、布局、数值规则、输入与参考要求 | workloads → compiler、evaluation |
| CostProfile / Estimate | 动作条件、服务需求、能量或面积、单位、覆盖与适用域 | costmodel → compiler、硬件、evaluation |
| PlacementPlan | 分片、任务、逻辑设备、rank 和物理资源对应关系 | compiler → runtime、evaluation |
| ExecutionPlan | 操作与搬运、缓冲分配、依赖、目标和负载哈希 | compiler → runtime、simulator |
| CommunicationPlan | 参与者、分片、规约语义、顺序和算法约束 | compiler 或 runtime → runtime |
| DataRef | 数据及分配身份、版本、所在存储、区域、shape、dtype、layout、内容引用 | 各阶段引用数据；目标有效性由组件协议维护 |
| Request / Event | 运行与请求身份、操作、端口、引用、依赖、状态、目标时刻与效果 | runtime、硬件组件、simulator 交互 |
| SimulationResult | 执行状态、目标时间、计数器、输出引用、覆盖和诊断 | simulator → evaluation |
| 验证和指标报告 | 参考差异、容差、质量、指标值、单位、统计窗口和公式版本 | evaluation → artifacts；经 evaluation 提供给 ui |
| ArtifactManifest | run 身份、输入和代码版本、文件位置与哈希、运行状态 | artifacts → evaluation 及复现工具 |

DataRef 有两种位置含义，必须同时分清。目标位置例如 `sram_0`，表示被模拟芯片的数据在哪里；内容位置例如 `outputs/y.npy`，表示宿主文件怎样保存数值。后者存在，不代表前者已经完成搬运或对目标计算单元可见。

例如，输入 x 的逻辑身份可以保持不变，但 host memory 中的副本和 SRAM 中的副本有不同存储引用与有效状态。runtime 提交 copy 请求，组件完成源读取和目标写入；目标可见后，依赖 x 的计算才能开始。accepted、source_consumed、destination_visible 分别表达接收、本请求已消费源数据和目标可读；源缓冲要等全部使用者释放后才能复用。

跨模块传递前检查版本、单位和引用；使用能力前检查 shape、精度和布局；执行前检查容量与依赖。unsupported、infeasible、unknown 成本和执行失败分别报告，不能统一解释为数值零或成功。

## 4 用一次矩阵向量实验串起各模块

研究任务为计算 y = W × x，W 的形状为 M × K，x 为 K，y 为 M。第一版目标由一个数字计算引擎、SRAM 和显式搬运组成。输入已处于目标内存还是需要主机装载，应在实验中声明；需要模拟主机路径时加入 systemmodel。

| 步骤 | 调用方与参与单元 | 输入及处理 | 产生的输出 |
| --- | --- | --- | --- |
| 1 定义问题 | 用户 → evaluation | 指定 M、K、数值规则、硬件方案、指标范围 | 实验意图与配置引用 |
| 2 解释参数 | evaluation → configuration | 展开模板和覆盖，统一单位，校验已知约束 | 冻结的 ResolvedConfig |
| 3 准备两侧描述 | evaluation → workloads、chipmodel、costmodel | 生成负载与参考，装配硬件，绑定成本依据并检查能力 | WorkloadSpec、HardwareSpec、组件实例和成本接口 |
| 4 生成计划 | evaluation → compiler | 检查容量，选择切块与放置，加入搬运和依赖 | PlacementPlan、ExecutionPlan |
| 5 装载执行 | evaluation → runtime、simulator | 注入组件，装载计划、初态和时间设置 | 可执行的实验实例与初始事件 |
| 6 推进工作 | simulator ↔ runtime 与组件 | 派发搬运；目标可见后计算；完成后释放资源并唤醒后继 | 输出 DataRef、动作计数、时间和诊断 |
| 7 验证与比较 | evaluation → workloads 参考及分析逻辑 | 比较 y，按声明边界计算延迟、能量和利用率 | 验证报告、指标、覆盖与解释 |
| 8 完成留存 | evaluation → artifacts | 核验各阶段记录和必需输出，再提交终态清单 | data/runs 下完整证据；ui 可查看 |

第 6 步不是一次函数调用就结束：硬件接收或背压 → simulator 处理下一个事件 → 更新资源和数据可见性 → runtime 提交新就绪工作，直到完成或诊断失败。costmodel 可以给出单动作服务代价，排队与重叠由该循环决定。

artifacts 从第 2 步起持续接收各阶段产物。发生错误时保留失败原因和已冻结输入。功能通过、执行完成、成本覆盖完整分别判断；只完成其中一项不能自动推出其他项。

### 这次实验保留下来的内容

下列路径均相对未来的 data/runs/<run_id>/，是已有产物规范的目录约定。当前尚无业务写入器。

| 保存位置 | 内容由谁产生 | 以后用来做什么 |
| --- | --- | --- |
| manifest.json | artifacts 汇集各阶段身份和状态 | 找到全部输入、版本、输出与依赖 |
| config/resolved.json | configuration | 解释真正使用的参数及覆盖来源 |
| workload/spec.json | workloads | 确认任务、形状、质量和输入引用 |
| hardware/spec.json | 硬件装配 | 确认资源、能力和拓扑 |
| plans/ | compiler；runtime 的动态增量单独记录 | 解释放置、切块、搬运和依赖 |
| models/manifest.json | costmodel 与硬件模块 | 确认模型实现、覆盖和成本依据 |
| results/metrics.json | simulator 提供计数，evaluation 生成指标 | 比较延迟、能量和资源使用 |
| results/validation.json | evaluation | 确认参考、容差、误差与通过范围 |
| outputs/ | 组件生成，artifacts 保存 | 校验数值或继续分析 |
| diagnostics/ 与 trace/ | runtime、simulator | 分析失败、等待和执行因果 |

## 5 不同工作需要调用哪些模块

表中的箭头表示信息流或实验调用顺序，不是新增代码依赖。contracts 是公共基础；需要形成实验记录时通过 artifacts 保存。ui 是可选入口，未来 CLI 与 ui 应使用同一组配置和实验接口。目前这些业务路线均待实现。

| 想完成的工作 | 主要调用路线 | 最终得到什么 |
| --- | --- | --- |
| 修改参数并检查是否合法 | 文本或 ui → configuration；evaluation 提供硬件能力约束 | 新草稿、有效参数、派生变化和错误位置 |
| 只看结构容量和理论界 | evaluation → configuration、workloads、相关硬件、costmodel → 分析 | 容量检查、理论上限或下界；不要求事件仿真 |
| 单独查询某项动作成本 | 条件对象 → costmodel | 带单位、适用域和覆盖的 Estimate |
| 检查一个编译转换是否正确 | WorkloadSpec 与输入 → compiler/src/interpret；workloads/reference 对照 | 转换前后语义证据；不要求完整事件仿真 |
| 评估单芯片延迟与能量 | evaluation → 配置、负载、chipmodel、成本 → compiler → runtime 与 simulator → 分析 | 完整计划、执行结果、质量与指标 |
| 比较数字计算与 CIM | 单芯片路线，更换 chipmodel 能力和成本，compiler 处理编码与映射 | 相同质量要求下的收益及编程、外围和搬运代价 |
| 研究双裸片或 3D CIM | 单芯片路线，加入 chipmodel 的 D2D、封装和所需热模型 | 封装内共享瓶颈、结构约束及条件收益 |
| 研究单节点多卡与 HBF 访问 | evaluation 装配 systemmodel 与 chipmodel；compiler 产生放置和路径需求；runtime、simulator 执行 | 主机、存储和共享 I/O 是否限制设备性能 |
| 研究多机多卡 | 在节点路线中加入 clustermodel；runtime 展开 collective | NIC 与 fabric 竞争、通信成本和扩展效率 |
| 扫描或优化参数 | evaluation/experiments/sweeps 或 evaluation/optimization → 每个候选走相应实验路线 | 合法与失败候选、指标集合、Pareto 关系 |
| 用测量修正成本模型 | data/calibration → evaluation/calibration → 新成本数据版本 → costmodel 读取 | 残差、适用域和新依据；按需重跑相关实验 |
| 查看或重新分析旧结果 | ui → evaluation → artifacts 读取清单与计数 → analysis | 新分析版本；有足够记录时无需执行硬件模型 |
| 重现一次旧实验 | evaluation → artifacts 读取冻结依据 → 重新装配与执行 | 引用原 run 的新运行，可核对差异 |

HBF 放在哪层取决于具体资源及接口归属：封装内介质、控制器由 chipmodel 表达，节点侧设备和主机路径由 systemmodel 组合。存储类型不自动决定全部拓扑，也不自动带来 CIM 能力。

恢复中断运行 Resume 另需完整兼容检查点，包括事件队列、硬件状态、runtime 状态和随机状态。只有 metrics.json 或输出张量时，可以分析结果，不能直接恢复执行。

## 6 修改一个参数到底会影响哪里

以模拟 CIM 的 adc_count 为例。它的参数定义属于 configuration/definitions；具体实例的取值存放于 config/hardware 中的模板或实例配置；并行转换行为属于 chipmodel/compute/cim/periphery；对应能量和面积依据由 costmodel 提供。

1. 在文本或 ui 中修改模板、实例或实验覆盖，并明确修改范围。
2. configuration 重新计算派生量，显示取值来源、受影响实例和约束。
3. evaluation 联合硬件能力与成本接口，检查新增组织是否有可用行为模型和成本依据。
4. compiler 按实验协议重新校验旧映射，或重新切块、放置和生成计划。
5. runtime、simulator 与硬件组件执行新计划，观察转换、累加、互连和等待的变化。
6. evaluation 对照基线解释指标；artifacts 为新配置创建新记录；ui 展示差异。

ADC 数量增加不保证整体吞吐同比增加，其他端口、累加或数据供应可能成为限制。成本表缺少新条件时显示依据不足。修改参数需要更新相关模型输入和计划身份，不能只改界面显示值。

| 改动范围 | 应在哪里表达 | 如何影响实验 |
| --- | --- | --- |
| 复用模板 | config/hardware/components | 使用它的实例可能都变化，先列出影响范围 |
| 某个硬件实例 | config/hardware/chips、systems 或 clusters | 只改变指定实例及其依赖 |
| 某次实验候选 | config/experiments 的覆盖 | 保留基线，生成候选配置和新 run |
| 参数定义或公式 | configuration/definitions 及派生逻辑 | 需要规则版本、验证和相关结果失效 |
| 运行中的 DVFS 策略 | runtime 策略与硬件事件 | 改变目标时间中的状态，按剩余工作推进 |

ui 的表单、文本配置和未来 CLI 共享同一字段定义。派生字段默认只读，运行配置保持冻结；编辑中的草稿属于下一次实验。若依赖缓存尚未细化，可以保守重跑相关链条，不能复用依据不匹配的旧结果。

## 7 各模块怎样解耦

解耦依靠公共对象、注入接口和唯一状态所有者。evaluation 构造具体 CPU、CIM 或网络组件，将符合 contracts 协议的对象交给 simulator 与 runtime；后两者调用协议，不需要导入具体硬件实现。

### 三种关系不要混用

| 关系 | 例子 | 表达含义 |
| --- | --- | --- |
| 代码依赖 | systemmodel 使用 chipmodel 的公开接口 | 谁允许导入谁，由 modules.json 约束 |
| 运行交互 | runtime 发请求，组件返回背压或完成 | 执行时的信息往返，通过注入协议实现 |
| 物理连接 | 某个 NIC 端口连接交换机端口 | 被模拟硬件怎样连通，由配置实例描述 |

compiler 依赖 contracts 和 costmodel，通过 HardwareSpec 了解资源，不读取硬件私有队列。configuration 通过公共约束描述校验，不反向导入硬件。ui 依赖 contracts、configuration 和 evaluation，图形数据由这些接口提供。

### 动态状态只由一个地方修改

| 状态或内容 | 负责维护的单元 | 其他单元如何使用 |
| --- | --- | --- |
| 参数草稿与冻结解释 | configuration | 读取 revision、有效值和哈希 |
| 静态计划与版本 | compiler 生成；动态增量由 runtime 标明来源 | 读取计划，变更生成新版本 |
| 软件队列与通信进度 | runtime | 完成通知、调度回调和只读诊断 |
| 硬件队列、端口、占用与数据有效性 | 拥有资源的 chip/system/cluster 组件 | 请求协议与只读快照 |
| 全局目标时间和待处理事件 | simulator | 时间接口、回调与事件记录 |
| 成本依据与适用域 | costmodel | 查询 Estimate 和来源 |
| 文件写入及运行清单 | artifacts | 读取清单与不可变引用 |

数据通路传 DataRef，控制通路传 Request/Event，观测通路传计数和快照。一次交换要明确生产者、消费者、版本、单位、有效期和失败方式。保存文件不会自动改变目标内存；绘图也不能修改硬件状态。

## 8 按目录查找应该修改的位置

### 主模块内部导航

此表集中列出实现责任。目录存在表示预留了归属；表内子目录目前仍以骨架为主。完整目录及依赖清单见 architecture/modules.json。

| 主模块 | 子目录与作用 | 开始阅读的位置 |
| --- | --- | --- |
| contracts | hardware、workload、plan、events、results 定义对象；units、versions 管单位和版本 | [模块设计](../contracts/docs/design.md) |
| configuration | definitions 字段；resolution 解析；validation 校验；migration 迁移 | [模块设计](../configuration/docs/design.md) |
| costmodel | interfaces 查询契约；providers/analytical、tabulated、external 成本来源；uncertainty 不确定性 | [模块设计](../costmodel/docs/design.md) |
| chipmodel | compute 计算；memory 介质和控制器；interconnect 片上及 D2D；composition 组合；packaging 几何与热；control、registry 控制与注册 | [模块设计](../chipmodel/docs/design.md) |
| systemmodel | composition/board、node 组合；io/pcie、cxl、dma、nic 节点路径；memory、topology 内存与拓扑 | [模块设计](../systemmodel/docs/design.md) |
| clustermodel | composition/cluster、groups 集群和组；fabric/links、switches、routing 网络；topology 拓扑 | [模块设计](../clustermodel/docs/design.md) |
| workloads | kernels、graphs 定义任务；reference 独立参考；profiles 负载特征；datasets 输入适配 | [模块设计](../workloads/docs/design.md) |
| compiler | src/ir 内部表示；globalsplit、globalsolver 划分放置；tiling 切块；memplan 内存；sched 调度；lowering 转换；interpret 解释；export、pipeline 导出与组织 | [模块设计](../compiler/docs/design.md) |
| runtime | dispatch 派发；streams 顺序；communication/p2p、collectives 通信策略；policies 动态决策 | [模块设计](../runtime/docs/design.md) |
| simulator | engine/events、time 事件与时间；adapters 协议适配；stats 计数；trace 轨迹；snapshots 检查点 | [模块设计](../simulator/docs/design.md) |
| artifacts | manifest 清单；codecs 编解码；storage 读写；provenance 来源 | [模块设计](../artifacts/docs/design.md) |
| evaluation | experiments/runner 单次实验；sweeps 扫描；analysis 分析；optimization 搜索；calibration 校准 | [模块设计](../evaluation/docs/design.md) |
| ui | forms 表单；views/topology、package、mapping、timeline 各视图；services 调用入口 | [模块设计](../ui/docs/design.md) |

compiler/src/lba 是保留目录，算法职责尚未定义，暂不接入 pipeline。compiler 下的 include、python、tests、tools、scripts、3rdparty、temp 分别预留公开头文件、Python 入口、局部验证、工具、脚本、依赖和临时输出；这些目录不表示相应语言实现已经存在。

### 支撑目录与根目录文件

| 路径 | 负责存放或执行什么 | 与主模块的关系 |
| --- | --- | --- |
| config/ | 硬件、成本、编译、运行、仿真和实验配置 | 文件由用户或工具编辑，configuration 解释 |
| data/inputs、calibration、runs | 输入、校准材料及运行记录 | workloads 或 costmodel 使用数据；artifacts 管保存 |
| docs/ | 总览、规范、方法、决策和 Word | 说明各模块约定，不承担业务执行 |
| example/ | 可阅读的结构示例与未来完整用例 | 展示怎样组合模块；当前结构 JSON 不可执行 |
| tests/ | 跨模块和集成验证归属 | 验证契约及组合；compiler/tests 聚焦编译内部 |
| tools/ | 开发维护工具 | 当前 check_structure.py 检查骨架一致性 |
| .github/ | GitHub 自动检查配置 | 推送后运行结构和文档检查 |
| .build/ | 本地文档构建、渲染和检查中间文件 | 不进入 Git，不是硬件模块或实验正式数据 |
| README.md | 仓库入口与当前状态 | 指向本文及模块导航 |
| .gitignore | 哪些缓存和运行数据不提交 | 不控制模型行为 |
| .gitattributes | Git 的文件文本等处理规则 | 不定义仿真对象格式 |

config 与 configuration 分别是“配置文件”和“解释配置的程序”；data 与 artifacts 分别是“被保存的数据”和“管理数据保存的程序”。修改文件内容、修改解释逻辑、修改模型行为是三种不同开发任务。

## 9 当前完成情况与使用入口

| 能力 | 当前完成情况 | 现在能得到什么 |
| --- | --- | --- |
| 架构与模块划分 | 已完成目录、职责、子目录和允许依赖设计 | 可以定位需求和规划接口 |
| 公共数据与生命周期 | 已完成文档约定，尚无可执行业务 schema | 可以评审字段和边界，不能直接导入配置运行 |
| 结构示例 | 已有 heterogeneous_topology.json 及检查 | 可以检查包含、端口、stack、视图和 rank 引用 |
| 文档与结构工具 | 已有 check_structure.py 和 build_docx.py | 可以运行一致性检查和 Word 构建 |
| 配置解释与参数界面 | 已有设计，解析器与前端未实现 | 暂不能用表单改参数后执行实验 |
| 编译与软硬件执行 | 已有设计，业务引擎未实现 | 暂不能生成可运行计划或芯片时序结果 |
| 实验优化与运行留存 | 已有设计，实验器与写入器未实现 | 暂不能自动扫描、校准或恢复运行 |

当前可执行的维护命令，在仓库根目录运行。第一条只需 Python 3.10 或更高版本；第二条还需 docs/tools/requirements.txt 中的文档依赖。

```text
python tools/check_structure.py
python docs/tools/build_docx.py --document overview
```

首次业务实现仍按窄范围推进：明确一个 GEMM/MatVec 的数值与数据契约，完成配置解析、一个计算引擎和 SRAM、合法计划及显式搬运，再验证资源争用和时间。随后才增加扫描、图形界面和更复杂硬件范围。

## 10 后续阅读和维护规则

日常先用本文定位模块与任务路线；修改具体行为再进入相应规范。以下文档承担不同权威范围，不需要从头全部阅读。

| 需要确认的事项 | 文档入口 | 它进一步规定什么 |
| --- | --- | --- |
| 顶层边界 | [架构设计](architecture/design.md) | 模块职责与装配原则 |
| 允许依赖和完整目录 | [模块清单](architecture/modules.json) | 机器可检查的结构边界 |
| 交换对象及完成语义 | [公共契约](interfaces/contracts.md)、[生命周期](interfaces/resource_lifecycle.md) | 身份、可见性、重试、取消和版本 |
| 结果怎样保存与复现 | [产物规范](interfaces/artifacts.md) | 运行清单、文件组织、Replay 与 Resume |
| 参数怎样计算和比较 | [参数方法](methods/parameters_and_math.md)、[工作流](methods/workflows.md) | 公式假设、变更和实验协议 |
| 是否已经达到实现要求 | [验证规范](architecture/validation.md) | A–F 阶段与证据门槛 |
| 深入某种架构 | [场景推演](architecture/scenarios.md)、[补充审视](architecture/design_review.md) | CIM、3D、HBF、异构与遗漏边界 |

新增功能时先确定它改变哪个状态、由哪个模块负责、增加哪种输入输出，再更新模块设计和公共契约。目录边界改变时同步 modules.json；本总览负责保持整体解释一致。Markdown 是正文维护源，Word 是相同内容的阅读版本。

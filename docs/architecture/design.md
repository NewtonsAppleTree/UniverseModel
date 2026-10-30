# 顶层架构与模块边界

## 1 目标与当前范围

UniverseModel 用于回答：给定工作负载、精度与物理约束，怎样组织计算、存储和通信资源，才能获得可解释、可复现的端到端收益。覆盖架构定义、软硬件建模、映射、功能验证、性能与能耗评估，并保留未来用实测或 RTL 校准的入口。

当前交付是模块目录、架构规范、结构示例与检查工具；编译器、执行模型、参数界面和仿真引擎尚未实现。chipmodel 保存软件架构模型，不包含 RTL。模型是否可信取决于行为覆盖、参数依据和验证证据，不能用目录完整代替实现完成。

体系同时覆盖 CPU、GPU、NPU、数字/模拟 CIM、3D CIM、双裸片、HBM/HBF、异构节点与多机多卡。每次实验只启用回答当前问题所需的层级和精度。

## 2 物理层级与五种关系

物理包含主链为 Cluster → Node → Board/Card → Package → Die → Tile/Core → Engine/Array。可选层级允许省略，但同一物理资源只能有一个直接所有者。Core 不作为跨所有架构统一的性能单位；CPU 核、GPU SM、NPU Tile、CIM Array 的能力由独立字段描述。

| 关系 | 表达对象 | 约束 |
| --- | --- | --- |
| 物理包含 Containment | 属于哪个节点、封装、裸片 | 单一所有者，无包含环 |
| 通信 Connectivity | 端口、链路、交换节点、可选路径 | 有方向、容量、协议和争用范围 |
| 地址 Address 与一致性 Coherence | 可访问区域、地址转换、一致性域 | 可连接不代表可直接访存或保持一致性 |
| 执行映射 Placement | 逻辑设备、rank、任务到资源 | 视图只引用资源，不复制物理状态 |
| 热与供电 Thermal/Power | 堆叠邻接、热耦合、供电域 | 可跨物理包含树，使用显式关联 |

DeviceView 表示软件可见设备。一只逻辑设备可引用两片 Die；一片 Die 也可在容量隔离约束下划分多个逻辑设备。rank 是通信参与者，不等于芯片、GPU 或节点数量。双裸片仅描述裸片数量与组织方式，不自动表示 3D。

3D CIM 分为裸片内三维阵列、多个 CIM 裸片堆叠、CIM 与数字逻辑堆叠。array_layers、die_stack_depth、compute_die_count 分开定义。同一封装可以同时有 2.5D 链接和局部 3D 堆叠。HBF 是 Flash 存储能力，不自动具备 CIM，也不能直接替代 HBM 的访问语义。

## 3 大模块与唯一职责

| 模块 | 负责内容 | 对外输出 |
| --- | --- | --- |
| contracts | 公共数据语义、单位、版本和端口协议 | 可独立验证的契约 |
| configuration | 定义、组合、派生、校验配置 | 冻结的 ResolvedConfig |
| costmodel | 动作成本、特征化和不确定性 | CostProfile、Estimate |
| chipmodel | Core/Tile/Die/Package 的资源与行为 | 能力描述、请求响应、局部状态 |
| systemmodel | Board/Node、主机内存、NUMA、DMA、NIC | 节点拓扑与系统资源行为 |
| clustermodel | 节点间 Fabric、交换、路由与通信组 | 网络资源与路径描述 |
| workloads | 任务语义、输入分布和独立参考 | WorkloadSpec、输入与参考规则 |
| compiler | 语义转换、划分、映射与静态计划 | PlacementPlan、ExecutionPlan |
| runtime | 派发、流、动态策略与集合通信展开 | 合法请求、同步和策略记录 |
| simulator | 时间推进、事件因果、统计与轨迹 | SimulationResult、TraceEvent |
| artifacts | 序列化、来源、版本与存储 | ArtifactManifest 和可恢复记录 |
| evaluation | 装配实验、校准、搜索和比较 | 实验集合、分析与推荐条件 |
| ui | 配置表单、拓扑、映射与结果视图 | 同一配置的编辑与解释入口 |

config 保存配置文件，configuration 实现配置逻辑；data 保存数据与运行记录，artifacts 实现保存规则。tests、example、tools 分别保存验证、示例与开发工具。所有主模块均有 README.md 和 docs/design.md；完整目录与允许依赖以 docs/architecture/modules.json 为准。

## 4 解耦规则与装配

contracts 不依赖其他业务模块。硬件模型逐层组合：systemmodel 使用 chipmodel，clustermodel 使用 systemmodel；各层可以查询 costmodel。compiler 只读取公共能力和成本接口，不读取硬件内部队列。runtime 与 simulator 只依赖 contracts 中的协议。

evaluation 是组合入口：加载配置、构造硬件与策略、把符合协议的实例注入 simulator，再委托 artifacts 保存产物。simulator 可以调用注入的组件，但不需要导入某个 CPU、CIM 或集群实现。模块依赖是代码关系；请求与完成通知可以双向传递，不意味着代码依赖成环。

| 状态 | 唯一维护方 | 其他模块如何获取 |
| --- | --- | --- |
| 已冻结配置 | configuration 输出，不可变 | 通过标识和哈希读取 |
| 硬件公共规格 | 硬件装配输出，不可变 | 通过能力契约读取 |
| 资源队列、端口、存储内容与占用 | 对应 chip/system/cluster 组件 | 请求协议、只读观测快照 |
| 计划与映射 | compiler 输出，不可变 | runtime 装载；变更生成新版本 |
| 软件队列、流和通信进度 | runtime | 通知与策略诊断 |
| 全局时间、待处理事件 | simulator | 时间接口与事件记录 |
| 成本参数和适用域 | costmodel | Estimate 及来源标识 |
| 运行清单与持久化事务状态 | artifacts | manifest 与版本化产物 |

NIC 属于节点；集群只连接和引用 NIC 端口。成本供应方不负责决定仲裁时序。资源占用由组件维护，仿真器可持有观测副本，但不能另建一套可独立修改的占用状态。

跨模块不传任意可变字典或编译器内部 IR。控制信息使用小型、带版本的数据对象；大张量使用 DataRef，显式声明所在存储、布局、版本和内容引用。宿主程序共享同一个数组，不能让目标系统中的搬运、复制和可见性消失。

## 5 一次实验的完整链条

1. 声明问题：负载、数值质量、时延/吞吐目标、容量/功耗/面积限制以及比较范围。
2. configuration 解析组件模板、架构实例和实验覆盖，计算派生量并校验约束，冻结配置及来源。
3. evaluation 装配对应模型，通过公共契约输出能力和拓扑；workloads 提供负载和独立参考。
4. compiler 进行划分、切块、放置、存储规划和调度，导出绑定配置与负载的计划。
5. runtime 依据依赖及已发生事件派发操作；simulator 推进时间；各资源维护状态并通知完成。
6. evaluation 检查功能、汇总规定边界内的性能与成本；artifacts 保存输入、计划、成本版本、结果和诊断。
7. 修改候选参数或映射策略，明确采用固定映射还是重新映射实验，比较收益、代价及不确定性。

延迟的解释链应能从“结果变慢”回溯至“哪个阶段等待、哪个共享资源受限、哪个参数或策略造成”。只有总 TOPS、总带宽和一个利用率常数，无法支撑这种解释。

## 6 按问题选择精度与扩展顺序

| 问题 | 最小必要模型 | 升级条件 |
| --- | --- | --- |
| 容量是否足够、上限是否合理 | 结构约束、工作量与解析下界 | 可行候选过多，需要区分实际瓶颈 |
| 哪种映射更快 | 存储生命周期、有限资源事件模型 | 差异来自流水线、bank 或仲裁细节 |
| CIM 是否带来端到端收益 | 编码、外围转换、数据移动与精度 | 结论对器件误差或温度敏感 |
| 3D/双裸片是否合算 | D2D、堆叠关系、容量与热预算 | 热反馈改变频率或可靠性判断 |
| 多卡/多机如何扩展 | NIC 注入、共享路径、collective 与并行策略 | 路由、队列或故障成为主要问题 |

首个实现闭环选择一个 GEMM/MatVec、小型数字引擎、SRAM 和显式搬运。通过独立参考与手算时序后，替换或增加 CIM，引入多核/封装，再扩展节点和集群。系统研究也可先使用经过校准的设备摘要模型，但摘要与细粒度实现不能同时收取同一段时间或能量。

## 7 文档层级与变更顺序

顶层边界见本文；跨模块语义见 docs/interfaces/contracts.md；保存与复现见 docs/interfaces/artifacts.md；公式、工作流与优化见 docs/methods；场景与第一性原理见 docs/architecture/scenarios.md 和 first_principles.md。

新增功能按“问题与假设 → 契约及参数定义 → 模块实现 → 验证证据 → 文档与示例”推进。先判断现有资源、关系或策略是否能组合表达，只有出现新的状态所有者或稳定职责时才增加顶层模块。

本轮补充审视见 docs/architecture/design_review.md：区分接口冻结前的 P0、对应场景报告前的 P1，以及由决策敏感性触发的 P2。专题覆盖请求/缓冲生命周期、模型组合、完整工作量、实验有效性与物理可行性；这些能力继续归属现有 13 个模块。

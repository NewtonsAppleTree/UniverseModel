# 公共契约与信息交换

## 1 契约的稳定边界

本文件规定后续实现必须保持的语义，当前尚未提供可执行 schema。外部契约与编译器内部 IR 分别版本化。所有公开对象携带 schema_version、稳定 ID、来源标识；单位、对象引用和枚举值由 contracts 统一定义。

| 对象 | 生成方 → 使用方 | 核心信息 |
| --- | --- | --- |
| ResolvedConfig | configuration → 装配与全部参与方 | 原始覆盖、完整有效值、派生值、单位、来源、哈希 |
| HardwareSpec | 硬件装配 → compiler/runtime | 资源、端口、能力、关系、地址域、约束、时钟域 |
| WorkloadSpec | workloads → compiler/evaluation | 语义、形状、布局、精度、输入引用与参考规则 |
| CostProfile / Estimate | costmodel → 模型/compiler/evaluation | 动作条件、延迟/能量/面积、范围、来源与置信说明 |
| PlacementPlan | compiler → runtime/evaluation | 分片、任务、rank、DeviceView、物理资源和内存放置 |
| ExecutionPlan | compiler → runtime/simulator | 操作、缓冲区、依赖、静态约束、目标与负载哈希 |
| CommunicationPlan | compiler/runtime → runtime | 参与组、顺序、数据分片、规约规则、算法选择 |
| Request / Event | runtime/组件 ↔ 组件/引擎 | 请求身份、端口、资源需求、依赖、状态及完成效果 |
| SimulationResult | simulator → evaluation | 状态、目标时间、计数器、输出引用、模型精度与诊断 |
| ArtifactManifest | artifacts → 全部工具 | 产物类型、位置、哈希、版本、来源、运行状态 |

构造 HardwareSpec 时只导出静态能力与可查询的公共约束，不导出私有队列对象。运行观测使用独立只读快照。估计结果带 estimated 标识，实际模拟完成时间使用 observed/simulated 字段，不能混用。

## 2 标识单位与地址可见性

物理实例 ID 在单次已解析架构中唯一。模板 ID 不是实例 ID；复用模板必须生成不同实例。DeviceView、rank 和通信组只通过引用连接实例。包含、连接、一致性、放置和热关系分别编码。

规范交换单位采用 byte、bit、second、hertz、joule、watt、square_millimeter、kelvin；显示层可换算 ns、GB/s 等。B 与 bit、GB 与 GiB 必须区分。cycles 必须绑定 clock_domain；多时钟事件转换到统一时间基准，舍入规则属于引擎版本。

DataRef 包含 data_id、version、storage_resource_id、region/offset、byte_length、dtype、shape、layout 和可选 content_ref/hash。data_id 相同不代表任意存储都已有有效副本。搬运完成或一致性协议确认后，目标副本才达到声明的可见性；写入产生新版本或显式声明原地更新规则。

大数据经引用交换；数据内容保存由 artifacts/storage 处理，目标内存有效性由硬件/运行时协议维护。未建模一致性的配置不得默认提供全局共享内存语义。

## 3 计划资源及依赖

计划至少绑定 schema_version、plan_id、hardware_hash、workload_hash、compiler_version、数值规则与能力要求。输入实际数据哈希在运行清单中绑定。

| 计划条目 | 必需字段 | 必须校验 |
| --- | --- | --- |
| 缓冲区 | 存储资源、偏移、长度、布局、对齐、生命周期 | 容量、地址有效性、别名与重叠合法性 |
| 计算操作 | 操作码、形状、输入输出、精度、目标资源 | 能力匹配、数值规则、数据位置 |
| 搬运操作 | 源/目标区域、数据版本、长度、路径约束 | 连通性、访问权限、边界与目标可见性 |
| 同步操作 | 等待事件、参与者、同步范围 | 引用存在、完成条件可达 |
| 通信操作 | group、sequence、参与者、字节数、规约规则 | 各参与者匹配；分片与数据类型一致 |

首版外部执行计划使用有限操作 DAG。循环在导出前展开或表示为有明确次数、依赖与成本范围的复合操作。自适应 runtime 策略可以生成追加操作，但必须记录决策和生成版本。

依赖边默认表示前驱完成后后继才具备资格。若支持分块流式消费，必须单独声明 chunk 级就绪事件与消费范围。RAW、WAR、WAW 及别名冲突需由计划或已声明同步机制覆盖。

PlacementPlan 描述放在哪里，ExecutionPlan 描述操作及约束，runtime 决定何时实际提交；预计时间不能强制消除资源争用。保留映射的参数实验仍须重新校验并生成绑定新配置哈希的计划。

## 4 请求执行与完成时间

组件协议包含能力查询、请求提交、接受/背压、状态转换、完成/失败通知和只读观测。接口可以实现为函数、事件或消息，不要求微服务。每个请求携带唯一 request_id、operation_id、目标端口、数据引用与回调/事件标识；重试必须避免重复执行。

操作状态为 submitted → ready → started → completed，任一未完成状态可转 failed/cancelled。submitted 表示进入软件或硬件队列；ready 表示依赖满足；started 表示取得必要资源；completed 表示规定的数据和同步效果已可观察。接收确认不等于完成。

延迟 Latency、发射间隔 Initiation Interval、占用 Occupancy 分别描述。流水线可以晚完成但早接受下一项；多阶段操作按真实占用释放资源。预留多个资源应声明原子获取或统一获取顺序，避免隐藏死锁。

simulator 管理统一时间与稳定事件排序，组件维护局部状态。相同时间的处理顺序固定，例如完成/释放 → 可见性与依赖更新 → 策略回调 → 仲裁发射。顺序及同时间级联事件的终止规则必须版本化；禁止向过去插入事件。

传输分段建模时，链路、DMA、内存端口与协议阶段声明各自的计费范围。端到端摘要延迟与内部细节只能选择一种权威计时方式。能否重叠由依赖和资源决定，不用简单相加或统一取最大值替代。

## 5 通信与异构数值语义

集合通信契约先定义结果语义，再选择 ring/tree 等算法。group_id、参与者排序、sequence_id、元素类型、reduction、分片长度必须匹配；缺少参与者不能被当作通信耗时较长。rank 到设备的映射独立保存，允许一设备多 rank 或一 rank 协调多个引擎，但共享容量仍只计一次。

CPU/GPU/NPU/CIM 的数据类型、布局、累加顺序和转换均显式描述。CIM 权重映射包含编码、位切片、符号、阵列位置和校准版本。模拟误差需记录模型、分布、随机种子、相关性假设及适用条件。输出误差不能仅用硬件吞吐替代。

HBF 的页粒度、访问接口、写入限制和介质行为由具体能力描述决定；需要预取/搬运时生成显式操作。连接协议的名称不能自动授予字节寻址、缓存一致性或持续峰值带宽。

## 6 版本兼容与结果状态

不支持的 schema、单位、能力或字段语义应明确报错，不静默忽略。迁移生成新对象与迁移记录，不修改历史实验。内容哈希遵守统一规范化规则；哈希证明身份一致，不证明语义正确。

SimulationResult 区分 succeeded、failed、cancelled，保留部分统计的有效区间。所有必需操作完成且输出达到规定可见性才可成功。仍有工作却无可推进事件时输出死锁/无进展诊断；事件上限、目标时间上限、宿主墙钟超时分别记录。

TraceEvent 保存时间、阶段、资源、操作、状态和阻塞原因；必要时保存关联 request_id 与数据版本。核心计数器独立于可关闭或采样的轨迹。持久化清单、原子提交与复现规则见 docs/interfaces/artifacts.md。

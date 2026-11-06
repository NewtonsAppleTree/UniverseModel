# contracts：公共语义与协议

## 核心与边界

最重要的是不同模块对“同一对象、同一单位、同一次完成”理解一致。contracts 定义公共值对象、资源能力与端口协议，不组织实验，不包含硬件状态或编译优化逻辑；无业务依赖。

`hardware` 管资源/端口/关系，`workload` 管语义与数据引用，`plan` 管放置/执行/通信计划，`events` 管请求及通知，`results` 管结果，`units` 管量纲，`versions` 管兼容性。结构格式校验在本模块；具体芯片能否支持某配置由对应硬件能力约束判断。

## 输入输出与不变量

输入是有版本的结构数据或协议调用，输出是已解析值对象、诊断或兼容转换结果。对象引用必须存在；包含树不能有环；依赖图必须满足所采用的执行语义；`DataRef` 的逻辑身份、位置和内容版本不能混为一体。动态状态只通过事件或只读视图跨边界。

接口对象见[公共契约](../../docs/interfaces/contracts.md)。对象字段应分为 required、optional、derived、extension；扩展不得悄悄改变公共字段含义。未知操作与不兼容版本直接诊断，未知展示元数据可按明确规则保留。

独立组件拟增加 ComponentSpec、PortSpec、BenchSpec、StimulusSpec 及结果范围，详见[组件接口提案](../../docs/interfaces/component_protocols.md)。统一身份、单位和生命周期，compute/memory/transfer/sampled_signal 等有效载荷按协议区分。现行 ExecutionPlan 生产者字段的迁移要求见[局部仿真规划](../../docs/architecture/composable_simulation.md)，新对象不能被当作已存在的 schema。

张量的语义轴、逻辑 ROI、存储 view 和 partial result 的最小关系另见[张量区域契约提案](../../docs/interfaces/tensor_regions.md)。axis 编号不能代替语义，ROI 不能代替物理地址，partial shape 相同也不足以允许归并；具体 tiling 策略由 compiler 维护。

## 参数与检查方法

本模块的关键配置是 `schema_version`、单位体系、时间表示、ID 命名空间和兼容表。量纲推导属于可验证约束，例如 `bytes / (bytes/second) = second`；不能凭字段都叫 bandwidth 就允许 bit/s 与 B/cycle 混算。

JSON/YAML 是存储形式，不是完整契约。校验分三层：语法/类型 → 引用及结构 → 跨字段语义。硬件可行性与独立功能正确性是后续阶段。布局、精度、溢出规则、方向和可见性不能只写成注释。

## 演进、验证与保存

先定义最小闭环实际需要的对象，再扩展可选能力。重大语义变化升级主版本，兼容迁移保留旧输入和转换记录。公共契约避免包含具体 Python/C++ 对象或私有 IR，便于未来替换语言和序列化方式。

验证使用合法/非法最小对象、版本迁移往返和引用检查；序列化往返必须保持语义身份。保存 schema 版本、规范化规则版本与迁移链。边界稳定的收益是模型和编译器可以分别演进，不是为所有未来场景预先堆字段。

## 生命周期与模型覆盖

条件能力需同时表达 shape/布局/精度等前提，错误分类区分不支持、不可行和缺少成本依据。accepted、source_consumed、destination_visible 及取消过程见[生命周期规范](../../docs/interfaces/resource_lifecycle.md)；模型覆盖不能仅由一个 fidelity_level 代替，见[组合规则](../../docs/architecture/model_composition.md)。

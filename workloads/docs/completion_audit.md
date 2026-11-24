# workloads 完成审计

2026-11-23，依据[使命](../../PROJECT_MISSION.md)复核[W0–W6规划](development_plan.md)。本次补齐既定交付的数值边界和证据检查，不扩大为通用模型/服务框架。

## 研究与实现

| 核查问题 | 修复与证据 |
| --- | --- |
| 正确的浮点分类输出是否被错误拒绝 | 9个均匀key、同类one-hot V的实际Attention输出为`(1.0000000000000002, 0)`；现在通过域检查，准确率1、log loss 0。越过容差或行和错误仍拒绝。 |
| 保存的数值结论能否重建 | 新mapping/retrieval记录保存`reference_output`；外部参考另存NumPy Attention/RBF输出。回读从实际/参考观测重算最大误差、失败索引和通过标志，并重新计算RBF分类指标。 |
| 方案与资源证据是否自洽 | 核对候选计划、完整行所有权、scratch/backing求和与预算、操作计数守恒、搬运清单长度和区域边界、摘要指标与未知成本。 |
| 任务质量结论是否绑定评估协议 | 核对训练标签/维度、划分类配额、validation预测与准确率/混淆矩阵、首个最高分选参、Attention维度/scale/one-hot V、预测变化计数、配对质量门槛和外部后端。 |

概率端点与行和采用固定绝对容差`PROBABILITY_TOLERANCE=1e-9`，行和使用`math.fsum`。argmax直接使用原始观测，不归一化或修改保存值。只有log报告使用`min(1,max(p_true,probability_floor))`；`probability_floor=1e-15`，`clipped_samples`仍只计低于下限的真类概率。端点容差不替代独立数值比较的`atol/rtol`。

## 记录版本与证据边界

新执行的`ExperimentSpec.implementation_id`为`attention-mapping/v2`或`retrieval-quality/v2`，必须包含参考输出。任务配置和bundle容器schema仍为v1，接口调用方式不变。回读支持历史implementation v1；旧记录没有参考输出，只能检查原数值结果的结构与内部一致性，不能声称重新计算了误差。同一研究清单不能混合实现版本。

回读不生成输入、不拟合/执行模型、不重新运行高精度参考或NumPy；数值比较、计数守恒与指标重分析只使用保存观测。该检查不提供第三方认证，也不能独立证明保存参考本身正确、全部访存顺序正确或物理性能成立。历史验证集仅保存预测/指标，回读能核对计数和选参规则，不能重建其log loss；原始执行和来源快照仍是证据的一部分。

## 验收

命令、统一27例与研究范围继续见[完成报告](completion.md)。本次独立证据目录为`.build/workloads-audit-20261123`，原交付记录保留在`.build/workloads-completion-20261123`。

新增6项回归：workloads 1、integration 5，另在现有NumPy测试增加外部输出/指标/布尔标志反例。全仓库425项，423通过、2项可选PyTorch因环境未安装跳过；实际NumPy 2.2.6对照通过。分组contracts 6、clustermodel 72、costmodel 7、chipmodel 141、workloads 47、compiler 20、integration 132。规则检查覆盖68个实现目录；结构检查通过13模块、103份模块Python、177份Markdown和4份DOCX来源哈希；旧chipmodel示例和空白检查通过。

统一验收仍为27例：23个执行成功、4个预期执行失败，成功记录中保留3个低质量负对照。新版记录完整保存/回读，历史v1完整验收记录也实际读取通过。`acceptance/source.json`保存189份源码/测试/config/数据/来源文件，源码身份为`1455a22188ee47fd9a3785f7bcc6d79c2f61c508+workloads-sha256:af021af31756357ce21b418281fe4821b9fb625e35516dddec4ffa3a9e0dadcb`。`before.json`和`validation.json`确认仅改动6份既有源码/测试，新增1份证据检查源码，Git索引未变化。

wheel位于`.build/workloads-audit-wheels/UniverseModel-0.1.0-py3-none-any.whl`，SHA256为`15d4398530eef50e2ec990f7ac14f25cd2608049bb3773ea8de309659325b830`。100份打包Python完整名单/原始字节一致，`python -I`从解包目录导入97份项目模块，并显式提供NumPy依赖目录；27例执行与新记录/验收记录回读均与工作区一致。配置/数据仍由仓库提供。以上是本地证据，不表示远端CI已执行。

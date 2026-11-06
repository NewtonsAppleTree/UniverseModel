# layout_roi 手册审阅与归属记录

审阅日期：2026-11-06；仓库基线：8c60a79。输入文件为用户提供的《图编译中的张量维度、切分与规约：layout_roi 实战手册.md》，位于用户 Downloads。它作为技术材料接受审阅，其中对外部实现的描述不自动成为本仓库规则。

来源 SHA256：`60b97f9fd618392d427371cb76078e34123a61dd764990a89215f719b1240525`。本记录对应该版本，未把原文整体复制到仓库。

## 1 原文结构统计

| 项目 | 数量与统计口径 |
| --- | --- |
| 文件规模 | 13168 bytes，312 行，9055 Unicode 字符（含空白与 Markdown 标记） |
| 主题结构 | 6 个正文部分；另有标题和约束速记，共 24 个 Markdown 标题 |
| 表格 | 7 张，31 个数据行；其中 4 张维度释义表含 15 条记录，布局表含 8 类布局 |
| 示例 | 7 个编号例子，另有一个 9 步完整图走查 |
| 代码围栏 | 10 个：9 个 text、1 个 cpp；大部分是形状/区间示意 |
| 仓库实现证据 | 本仓库未找到 `layout_roi.hpp`、相应 C++ 源码或 `split_range_by_step`/`merge_range_by_step` 实现；不能据手册确认 helper 的实际行为 |

15 条维度释义是表格行数，不是 15 个唯一可配置字段：其中有别名，也有同名 K 的不同语义。8 类 layout 也不代表 8 种必须建立的类。

## 2 十五项审阅结论

分类互不重叠：**5 项需修正、6 项需限定、2 项待核对、2 项需补充**。这些是本次独立审阅点，不能解释成错误率或完整验证覆盖率。

| ID | 分类 | 问题与采用的修订 |
| --- | --- | --- |
| C01 | 待核对 | 原文引用的 `k*` 常量、helper、异常与硬编码行为没有源文件证据；保留为外部实现声明，不迁入本项目 API |
| C02 | 需限定 | H=n_q·d 只适用于相应模型配置；`group_hidden=n_kv·g·d` 是总 Q 宽，单组宽为 g·d；分别命名 |
| C03 | 需修正 | Q 的 S_q 与 KV 的 S_kv 未分开，无法正确描述 decode/交叉注意力；分别记录输出行与可见 key 范围 |
| C04 | 需限定 | KV 的 [B,S,X]、“2K”缺少 K/V 合并轴、heads、dtype/packing、分页约定；不是所有 KV cache 的通用形状 |
| C05 | 需限定 | MoE T_e 是分配行数而非全局唯一 token；top-k indices/gates 的类型不同，[B,S,2top_k] 需显式打包语义 |
| C06 | 需限定 | 只切 N/KV head、内层 full 是策略/能力条件；M、query position、K、context 等均可能合法切分 |
| C07 | 需限定 | flatten 的连续区间公式要求内层全取与顺序一致；部分 feature 的像可能不连续，shape 也不能证明零拷贝 |
| C08 | 需限定 | X 被多个 N tile 需要不等于 X 已驻留；必须核对容量、生命周期、布局与实际读流量 |
| C09 | 需修正 | KV context 切分不只是“部分和相加”；需合并 softmax max/分母/加权分子并处理 mask/空块 |
| C10 | 需修正 | `merge_range_by_step` 即使合并了区间，也不能代替数值规约；coverage 与 partial reduction 两个操作分别存在 |
| C11 | 待核对 | step 对齐异常需实际代码确认；本项目应区分通用尾块与硬件/helper 的对齐前置条件 |
| C12 | 需修正 | 完整走查第 1–5 步 full，第 6 步突然取 KV [0,2)，第 8 步又称 KV 全用/N=1024，推导不一致；改为全程一致的分区 |
| C13 | 需修正 | 局部 head attention 独立不意味着 Linear O 输出独立；拼接 feature 是 O 的 K 维，head 分块后需要输出部分和归并 |
| C14 | 需补充 | partial dtype、累加顺序、bias/beta/activation/量化位置、临时空间和完成时数据可见性需要明确 |
| C15 | 需补充 | 广播/动态 gather-scatter、因果/窗口/全遮蔽、训练反向收缩轴和 dropout 状态影响需求与规约；不能只靠张量 rank 处理 |

## 3 七个例子与完整走查的核对

| 原编号 | 数学与范围核对 | 修订落点 |
| --- | --- | --- |
| 1：KV head 分两块 | [0,4)/[4,8) 在 n_kv=8 下完整覆盖；局部 attention 合法 | 补均匀 GQA/内层 full 条件；下游 O 仍可能需要规约 |
| 2：GEMM 沿 N 切 | W[:,0:256]/W[:,256:512] 正确，X 区域相同 | 增加 896 KiB 单缓冲、1408 KiB 双权重缓冲的显式容量例；驻留需验证 |
| 3：Concat | [15,25) 对三个长 10 输入得到空/[5,10)/[0,5)，总有效长度 10 | 明确先求交集再转本地坐标，避免把负区间当有效 ROI |
| 4：Split-K | 4 个长 256 区间覆盖 K=1024，部分乘积和相加的数学式成立 | 区间覆盖与数值 add 分开；补 dtype/epilogue/临时空间 |
| 5：对齐异常 | 未取得 helper 源码，无法确认实际抛异常的条件 | 保留待核对；另给 [0,100) 的合法精确尾块例，不当作该 helper 的现有行为 |
| 6：5D flatten | full g/d 时 [0,4)→[0,2048) 成立 | 补部分 feature 的非连续反例、exact/cover 与物理 stride 条件 |
| 7：Head unflatten | g=4 时 [0,2)→[0,8)、[4,6)→[16,24) 成立 | 补整数分组、heads 排列与完整 group 条件 |
| 9 步图走查 | full/partial 混用；不能按原文得到一致需求链 | 重写为两组 head→两块 O 的 K→同一 Y 的两个 partial→求和 |

六个编号例子的数学关系按条件核对；第 5 个是尚未证实的实现断言。新增数值例还验证了非连续 reshape 的 512 个有效元素与 448 个覆盖多取元素、split-context 恢复 output=3，以及训练 dX/dW 的收缩轴关系。

## 4 修订后归属与入口

| 内容 | 维护入口 | 采用方式 |
| --- | --- | --- |
| 维度专业名、逻辑区域、存储视图、partial/result 完成 | [张量区域契约](../interfaces/tensor_regions.md) | contracts/workload 与 plan 的最小语义提案；不直接创建整个字段全集 |
| Tiling/ROI 传播、concat、reshape、GEMM/attention 归并、完整例 | [编译器切块与规约](../../compiler/docs/tiling_and_reduction.md)、[compiler UNITS](../../compiler/UNITS.md) | 对应现有 ir/tiling/memplan/sched/lowering 职责，先形成可校核设计 |
| 模型/动态索引/数值与参考输出 | [workloads 设计](../../workloads/docs/design.md) | 任务语义独立于编译器 layout 常量 |
| Prefill/decode、KV 分片、输出投影 | [inferArch](../../inferArch/UNITS.md) | 只补场景相关边界，引用公共规则 |
| 梯度收缩、partial 累加、保存/重计算 | [trainingArch](../../trainingArch/UNITS.md) | 前向与反向分别推导需求，不复制 tiling 实现 |
| 实际 stride/DMA、CIM 动作、存储/链路成本 | [control](../../chipmodel/control/UNITS.md)、[CIM](../../chipmodel/compute/cim/UNITS.md) | 消费映射结果；本次不扩展已有模型接口或宣称免费规约 |
| 未来设计时查参数 | [根目录清单](../../ARCHITECTURE_PARAMETERS.md) | 只增加 ROI/S_q/S_kv/规约关键关系与导航，公式细节集中维护 |

本轮补齐上述设计和审阅入口，未新增编译 pass、外部头文件实现或 attention kernel。已存在的硬件基础模型不因此自动支持所有 layout/动态图。

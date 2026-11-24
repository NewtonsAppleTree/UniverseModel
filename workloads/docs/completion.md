# workloads W0–W6 完成报告

本轮按[项目使命](../../PROJECT_MISSION.md)完成[既定任务规划](development_plan.md)。交付的中心是独立任务语义、状态/输入来源、可执行映射与可检验研究证据；可组合性不依赖完整芯片/集群链路。W0–W6均有实现和验收，后续课题的机制/质量/物理扩展按主张进入。

下文保留W4–W6交付时的419项回归与原始证据。后续完成审计修复概率端点舍入、补齐保存参考输出并加强回读一致性；当前实现及最新验收见[收尾审计](completion_audit.md)。

| 包 | 完成内容 | 实际证据与适用范围 |
| --- | --- | --- |
| W0 | 复用GEMM/MatVec、Linear/ReLU/MSE/SGD与工程边界，明确资源/输入/参考归属 | workloads只依赖contracts；无通用空类 |
| W1 | MHA/GQA/MQA与显式因果位置、逻辑计数、稳定输入、独立Fraction/Decimal参考 | 手算、60组独立float比较、极值与精度边界 |
| W2 | 不可变KV快照、token轴追加、形状/容量/源身份、Attention绑定 | 多batch/head整段prefill与逐token/分块等价；不冒充物理page管理 |
| W3 | 有限完整profiles、文件SHA/语义绑定/来源/用途/预算与失败 | 10例合成台架、CSV真实观测、严格来源边界 |
| W4 | query-block计划、QK/softmax/AV解释、KV复制与score驻留、scratch/backing、MAC/DMA接入 | 18组随机形状×4策略、5个同任务方案、容量失败、逐区域/搬运守恒 |
| W5 | UCI真实RBF分类，train-only拟合、validation选参、固定held-out质量和数值简化 | 3个split×4变体、独立NumPy matmul/直接距离、无泄漏和质量负对照 |
| W6 | 版本/原始源码与数据哈希、完整运行记录、只读回放、规则/文档/CI/wheel | 统一27例，4个预期执行失败及3个低质量负对照；最终验收记录见STATUS |

首包接口见[Attention/KV与来源](foundation_usage.md)，后续完整公式、独立调用、源许可及实验口径见[映射与质量](mapping_and_quality.md)。各目录UNITS维护专业参数，实际字段仍以代码为准。既有芯片/集群接口保持可用，新增行为没有反向导入硬件到workloads/contracts。

本轮W4–W6新增24项测试，全仓库419项：417通过、2项可选PyTorch因默认环境未安装跳过，NumPy独立测试实际通过。分组为contracts 6、clustermodel 72、costmodel 7、chipmodel 141、workloads 46、compiler 20、integration 127。规则通过68个实现目录，结构通过13模块、102份模块Python、176份Markdown及4份DOCX来源哈希；旧示例与空白检查通过。

完整本地证据保存在`.build/workloads-completion-20261123`：acceptance/含27例、原始源码/数据身份和三个只读摘要，references/含UCI原始来源及许可页面；各组日志、validation.json及wheel_audit.json保存工程核对。source.json覆盖188份Python/config/数据/来源文件，源码身份为`1455a22188ee47fd9a3785f7bcc6d79c2f61c508+workloads-sha256:79a4ebeda1de3dee081990b0892b96c047b5b497defa99a56916ee4189dac66d`。

wheel为`.build/workloads-completion-wheels/UniverseModel-0.1.0-py3-none-any.whl`，SHA256 `c958e5d6fe79181a4d8495fad84b962adf7effa8bffaba8badac5d676bd714a0`；99份打包Python的完整名单/原始字节与工作区一致。python -I从解包目录导入96份项目模块，显式提供NumPy 2.2.6的依赖目录，三组27例及原记录/新记录回放与工作区完全一致。项目代码未从checkout回落导入；配置和数据仍由仓库提供。

## 可复现入口

```text
python tools/validate_workloads.py --output .build/workloads-acceptance
python tools/validate_workloads.py --read .build/workloads-acceptance
python -m pip install -r tools/requirements-workloads-numpy.txt
python tools/validate_workloads.py --numpy-reference --output .build/workloads-numpy
python tools/validate_workloads.py --read .build/workloads-numpy
```

基础、映射、任务质量可分别通过workload_demo、attention_demo、retrieval_demo运行，均支持保存/回读。原始来源数据随仓库提供，运行不联网。NumPy仅在显式选择时使用，默认路径只用标准库；回放任何已存外部参考结果都不需要NumPy。CI包含标准库和独立NumPy两条验收路径，远端运行状态与本地测试分开。

## 研究证据的边界

W4给出的是指定分配/复制/驻留下的功能与资源工作证据。已知MAC/DMA子集下界不是整任务时间，softmax服务、存储/争用及完整物理成本仍未知；没有执行证据时不报告吞吐/能效。query分块融合不等于online-softmax/context partition。

W5给出真实有限分类集的质量证据：三个split基线正确数28/29/27，各30例；轻度舍入未改变准确率，粗控制降为10/30并被质量门槛拒绝。NumPy两种表达补充软件独立性；这些结果不表明数据具备LLM/生产服务代表性，不建立跨任务泛化或新的研究创新。重复split共用原始观测，不当作独立样本构造显著性结论。

变体仍为float64，十进制舍入不是硬件低bit存储，预处理/舍入/物理转换成本未知。原Iris数据已知历史差异按来源保留，不能将其他库版本静默混入相同身份。

## 后续研究触发条件

| 需要检验的主张 | 下一步必要工作 |
| --- | --- |
| context切分/online softmax降低容量或提高并行性 | 加入新的归约语义、重缩放、partial状态和工作/访存守恒证据 |
| 低bit KV/算子带来能效收益 | 明确格式/打包/转换、舍入误差、质量容差和真实动作成本 |
| 对完整语言模型或推理服务有效 | 固定模型/数据/任务指标、投影/位置编码、实际trace、状态/请求生命周期 |
| 训练算法或Attention反向有效 | 按需扩展梯度/优化器语义，补独立autograd/有限差分及收敛证据 |
| 动态执行、真实吞吐/时延或物理可行 | 接入runtime/simulator或设备、标量/访存/队列服务，补器件/系统校准 |

这些是后续课题的范围选择，不计为已经实现，也不需要为了宣称目录完整而提前全部展开。当前已完成W0–W6约定任务；后续任务应继续按“研究什么、怎样建模、如何证明”设定范围与验收。

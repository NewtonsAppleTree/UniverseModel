# Linear 训练 step 与短链：实施计划

日期：2026-11-23；依据 PROJECT_MISSION、[路线](../RESEARCH_ROADMAP.md)和[线性首批](linear_experiment_plan.md)。目标是让平台表达真实的训练依赖、梯度/权重版本与完整工作，检验从单算子向短链组合的接口。

## 本批范围

正整数 batch 和层宽，float64、无 bias 的一层或多层 Linear，隐层可用 ReLU（零点导数取 0）或 identity；MSE=所有输出元素平方误差的均值，SGD 无 momentum/weight decay。每步计算所有权重梯度和输入梯度，然后一起生成新权重版本。更新前不修改输入状态；拒绝版本或内容身份不符的梯度。

前向/反向 GEMM 复用已有分块解释器。转置显式材料化，保存激活、梯度及新旧权重都有命名张量和生命周期；scratch 与张量 backing 存储是两个独立预算。提供完整操作/有效 payload 账本，但辅助算子的硬件服务未校准，完整 step 时间与能耗未知。只报告 GEMM 子集资源下界，不据此宣称训练加速比。

## 顺序与验收

| 批次 | 交付 | 验收 |
| --- | --- | --- |
| A | 训练语义、不可变参数/梯度、SGD 与输入生成；独立精确参考 | 手算 Linear、ReLU 零点、梯度有限差分、旧梯度拒绝、无输入状态污染 |
| B | 短链固定阶段规划、GEMM lowering、功能执行、命名张量生命周期 | 完整前向/反向/更新；显式转置；使用前生成/最后使用后释放；两个容量预算与边界反例 |
| C | 实验比较、动作/流量记录、失败保存回读 | 同输入与旧状态多方案；所有输出、梯度和新权重对照；不能用 MAC 子集时间冒充完整 step |
| D | 固定版本 PyTorch CPU 功能交叉验证、文档、CI、测试与打包 | 标准库默认链独立运行；可选 PyTorch 用 autograd 对比；记录版本/配置/结果，不作为性能校准 |

PyTorch 在 `.build/torch-crosscheck` 独立环境安装固定 CPU 版本；若外部环境不可用，保留明确诊断，标准库路径仍须完成。Timeloop/ZigZag/SCALE-Sim 的性能对照需先统一布局/数据流/服务假设，另作下一批实验；本批不建立一个未经校准的通用事件引擎。

## 验收记录

2026-11-23，A–D 在上述范围内完成。入口为 `python -m example.training_demo`，完整语义与独立调用见[指南](../../evaluation/docs/training_step.md)。

| 验收 | 实际结果 |
| --- | --- |
| 数值与状态 | 单层手算、batch/output mean 归一化、中心有限差分、ReLU 零点、旧版本及同版本异源梯度拒绝、连续两步、非有限结果拒绝 |
| 计划与生命周期 | 前向/反向/更新顺序、dW/dX 收缩轴、转置材料化、唯一生产/定义后使用、inclusive 活跃区间、backing/scratch 独立容量反例通过 |
| 默认训练比较 | B=2、widths=(3,4,2)、ReLU、lr=0.125；三合法方案均为 loss=0.18958117067813873、version=1；超 scratch 方案留失败记录 |
| 完整工作量 | 120 MAC，另计 58 次标量算术、16 次比较、16 次选择、34 个转置元素；backing 峰值 568 B；完整 step 时间/能耗未知 |
| PyTorch | Python 3.12.4 / torch 2.5.1+cpu，CPU float64；autograd/SGD 对照一层、两层 ReLU/identity、三层 ReLU及两种分块，默认候选另保存完整结果 |
| 测试 | 新增 23 项：7 workloads + 8 compiler + 6 常规集成 + 2 可选框架；默认全仓库 108 通过、2 跳过；框架环境这 2 项另行通过 |
| 规则/结构/打包 | 52 个实现目录的 UNITS/注释规则；13 模块、46 个 Python 文件允许 import、150 份 Markdown 和 4 份 Word 源哈希检查通过；wheel 含 7 个训练实现文件，不包含 PyTorch 依赖 |
| 保存与回读 | 8 份默认运行（exact/torch 各 4）已验证并保存；默认无 PyTorch 环境可回读外部参考 bundle；失败点仍保留 |

[验证快照](../reference/data/training_validation_2026-11-23.json)保留实际输入/配置、参考环境/pip freeze、全部数值校验、指标及 50 份源码内容哈希。原始完整 bundle 在 `.build/training-exact-20261123` 与 `.build/training-pytorch-20261123`。源码标记为 `5ebefa1-plus-training-workspace`；哈希不是完整源码归档，正式复现仍需源码/补丁和环境快照。

CI 已配置默认训练保存/回读和独立 pinned PyTorch job；本地通过不宣称远端 CI 已执行。本批没有验证真实训练性能、能耗、收敛、分布式框架或外部架构模拟器；不改变工作区当前 clustermodel 的独立开发安排。

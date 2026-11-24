# workloads：任务生产与独立参考

W4/W5进一步提供Attention映射数值校验、真实表格来源、标准化RBF检索图与分类质量协议；实现/边界见[映射与质量](docs/mapping_and_quality.md)，完整W0–W6验收见[完成报告](docs/completion.md)。真实Iris是限定任务证据，不代表通用真实负载库。

本模块只依赖 contracts。[kernels](kernels/UNITS.md) 构造稠密 GEMM/MatVec 与 Attention 及逻辑工作量，[graphs](graphs/UNITS.md) 提供 Linear 训练短链和不可变逻辑 KV 追加，[reference](reference/UNITS.md) 提供独立整数/有理数/Decimal参考。[profiles](profiles/UNITS.md)维护有限 Attention 案例，[datasets](datasets/UNITS.md)加载带原始字节哈希和来源的本地数据。Attention首包的职责、参数、调用和证据见[指南](docs/foundation_usage.md)；通用图、代表性真实负载和分布式训练仍待实现。

任务数据归 workloads/调用者所有；不读取硬件状态或 compiler 计划。输入是 M/N/K、dtype、实际数据或生成 seed，输出是公共任务值、参考数组和逻辑计数。工作量 `MNK MAC = 2MNK conventional operations`，唯一张量存储不是实际流量。最敏感参数是形状、精度和验证容差；无本模块目标时延/能耗。

调用顺序：创建 [LinearSpec](../contracts/workload/UNITS.md) → 显式数据或 `generate_inputs` → `describe_work` / `reference_linear` → `compare_output`。可跳过整个实验链独立使用。语义、限制和命令见[线性实验指南](../evaluation/docs/linear_mapping.md)，独立验证见[测试](../tests/workloads/test_linear.py)。

## 训练短链扩展

[graphs](graphs/UNITS.md) 已提供 Linear 训练链的输入生成与完整工作量；[reference](reference/UNITS.md) 提供精确有理数前向/反向/更新参考。通用图、真实训练 profile、分布式与优化器家族仍待具体问题驱动。调用：TrainingSpec → state/data → reference_training 或独立 compiler 执行 → 比较全部输出/梯度/新权重；[训练指南](../evaluation/docs/training_step.md)维护完整用法与限制。

[reference](reference/UNITS.md)新增通用整数MatVec精确参考，为CIM数值验证提供独立点积；不导入chipmodel，也不共享其电导/ADC/移位实现。

<!-- model-fields:start -->



<!-- model-fields:end -->

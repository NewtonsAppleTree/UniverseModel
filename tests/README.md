# 验证归属

W4–W6新增24项：compiler 3项Attention区域/搬运测试，workloads 7项真实数据/无泄漏/质量边界测试，integration 14项独立数值/映射/真实任务/NumPy/完整27例验收测试。来源、固定划分、配对条件及适用域见[完成报告](../workloads/docs/completion.md)。

workloads首包新增27项：[Attention语义/独立数值参考](workloads/test_attention.py)10项、[KV前缀/分块与身份](workloads/test_kv_cache.py)4项、[本地数据与有限profiles](workloads/test_profiles.py)6项、[完整实验/失败/回放](integration/test_workload_experiment.py)7项。覆盖手算、60组独立float算法、GQA复制等价、极值与状态边界；证据口径见[指南](../workloads/docs/foundation_usage.md)。

基础收尾新增[数值边界测试](chipmodel/test_numerical_boundaries.py)与[统一验收测试](integration/test_chipmodel_acceptance.py)：线路大计数、热收敛、CIM有理乘加/下溢、严格序列，以及完整预期失败/哈希/只读回放。全仓库七组回归与104案例验收互补，见[完成报告](../chipmodel/docs/completion.md)。

CH9新增[成本接口测试](costmodel/test_costs.py)、[物理模型测试](chipmodel/test_physical.py)和[物理集成测试](integration/test_physical_experiment.py)，覆盖固定来源再现、条件/未知成本、唯一计量、观测窗口、50组高精度热参考、CH8读写/线路量和完整保存回读。成本组独立运行 `python -m unittest discover -s tests/costmodel -p "test_*.py" -v`；其余沿用chipmodel/integration组。来源再现不代替器件校准，见[CH9指南](../chipmodel/docs/physical_evidence.md)。

CH6新增[计算能力模型测试](chipmodel/test_compute_capabilities.py)与[计算能力集成测试](integration/test_compute_experiment.py)，涵盖CPU阶段槽枚举、GPU资源消耗/启动限额、NPU签名/尾批、完整单因素协议及Tile供数/不重复计费。运行方式沿用chipmodel和integration的独立discover命令，边界和证据见[指南](../chipmodel/docs/compute_capabilities.md)。

本目录按 contracts、configuration、costmodel、chipmodel、systemmodel、clustermodel、workloads、runtime、simulator、artifacts、evaluation、ui 与 integration 划分。compiler 的阶段验证保留在 compiler/tests。

本目录规定测试归属，已完成的验证与可运行命令见[实现状态](../docs/STATUS.md)。功能与时序实现时，优先增加独立参考、容量/端口/因果反例、可手算争用与完整复现案例，避免仅重复代码行为。

完整验收标准见[验证规范](../docs/architecture/validation.md)。

CH5新增[CIM模型测试](chipmodel/test_cim.py)、[独立整数参考测试](workloads/test_integer_matvec.py)和[CIM实验测试](integration/test_cim_experiment.py)：80组随机整数矩阵×两种差分、不同矩形、精确电压/码值、ADC尾批/尾slice、样本年龄与内部/外部容量、资源II、量化/溢出/源身份和完整保存回读。证据与复现见[CIM指南](../chipmodel/docs/cim_bench.md)。

chipmodel CH1–CH4新增[基础模型测试](chipmodel/test_foundation.py)与[数字Tile集成测试](integration/test_digital_tile.py)：有理数精度、逐byte独立地址枚举、共享端口/路径账本、预留/owner反例、相同输入功能/流量、单因素瓶颈迁移及完整候选回读。复现与边界见[指南](../chipmodel/docs/foundation_usage.md)。

集群收尾新增[独立路径参考与批量回归](clustermodel/test_closeout.py)5项，以及[回读严格性测试](integration/test_cluster_experiment.py)2项；覆盖360个端点对、不同长度/显式路径、profile替换、停用后恢复和重复候选/运行身份。网络相关测试累计103项；最终全回归结果见STATUS。宿主规模实验可用[benchmark_cluster.py](../tools/benchmark_cluster.py)，不把计时阈值写入正确性测试。

此前横向新增[模型测试](clustermodel/test_breadth.py)18项、[集成测试](integration/test_cluster_breadth.py)6项，覆盖leaf-spine、最短路径候选、多轨共享、方向停用、需求矩阵与记录兼容；当时网络相关测试累计96项。

C2/C3阶段新增[集群模型测试](clustermodel/test_cluster.py)23项及[实验集成测试](integration/test_cluster_experiment.py)10项，验证四节点精确值、共享NIC/交换/介质、双工/组/路由、帧基准、敏感性与完整候选回读。加上C1，共72项网络相关测试。

C1网络39项测试：[公共契约](contracts/test_network.py)6项、[链路](clustermodel/test_links.py)13项、[直连图](clustermodel/test_topology.py)13项、[工程记录](integration/test_network_experiment.py)7项。验证独立手算、分包/基准、双工/共享引用、profile边界和保存回读；C1范围不包含交换路由，新增C2/C3测试覆盖静态交换路由和共享账本；仍无争用执行或物理校准。工程测试随integration运行，模型用：

```text
python -m unittest discover -s tests/contracts -p "test_*.py" -v
python -m unittest discover -s tests/clustermodel -p "test_*.py" -v
```

ADC 的独立阈值参考在 [test_adc.py](chipmodel/test_adc.py)；各子模块及系统关系测试在 [test_models.py](chipmodel/test_models.py)，覆盖工作量、GPU 驻留、CIM 功能链、DDR/突发、容量/布局、热模型、资源包络与计量范围。在仓库根目录用 Python 3.10+ 标准库执行：

```text
python -m unittest discover -s tests/chipmodel -p "test_*.py" -v
```

结构检查另行运行 `python tools/check_structure.py`；它不代替数值或时序验证。

代码/参数文档规则另行运行 `python tools/check_model_rules.py`。更新字段后可用 `--write-docs` 刷新各目录 UNITS.md 的生成区；默认只检查，不修改文件。

通用工程边界在 [test_framework.py](integration/test_framework.py) 验证：严格配置/覆盖、冻结嵌套值、规范化哈希、独立 ADC/DMA 接入、重复调用隔离、失败/未知指标、模式/单位、保存往返与损坏/不完整产物，以及依赖/注释检查的非法样例。单独运行：

```text
python -m unittest discover -s tests/integration -p "test_*.py" -v
```

它验证工程接口，不代替硬件的数值或时序校核。结构检查还核对主模块 Python import，允许依赖以 modules.json 为单一维护定义。

线性实验新增三层验证：[workloads](workloads/test_linear.py) 提供手算/精确参考、格式与身份边界；[compiler](../compiler/tests/test_linear_mapping.py) 检查尾块、覆盖、归约生命周期和容量/流量；[integration](integration/test_linear_experiment.py) 验证 MAC/DMA 时钟、未知能耗、数值失败、敏感性、记录和 CLI 回读。后者随现有 integration 命令运行，前两组单独运行：

```text
python -m unittest discover -s tests/workloads -p "test_*.py" -v
python -m unittest discover -s compiler/tests -p "test_*.py" -v
```

本轮 27 项新增测试验证声明语义；尚未提供外部工具性能校准或训练执行证据。

2026-11-23 训练批次另新增 23 项测试：[workloads](workloads/test_training.py) 7 项手算/归一化/有限差分/边界，[compiler](../compiler/tests/test_training.py) 8 项反向轴、ReLU、状态和生命周期/容量反例，[integration](integration/test_training_experiment.py) 6 项完整工作/记录/多形状/质量检查，以及 2 项可选 PyTorch autograd/SGD。它们使用上面的四组 discover 命令；默认共 108 项通过、2 项跳过，固定 PyTorch 环境额外通过这 2 项。外部 CPU 数值对照不是目标性能校准。

```text
.build/torch-crosscheck/Scripts/python.exe -m unittest discover -s tests/integration -p "test_training_experiment.py" -v
```

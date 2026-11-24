# W4/W5：Attention映射与真实任务质量

本包接续[Attention/KV首包](foundation_usage.md)，完成[开发计划](development_plan.md)中的映射接入、真实任务协议和对应工程验收。任务语义保持独立于硬件；每项结果区分数值正确性、有限测试集质量、资源分析和物理证据。它服务于[项目使命](../../PROJECT_MISSION.md)中的软硬件协同研究基础设施，当前实验不声明新的架构机制或论文创新。

## W4：同一任务下的映射比较

研究问题是query分块、score/probability驻留和KV布局怎样改变数据移动及容量。公共[AttentionPlan](../../contracts/plan/attention.py)声明query_tile、score_policy、kv_layout及完整AttentionBlock。每块拥有一个batch/query head的连续完整输出行，沿完整KV上下文归约；真实尾块不填充算术。compiler独立检查行游标、网格、顺序、无重复/遗漏及任务身份。没有context split、online softmax、反向或动态执行语义。

| 接口 | 行为与证据 |
| --- | --- |
| compiler.src.tiling.attention | build_attention_plan / validate_attention_plan：有界计划生成、独立行覆盖验证 |
| compiler.src.memplan.attention | plan_attention_memory / count_attention_traffic：命名区域、分离scratch/backing和实际payload |
| compiler.src.interpret.attention | execute_attention_plan：按计划做KV复制、可见QK、stable softmax、AV和可选中间结果落存 |
| workloads.reference.attention | compare_attention：完整输入身份绑定，atol+rtol数值校验，独立于计划实现 |
| evaluation.experiments.runner.attention | 同任务/输入/硬件预算比较；格式匹配的chipmodel MAC/DMA查询、失败和完整记录 |

共享KV布局的K/V backing按Hkv拥有，计算时每个query block仍重新读取对应整段K/V，不推断硬件缓存复用。expanded布局先为每个query head从原K/V读一份再写扩展副本；原始输入保留，扩展区域独立预留，重复copy不是免费别名。随后计算读取扩展区。二者都沿可见key计算，因果mask不产生额外无效MAC，但本版仍传输完整KV head的payload。

fused把一个query block的score/probability在scratch中原地复用；spill通过同一外部命名临时矩阵完成score写/读、probability写/读，每个矩形score元素增加4×8 B搬运。masked位置存零并排除softmax。这是query分块融合，不是FlashAttention/online-softmax实现，不声称消除了所有局部score材料化。

设q=min(query_tile,Sq)，scratch为Q(qD)、K(SkvD)、V(SkvDv)、score(qSkv)、O(qDv)、max/sum(2q)六个disjoint arena的最大保留量，总计8[qD+Skv(D+Dv)+qSkv+qDv+2q] B。它是本分配器的保守预留，不是最优活跃峰值。backing独立保留原Q/K/V和O，expanded另加8B·Hq·Skv·(D+Dv)，spill另加8B·Hq·Sq·Skv。两份容量属于不同资源，不能互相借用或重复命名为同一个scratch。

每条AttentionTransfer给出命名tensor、方向、域内offset和连续payload；变换prelude的block_index=-1。下游可独立把这些区域映射到具体资源；当前MAC/DMA分析只接payload，不假装包含bank冲突或DRAM时序。算术严格为float64单独乘加，overflow作为候选失败，不由高精度参考的成功掩盖。

[默认5方案](../../config/experiments/attention_mapping.json)固定B1/Hq4/Hkv2/Sq3/Skv4/D2/Dv3、scale0.5、因果起点1；scratch340 B、backing2000 B。实际QK/AV工作72/108 MAC，36次exp，max和分母归约各24次。所有成功方案数值通过：

| 方案 | 外部payload B | scratch预留 B | backing预留 B | 解释 |
| --- | ---: | ---: | ---: | --- |
| fused_q1 | 2400 | 248 | 800 | 每块1行，共12块，重复读取KV |
| spill_q1 | 3936 | 248 | 1184 | 相同工作增加1536 B中间结果搬运 |
| fused_q2 | 1760 | 336 | 800 | 2行块加真实尾块，共8块，减少KV重读 |
| expanded_q1 | 3680 | 248 | 1440 | 显式KV复制增加1280 B搬运及640 B backing |
| capacity_failed | 未执行 | 424需求 | 800需求 | 3行块违反共同340 B scratch预算，保留失败 |

MAC能力签名必须与float64非FMA运算一致。唯一MAC与串行DMA分别查询一次，known_resource_lower_bound=max(理想MAC服务,串行DMA服务)；假设同一DMA请求服务不重叠。softmax各动作、复制量和传输明细独立保留。实际执行还缺标量服务、依赖/争用、SRAM/DRAM访问和物理动作成本，target_execution_time/target_energy为None，不能将payload或局部下界差异报告为整任务加速比。

独立调用先构造spec/inputs和plan，再分别调用memory/traffic/interpreter，最后compare_attention；不需要通用runner。运行研究入口：

```text
python -m example.attention_demo --output .build/attention-mapping
python -m example.attention_demo --read .build/attention-mapping
```

## W5：真实有限任务、质量与来源

选定的基础设施验证问题是：在固定真实分类数据、训练支持集和质量门槛下，对KV支持坐标进行数值简化是否改变预测和质量。任务为标准化特征上的RBF核检索分类器，可准确表达为Attention，避免为本次验收构造完整模型库。数据/参数/模型状态/Attention接口均可独立替换；这不代表语言模型或生产服务。

[UCI Iris来源](../../config/workloads/iris/README.md)有150行、4项cm特征、3类标签；取得原始字节、说明和API元数据，保留DOI、CC BY 4.0署名、哈希和已知数据差异。SHA256为`6f608b71a7317216319b4d27b4d9bc84e6abd734eda7872b71a458569e2656c0`。原始数据未修正；特别保留来源记录的第35/38行差异。本地CSV加载先做路径包含性、大小/样本数、原始字节SHA、宽度/标签/有限值校验，不下载或推断缺失值。

每个seed按类把行号依据`SHA256(split-sha256/v1:{seed}:{class}:{row})`排序，取每类30训练、10验证、剩余10测试，合计90/30/30。分割穷尽且互斥；均值与population标准差仅在训练集上拟合，常量特征scale取1。标准化支持集及标签构成不可变RetrievalState；身份绑定实际数据、划分、均值/尺度和支持内容。预处理前后的值和全部划分随运行保存。重复seed使用相同原始观察，并非独立数据集抽样。

对标准化query x和支持向量z，设Q=[2x,−||x||²,1]、K=[z,1,−||z||²]，则QK=−||x−z||²，V是支持标签one-hot。显式scale是RBF逆带宽；D=特征数+2=6，Dv=类别数3。Q/K的浮点构造本身有舍入，独立NumPy直接距离表达式用于核对这一变换。V和训练支持标签参与模型；测试标签只用于最后质量报告。

scale候选固定为0.25/1/4，只用验证准确率选取首个最大值，保存完整选择表；所有数值变体使用同一选中scale、支持状态和测试集。变体为unrounded、key_decimals=1、12和−2；采用Python round的十进制位数及ties-to-even语义，对支持坐标舍入后重新构造K的范数项，query和V保持原值。此变换仍使用float64存储，不能据此宣称INT量化容量、少搬运或硬件加速；舍入/预处理的物理成本未知。

质量报告保存每例概率/预测/真值、confusion[true,predicted]、correct、accuracy、平均自然对数loss及裁剪数量。argmax并列取第一个声明的类别。概率端点与行和允许1e−9绝对舍入误差，log-loss显式使用1e−15下限及1上限；只为log报告裁剪，不修改原始观测或预测。质量门槛是准确率至少0.8且相对同split基线下降不超过0.05；使用精确计数比例与参数的十进制值比较，避免浮点边界误拒绝。

默认seed0/1/2分别选scale4/1/1，基线测试正确数28/29/27（各30例）。1位和12位舍入在这些划分上未改变准确率，属于本协议下的无质量收益情形；−2位控制把支持坐标归零，正确数10/30，数值实现正确但任务质量不合格。共有12个执行成功的研究案例，其中3个质量门槛失败是预审负对照；不得把它们改成异常或从结果移除。这一结果不能推出其他任务/分布或更低精度存储也满足质量要求。

可选[NumPy适配](../../evaluation/calibration/numpy_attention.py)提供两条独立表达：batched matmul/GQA/causal softmax及直接exp(−scale·distance²)分类。NumPy实际版本、Python和平台参与配置身份；当前使用2.2.6。依赖延迟加载，默认标准库路径可用；显式要求NumPy但不可用时形成失败记录，不静默忽略。它提供外部软件功能对照，没有目标设备计时或校准主张。

```text
python -m example.retrieval_demo --output .build/retrieval-quality
python -m pip install -r tools/requirements-workloads-numpy.txt
python -m example.retrieval_demo --numpy-reference --output .build/retrieval-numpy
python -m example.retrieval_demo --read .build/retrieval-numpy
```

独立路径为load_classification → stratified_split → fit_retrieval → select_retrieval_scale → retrieval_attention → 参考/解释器 → classification_metrics/classification_gate。原始数据/元数据、seed、选择表、实际模型与QKV、结果、失败和外部版本都在专业接口或记录中；不依赖完整实验才能调用其中一步。

## W6：完整验收与回放

```text
python tools/validate_workloads.py --output .build/workloads-acceptance
python tools/validate_workloads.py --numpy-reference --output .build/workloads-numpy
python tools/validate_workloads.py --read .build/workloads-numpy
python tools/check_model_rules.py
python tools/check_structure.py
```

统一验收固定基础10例、映射5例、质量12例，共27例，含4个预期执行失败和3个成功执行的低质量负对照。检查完整名单/预期，原始Python/config/数据/来源字节身份，三个bundle保存/回读一致性，最后提交report.json；已有目录不覆盖。未达预期的研究bundle和摘要先保留，缺少最终report表示验收未完成。

回读先核对完整工件字节和索引，再从保存记录重建摘要；不拟合模型、不重新选参、不读原始数据、不需要NumPy。分类指标会由保存的概率和真值重新计算，属于产物重分析。回读可发现缺失、混用来源/预算/配对状态、改动和指标矛盾，不能重新证明原模型正确或建立第三方签名认证。

新implementation v2必存参考输出和外部输出，回读重算数值比较、检查计划/资源守恒与分类证据；历史v1保留读取但没有参考输出的误差重算能力。版本、概率边界及验证范围见[收尾审计](completion_audit.md)。

全部接口有UNITS与参数关系，独立手算/随机数值/分块覆盖/无数据泄漏/精确质量边界/来源反例与记录测试随模块维护。最终测试、安装包和外部证据见[完成报告](completion.md)及[STATUS](../../docs/STATUS.md)。后续研究按实际问题增加上下文切块、低精度存储、真实语言模型、请求轨迹、任务质量或目标系统证据，属于扩展课题，不用空类或未知成本为零来制造覆盖。

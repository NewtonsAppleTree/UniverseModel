# workloads 首包：Attention、逻辑 KV 与可复现实验

本包落实[项目使命](../../PROJECT_MISSION.md)中的任务语义、可替换输入和独立验证需求。开发顺序与后续边界见[W0–W6计划](development_plan.md)，实际验收见[STATUS](../../docs/STATUS.md)。已有 GEMM/MatVec 和 Linear 训练短链继续可用；本包补充给定 Q/K/V 后的缩放点积 Attention、逻辑 KV 追加、本地数据清单与有限案例实验。

## 研究问题与模块分工

本包能够验证 query/KV 长度、MHA/GQA/MQA 分组与因果位置怎样改变数学输出、计算需求和逻辑容量，以及分块 prefill/decode 是否使用了正确历史。它为随后比较切块、融合与 KV 布局提供相同任务和独立参考。

| 位置 | 所有权与接口 | 模型层次 |
| --- | --- | --- |
| contracts/workload | AttentionSpec/Inputs、KvCacheSpec/State；冻结语义与实际数据 | 标准库公共值，不执行硬件 |
| workloads/kernels | describe_attention、generate_attention | 纯整数逻辑计数；有界确定性测试输入 |
| workloads/graphs | append_kv、attention_from_cache | 调用方持有不可变逻辑快照，追加产生新状态 |
| workloads/reference | reference_softmax、reference_attention | 小规模独立数值参考，无目标时序 |
| workloads/datasets、profiles | 本地字节哈希/来源、有限完整案例与宿主预算 | 不下载、不推断代表性，不调度请求 |
| evaluation/experiments/runner | workload.run_study/write_study/read_study | 通用实验、失败记录和只读回放 |

workloads 只依赖 contracts；compiler 负责随后选择布局、分块和实际搬运，chipmodel 负责映射后资源服务，runtime/simulator 负责需要动态执行时的状态协议。完整模型投影、RoPE、bias、dropout、任意 mask、量化、Attention 反向及完整 Transformer 不在本包语义中。

## 参数、布局与工作量

布局为 Q[B,Hq,Sq,D]、K[B,Hkv,Skv,D]、V[B,Hkv,Skv,Dv]，各轴正整数；Hq 能被 Hkv 整除，连续 Hq/Hkv 个 query head 共享一个 KV head。D 与 Dv 独立；scale 必须显式给定、有限且正，常见 1/√D 只是调用方选择。输入为有限的显式 Python float，存储语义为 binary64。

因果 query i 只看 j≤query_start+i；起点非负且 query_start+Sq≤Skv。非因果起点必须为零。所有行至少有一个可见 key，全屏蔽行在本版不可构造。输出 O[B,Hq,Sq,Dv]，概率 P[B,Hq,Sq,Skv] 的屏蔽位置为零。

设 R=B·Hq·Sq·Skv，行数 N=B·Hq·Sq。完整矩形 QK 和 AV 分别为 R·D、R·Dv MAC。非因果有效配对 P=R；因果 P=B·Hq·[Sq·(query_start+1)+Sq·(Sq−1)/2]。P·(D+Dv) 是可利用 mask 的工作量，能否省掉矩形工作仍需具体映射证明。缩放、max、减法、exp、分母归约和除法独立计数，不把 SFU 工作兑换成 MAC。分母归约按每行 n−1 个数学加法计，不统计 Python 初始化和高精度软件内部指令。

逻辑 Q/KV/O 字节分别为 8B·Hq·Sq·D、8B·Hkv·Skv·(D+Dv)、8B·Hq·Sq·Dv。一个全矩形 score 矩阵为 8R B；这个字段不表示必须材料化、同时活跃容量或外存流量，融合方案需另给生命周期。MHA/GQA/MQA 改变 Hkv 时，KV 唯一容量随之变化，不能按 Hq 重复计入共享数据。

## 独立调用与 KV 顺序

```python
from contracts.workload.attention import AttentionSpec, KvCacheSpec, KvCacheState
from workloads.kernels.attention import describe_attention, generate_attention
from workloads.graphs.kv_cache import append_kv, attention_from_cache
from workloads.reference.attention import reference_attention

spec = AttentionSpec(batch_size=1, query_heads=2, kv_heads=1,
    query_length=2, kv_length=2, key_dim=2, value_dim=3,
    scale=0.5, causal=True, query_start=0)
data = generate_attention(spec, seed=7)
work = describe_attention(spec)
reference = reference_attention(spec, data)

empty = KvCacheState(spec=KvCacheSpec(batch_size=1, kv_heads=1,
    key_dim=2, value_dim=3, max_tokens=16))
state = append_kv(empty, k=data.k, v=data.v, tokens=2,
    expected_identity=empty.identity_hash)
bound = attention_from_cache(spec, state, data.q)
assert reference_attention(spec, bound) == reference
```

追加输入按 [B,Hkv,新增tokens,D或Dv] 排列；在每个 batch/head 内追加，不能对完整扁平数组直接 old+new。每次成功追加 version+1、tokens 增加实际长度，旧快照保持不变。capacity_bytes=8B·Hkv·max_tokens·(D+Dv)，resident_bytes 使用当前 tokens；只计逻辑 payload，不计 page、元数据、目标传输或 Python 对象开销。

expected_identity 绑定源状态的形状、容量、版本与内容。该纯函数允许同一旧快照产生不同分支；它不维护全局最新版本，也不代替并发提交、淘汰或 page 分配协议。decode 应显式将 query_start 设置为本次 query 在 resident K 序列中的绝对位置；容量/位置不匹配会失败。

## 数值参考和验证预算

QK 与 scale 先用 Fraction 精确计算，减去精确行最大值后才转 Decimal 做 exp、归一化与 AV；这样可保留巨大公共偏移下的小差异。Decimal 有效位数 precision_digits 为 32–256，默认 80，采用独立局部上下文。概率与输出各自在最后转成 binary64，非有限输出拒绝；很小的概率/输出允许舍入为零。AV 使用内部高精度概率，因此保存的概率舍入为零时，输出中仍可能保留它与大 V 相乘的贡献。

这是有限精度高精度参考，不是实数形式证明，也不模拟目标 float64 每条指令的中间舍入。对大消去/极小概率敏感的研究应提高精度并补独立误差证据。max_elements 限制生成/读取后输入材料化，max_score_pairs 限制完整概率矩阵，max_macs 限制参考可见配对的 QK+AV 工作，max_file_bytes 限制文件读取/解析字节；这些都不是目标资源，也不是严格的 Python RSS 或 wall-time 上限。describe_attention 只用整数推导，可以分析超出参考预算的形状。

本包测试包括手算、60组独立 float 算法比较、GQA 与显式复制 MHA 等价、因果前缀均值、极值公共偏移/下溢、Decimal 环境隔离，以及多 batch/head 的整段 prefill 与逐token/分块追加等价。独立验证见[Attention测试](../../tests/workloads/test_attention.py)与[KV测试](../../tests/workloads/test_kv_cache.py)。参考执行成功不产生“与自身比较通过”的质量结论。

## 数据来源、默认案例与回放

[默认配置](../../config/experiments/attention_workloads.json)是 10 个合成案例：prefill MHA/GQA/MQA、短/长 decode、非因果 cross Attention、本地手算文件，共 7 个成功；输入规模超限、错误文件 SHA256、参考规模超限，共 3 个预期失败。case.expected_status 是审查过的夹具预期，实际 status 来自运行；任一预期不符使 CLI 退出码为 1。不同任务形状不是同预算硬件速度排名。

[本地文件](../../config/workloads/attention_inputs.json)使用 attention-input-file/v1、完整 spec_identity 和 Q/K/V；manifest 保存 dataset_id、相对 POSIX 路径、原始字节 SHA256、source、kind、split、usage_terms、limitations。先确认路径解析后仍在显式 data_root 内，再限量读、核对原始哈希、严格 JSON 与语义 shape。仅重排空白也会改变文件哈希。来源/用途是声明，加载器不替代授权、统计独立性或代表性验证。

```text
python -m example.workload_demo --source-revision <明确源码身份> --output .build/attention-study
python -m example.workload_demo --read .build/attention-study
python -m unittest discover -s tests/workloads -p "test_*.py" -v
python -m unittest discover -s tests/integration -p "test_workload_experiment.py" -v
```

--config 和 --data-root 可分别指定；data_root 与配置文件位置独立。已有输出目录不覆盖。输入准备失败保存来源、预算和诊断，不伪造 tensor；参考失败保留已准备的实际输入。RunRecord 保存完整配置、输入、来源版本、输出/失败和假设。host_elapsed_s 仅是通用 callback/收集窗口，不包括外部输入准备，不能作目标时延或全流程耗时。目标 execution_time/energy 明确为 None 并说明未知原因。

回读核对 bundle 原始字节、身份、完整名单和输出结构，不生成输入、不读原始 dataset、不重跑参考；它证明记录一致性，不能重新证明数值正确。哈希保护意外改动，不作为第三方签名认证。省略 --source-revision 会保留 unrecorded，表示源码来源不完整。

## 下一包的入口

本节保留首包交接背景。W4与限定真实任务W5现已完成，使用[映射与质量指南](mapping_and_quality.md)及[完成报告](completion.md)中的现状与验收入口。

W4 将冻结 Attention 的矩阵/非矩阵计划、因果工作、GQA 共享和 KV 区域生命周期，先做功能解释与工作/搬运守恒，再选择格式匹配的 chipmodel 资源。必须显式计入 softmax、格式转换与额外移动，才能研究切块/融合/驻留的收益。W5 按具体课题补模型/数据版本、独立外部基线与真实任务质量；当前合成案例不证明准确率、困惑度、收敛、服务代表性或目标硬件收益。

# 芯片架构与 AI 训练/推理参数清单

本清单用于设计查阅：先确定工作量和资源边界，再选计算、存储、互连及物理参数，最后计算时间、流量、容量、能耗和面积。它整合了已有参数手册与本次提供的两份术语材料，补充关键关系并修正容易误导建模的表述。核对日期：2026-11-06。

**这里列的是候选设计参数，不是全部必填项，也不表示对应机制已经实现。** 实际字段与接口以 [chipmodel/UNITS.md](chipmodel/UNITS.md) 及其子目录为准，能力以 [STATUS](docs/STATUS.md) 为准。本清单不另建配置 schema，不为每个名词生成类，也不提供跨器件通用的“典型值”。

## 1 使用方法与边界

### 1.1 从问题选择参数

| 设计问题 | 首先查什么 | 模型归属与继续阅读 |
| --- | --- | --- |
| 一个算子或训练/推理阶段需要多少资源 | [工作量与数值](#2-工作量与数值语义)、[AI 指标](#8-ai-训练推理的资源账本与指标) | [trainingArch](trainingArch/README.md) / [inferArch](inferArch/README.md) 组织场景；复用 workloads/compiler/runtime |
| CPU/GPU/NPU/SFU 能提供什么能力 | [计算](#3-计算与控制资源) | [compute](chipmodel/compute/UNITS.md) |
| CIM array + DAC/ADC + 缓冲如何配平 | [CIM](#4-cim-阵列与混合信号外围)、[首批路径检查](#9-设计时的十项检查与首批路径) | [CIM](chipmodel/compute/cim/UNITS.md)、[memory](chipmodel/memory/UNITS.md) |
| SRAM/cache/DDR/HBM/Flash 怎样选组织 | [存储](#5-存储层次与介质) | [memory](chipmodel/memory/UNITS.md)、[控制器](chipmodel/memory/controllers/UNITS.md) |
| 数据怎样跨单元、die、节点移动 | [互连与搬运](#6-互连数据搬运与同步) | [interconnect](chipmodel/interconnect/UNITS.md)、[systemmodel](systemmodel/docs/design.md)、[clustermodel](clustermodel/docs/design.md) |
| 频率、功耗、面积与热是否支持方案 | [物理条件与成本](#7-时钟电源封装热与成本) | [packaging](chipmodel/packaging/UNITS.md)、[costmodel](costmodel/docs/design.md) |

选择顺序：目标指标 → 任务和数据 → 资源与连接 → 相关参数 → 公式/局部模型 → 敏感性与来源核查。某个参数只有改变可观察结果或可行性约束时，才需要进入本次模型。

### 1.2 范围分层

| 层次 | 本仓库关注的内容 | 采用规则 |
| --- | --- | --- |
| 核心 | 操作与精度、并行度、L/II、容量/端口/粒度、流量/带宽、依赖与共享资源、PPA | 每条研究路径都要交代；没有该资源可注明不适用 |
| 按问题启用 | CPU 乱序细节、缓存一致性、DRAM 刷新/调度、PHY、CIM 非理想性、可靠性、制造与经济成本 | 先判断对结论的敏感性；可用有依据的摘要或外部特征化 |
| 不作为常规参数全集 | ABI/驱动/OS/工具链、Secure Boot/TEE、DFT/JTAG/覆盖率、DRC/LVS/CTS 流程 | 仅提取影响工作量、延迟、面积、功耗或成本的结果；不模拟完整软件生态和签核流程 |

软件策略中的 tiling、并行、重计算、调度会改变硬件需求，因此保留其**作用于硬件的量**。同理，验证和测试是参数证据来源，不需要把每项流程都变成硬件 Unit。

### 1.3 参数角色与统一单位

下表及后文用 **设 / 标 / 推 / 观** 分别表示设计或场景输入、特征化输入、公式派生量、运行观测量。策略和技术名是枚举，不是可直接相加的数值；同一概念的目标值、标定值和实测值须分别命名。

| 约定 | 说明 |
| --- | --- |
| 时间与频率 | 时间用 s，展示可用 ns/µs；频率 Hz；cycle 必须绑定 clock domain。固定频率时 T=C/f；最低时序约束换算为 C_min=ceil(t_min·f) |
| 容量与流量 | bit 与 B 区分；1 B=8 bit。kB/MB/GB 为十进制，KiB/MiB/GiB 为二进制；容量与实际传输字节分开 |
| 接口速率 | bit/s、B/s、transfer/s、symbol/s 分开；1 MT/s=10⁶ transfer/s。GT/s 不自动等于有效 Gbit/s |
| 工作量 | MAC、FLOP、integer op、instruction、µop、conversion、token 分别统计。MAC 按 2 op 计数时必须声明，不能直接混用各类峰值 |
| 物理量 | 电压 V、电流 A、电导 S、电阻 Ω、电容 F；能量 J、功率 W；面积 mm²；热阻 K/W、热容 J/K；温差 K 与 °C 等值 |
| 比例与概率 | 内部用 0..1，显示可用 %；利用率必须说明分子、分母、时间窗口、资源范围 |
| 证据 | 参数值附来源/版本、组织、精度、PVT、访问模式和统计边界。未知值留空或给有依据的区间，不填 0；这里不要求实现新的元数据框架 |
| 所有权 | 同一物理资源只计一次；摘要模型和内部细模型择一计量。复合 chip/die/core 的名称不能替代成员清单 |

## 2 工作量与数值语义

归属：训练/推理场景由 [trainingArch](trainingArch/README.md) / [inferArch](inferArch/README.md) 组织；任务语义在 [workloads](workloads/docs/design.md)，布局和分块在 [compiler](compiler/docs/design.md)，chipmodel 接收映射后的操作、数据和资源需求。详见[工作量与数值规则](docs/methods/workload_and_numeric_semantics.md)。

| 参数 / 专业术语 | 单位 | 关键关系与使用条件 |
| --- | --- | --- |
| 设：操作类型 Operator、张量形状 Tensor Shape | 枚举；element/axis | GEMM A[M,K]×B[K,N]：工作量 MNK MAC；若一乘一加计 2 op，则为 2MNK op。偏置、激活、归约等另计 |
| 设：批量 Batch、序列长度 Sequence Length、并发 Concurrency | sample、token、request | 分开记录 microbatch/global batch、有效长度/填充长度、到达分布；并发请求数不等于一次 kernel 的 batch |
| 设：数值格式 Numeric Format、操作数/累加器/输出精度 | 格式；bit/element | FP16/BF16/FP8/FP4/INT8/INT4 等须指定格式；指数、尾数、符号、累加精度和支持操作不能仅由 bit 数推断 |
| 设：量化 Quantization、舍入 Rounding、溢出 Overflow | scale、zero-point；枚举 | 仿射量化 x≈scale·(q−zero_point)；scale 的量纲随 x。声明 per-tensor/channel/group、饱和/回绕、NaN/Inf/subnormal 规则 |
| 设/观：稀疏结构 Sparsity、非零数 nnz | 比例、element、block shape | 稀疏率=1−nnz/N；有效工作和流量还受索引/元数据、负载不均、跳零能力影响。不能统一乘一个稀疏率 |
| 设：布局 Layout、步长 Stride、对齐 Alignment、分块 Tile | B/stride、B、element/axis | 地址=base+Σ index_i·stride_i；声明 stride 是 B 还是 element。边缘 tile、padding、swizzle 会改变物理访问 |
| 推/观：工作集 Working Set、活跃数据 Live Data | B | 紧密打包 N 个 b-bit 元素需 ceil(Nb/8) B；实际按各对象的行/块对齐后求和，再加 scale/index/metadata |
| 推/观：数据流 Dataflow、复用 Reuse、流量 Traffic | 策略、次、B/边界 | WS/OS/RS 表示某层数据驻留与循环映射；复用因子必须绑定张量和层级。Row-stationary 不能直接等同于 DRAM row-buffer 命中 |
| 设：依赖 DAG、状态生命周期 Lifetime、同步点 | task、s；关系 | 定义谁生产/消费/释放数据，输出何时可见；训练保存激活、CIM 权重驻留与 KV 追加均会改变峰值容量 |
| 推：计算强度 Arithmetic Intensity I、机器平衡点 Machine Balance | op/B | I=该阶段工作量 O/指定边界流量 D；I*=P_peak/B_peak。Roofline 上界 P≤min(P_peak,B_peak·I)，要求统计口径一致 [R1] |

最关心：完整工作量 O、各边界实际流量 D、峰值活跃容量、数值验收目标。Roofline 用于筛选瓶颈；依赖、小批次启动、队列、通信和资源共享仍可能进一步限制性能。

## 3 计算与控制资源

### 3.1 通用执行单元

归属：[CPU](chipmodel/compute/cpu/UNITS.md)、[GPU](chipmodel/compute/gpu/UNITS.md)、[NPU](chipmodel/compute/npu/UNITS.md)。MAC/ALU/FPU/向量/SFU/归约等先描述独立行为，再决定是否拆类。

| 参数 / 专业术语 | 单位 | 关键关系与使用条件 |
| --- | --- | --- |
| 设：操作集合 Operation Set、执行单元数、lane 数 P | 枚举；unit、lane | 加减乘除、exp/log/reciprocal、比较、归约、格式转换分别声明能力；SFU 近似精度和支持范围显式给出 |
| 标/设：单项延迟 Latency L、发起间隔 Initiation Interval II | cycle/item、cycle/issue | L 决定完成时间，II 决定连续发起能力；流水深度不直接等于 L 或 II；参数需绑定操作/精度/PVT |
| 推：空闲流水线批次完成时间 | cycle、s | G=ceil(W/P)，W>0 时 C=L+(G−1)II，W=0 时 C=0；T=C/f。要求等价 lane、供数充足、在途容量足够、无背压 |
| 推：峰值吞吐 Peak Throughput | item/s、op/s | 等价 lane 的服务峰值 P·f/II；若每 item 含 k 个所定义的 op，则再乘 k。总峰值只对可同时工作的独立单元求和 |
| 设/标：向量宽度 Vector Width、有效向量长度、掩码 | lane、element、bit | 最大 lane 数与本次活跃 lane 数分开；SIMD 指令宽度、标量位宽和寄存器宽度不是同一量 |
| 设/标：脉动阵列 Systolic Array、PE 网格、注入与归约 | row×column、element/cycle、cycle | 时间由映射、PE 的 L/II、边缘供数、传播、填充/排空及 tile 边界决定；R×C 不能直接推导任意矩阵的实际 MAC/cycle |
| 设/标：累加器 Accumulator、归约树 Reduction Tree | bit、input、level、cycle | 非负整数 K 项乘积需容纳 K·x_max·w_max；unsigned 位宽≥ceil(log2(K·x_max·w_max+1))。有符号/浮点用各自范围与舍入规则 |
| 观：执行利用率、形状利用率、供数/依赖停顿 | 比例、cycle | 分开统计实际执行/可服务工作、padding 浪费、等待原因；不能用一个“利用率”同时修正容量、带宽和能耗 |

### 3.2 处理器内部与硬件命令

| 参数 / 专业术语 | 单位 | 关键关系与使用条件 |
| --- | --- | --- |
| 设：ISA 与命令语义、Instruction Format | 枚举；bit/instruction | opcode、operand/address、dtype/shape、依赖、完成/异常语义明确；一个命令可展开为多项微操作，指令长度不等于数据位宽 |
| 设/标：取指/译码/发射/退休宽度 | instruction/cycle 或 µop/cycle | 稳态服务受最窄相关阶段限制，但宏指令与 µop 转换不可省略；IPC 是观测结果，不直接等于 issue width |
| 设：ROB、Issue Queue、LSQ、物理寄存器、MSHR | entry、register、B | 决定在途状态与延迟隐藏；分支恢复、重命名、旁路、顺序/乱序按研究需要启用 |
| 标/观：分支误预测率、恢复代价、指令组合 | 比例、cycle、比例/操作类 | 粗估额外工作需同时知道分支频度；流水重叠和依赖存在时不能把所有 penalty 简单相加 |
| 设/推：GPU SM/CU、warp/wave、驻留 block/warp | unit、thread/warp、block、warp | 驻留上限受寄存器、共享存储、线程/warp/block 限额及分配粒度共同限制；占用率 Occupancy=活跃 warp/支持上限，不等于算力利用率 [R7] |
| 设/观：SIMT 分歧、合并访存 Coalescing、共享存储 bank 冲突 | active lane 比例、transaction、cycle | 由执行掩码和地址分布决定；相同 occupancy 可能产生很不同的吞吐 |
| 设/标：命令队列、发射/完成宽度、同步状态 | entry、command/cycle、cycle | 小任务可能受 launch/dispatch/completion 限制；硬件队列归 control，软件调度归 runtime |

TMA 在本仓库表示可配置的张量搬运能力；TSU 保留为待定义操作集合的控制单元名，不指定厂商缩写或隐含功能。只有具体命令/状态明确后才建立行为模型。

## 4 CIM 阵列与混合信号外围

归属：[arrays](chipmodel/compute/cim/arrays/UNITS.md)、[encoding](chipmodel/compute/cim/encoding/UNITS.md)、[periphery](chipmodel/compute/cim/periphery/UNITS.md)。模拟电导、数字位运算、电荷域、时间域机制分别定义；数字 CIM 不必有 ADC/DAC。

| 参数 / 专业术语 | 单位 | 关键关系与使用条件 |
| --- | --- | --- |
| 设：物理阵列行列、子阵列数、激活行数 | row、column、array | 物理容量=Σ(rows·columns·cell_bits) bit；一次有效行数≤物理行数。坏单元、参考列、冗余和符号编码另占容量 |
| 设：cell bits、权重幅度位宽、差分编码、输入相位 | bit/cell、bit/weight、branch、phase | 位切片数 s=ceil(b_weight_magnitude/b_cell)；差分支路 d∈{1,2}。当前逐 bit 输入模型 p=b_input；其他编码须重定义 p |
| 推：逻辑工作与物理动作数 | MAC、cell-evaluation、conversion | 当前完整 R×C MatVec：逻辑 RC MAC，cell 动作 RC·s·d·p；ADC 转换 C·s·p·d_adc。模拟求差时 d_adc=1，逐支路转换时 d_adc=d；行分块/边缘利用另算 |
| 标/设：电导矩阵 Conductance G、输入电压 V | S、V | 理想电流求和 I_j=Σ_i G_ij·V_i [A]；差分用 G+−G−。线性/非扰动读取条件需校准，电导不能与量化整数权重直接互换 |
| 标：互连寄生、驱动/感测能力、读出建立时间 | Ω、F、A、s | WL/BL 电阻电容、selector/access device、sense amplifier、积分器决定阵列规模、压降、读出范围与时间；不是额外逻辑 MAC |
| 标/设：TIA 跨阻、偏置、输出范围 | Ω、V | V_out=V_offset+I·R_TIA；R_TIA 可带符号以表达反相。限幅、噪声与带宽不能由此理想式自动得到 |
| 设/标：ADC 分辨率 N、量程、lane、L/II | bit、V、lane、cycle | K=2^N，ΔV=(V_max−V_min)/K；当前均匀 offset-binary ADC 按 bin 量化并限到 0..K−1，V_max 归最高码。批次时间按第 3 节 |
| 设/标：DAC 位数、输出范围、建立与负载 | bit、V、s、F/A | 当前端点对齐 DAC：V(q)=V_min+q·(V_max−V_min)/(2^N−1)。以参考电压/2^N 定义 LSB 的器件需采用其传递函数，不能混用 |
| 设/标：MUX 共享、sample/hold、采样与保持 | column/ADC、sample、s、V/s | 共享增加读出次数；保持容量≥尚未消费样本数，样本年龄≤有效保持时间；采样、settling、转换和切换的重叠关系显式给出 |
| 标：INL/DNL、噪声、SNDR/SINAD、ENOB | LSB、V_rms、dB、bit | 满量程正弦常用 ENOB=(SINAD−1.76)/6.02；非满量程需按测试幅度修正，并记录输入频率/带宽。理想量化 σ=Δ/√12 依赖均匀误差假设，不是完整 CIM 误差模型 [R6] |
| 设/标：数字移位累加、符号恢复、re-quantization | bit、shift、operation、cycle | 输出=Σ_k partial_k·2^shift_k，再按声明的溢出/舍入策略处理；中途截断与最终截断不等价 |
| 标：program/verify、读噪声、变异、漂移、校准 | pulse、s、J、S；分布参数 | 器件间/同器件逐次变化分开；写入失败/重试、漂移随时间温度、校准开销按技术启用。训练权重更新必须计写代价与寿命 |

最关心：有效逻辑矩阵、编码放大、活跃行数、列输出动态范围、ADC 服务率/精度、外围共享、数据驻留和写入成本。阵列面积与能耗必须说明是否含外围；参考 [R10] 的分层建模边界，不直接移植其预测参数。

## 5 存储层次与介质

层级、管理方式、介质、接口、物理位置是独立维度。例如 L2 是层级标签，cache 是管理方式，SRAM 是介质；DDR/HBM 是带具体组织与接口约束的 DRAM 技术族。L0/L1/L2 不预设容量、介质或一致性范围。

### 5.1 所有存储资源先填的参数

| 参数 / 专业术语 | 单位 | 关键关系与使用条件 |
| --- | --- | --- |
| 设：层级、管理方式、访问语义、物理所有者 | 枚举、resource ID | RF/SPM/cache/main memory/storage 分开；读写、原子、显式搬运、只读、就地计算是能力；die/package/node 是实例放置 |
| 设/推：逻辑容量、物理容量、预留与元数据 | B、bit | 逻辑 payload、ECC、tag、spare、坏块预留分别记账；可用容量按实际组织算，不能从物理 bit 数无条件直除 |
| 设：bank、端口、字宽、读写/擦除粒度 | bank、port、bit、B/action | 独立读/写端口与共用读写端口分开；端口存在不表示 bank 冲突或总线争用消失 |
| 设/标：读/写延迟、最小发起间隔、在途数 | s/cycle、request | 读延迟不等于访问周期；深流水可 L>II；在途容量和请求大小决定能否隐藏延迟 |
| 标/推/观：读/写/合计带宽 | B/s | 指明 payload/wire、方向、共享链路和窗口；持续带宽由访问模式和控制器决定，不是接口峰值的固定比例 |
| 标：读/写/维护动作能量、静态/低功耗功率 | J/action、W、s | 每次动作大小与组织明确；唤醒、刷新、program/erase 单独描述，不能重复叠加已包含的待机或外围能耗 |
| 设/标：ECC、冗余、保留、维护机制 | bit/codeword、error/codeword、s | 记录码字、有效数据位、纠错能力、额外访问/延迟；on-die ECC 不自动提供端到端链路保护 |

### 5.2 RF、SRAM、SPM、buffer 与 cache

归属：[SRAM](chipmodel/memory/sram/UNITS.md)、[buffer/cache](chipmodel/memory/UNITS.md)。

| 对象 / 专业术语 | 核心参数与单位 | 关键关系与边界 |
| --- | --- | --- |
| SRAM bank / Register File | bank 数、word/bank、bit/word、R/W/RW port、读写 L/II | payload 容量=banks·words_per_bank·word_bits/8 B；RF 也可由其他电路实现，不把它强制视作一种 SRAM 宏 |
| SRAM 外围 | 行列译码、WL/BL、预充、sense amp、write driver、MUX；s/J/mm² | 宏级成本若已覆盖外围，不再加 cell/decoder 等细项；bank 组织和多端口实现会改变面积与时序 |
| SRAM 物理条件（按需） | 6T/8T/10T；cell area µm²；SNM/Vmin/retention V；leakage A | 6T 一般为交叉耦合锁存结构，不是时钟触发器；端口数不能单由晶体管数推断。SNM、assist、bitline swing 用于可行性/成本校准 |
| Scratchpad / 显式缓冲 | 容量 B、bank mapping、allocation/alignment B、生命周期 | 没有 cache hit/miss 语义；地址冲突、生命周期重叠和 DMA 访问仍需描述 |
| FIFO / ping-pong / 多缓冲 | slot 数、B/slot、读写端口、生产/消费时刻 | 相同槽的容量=slot_count·slot_bytes；双缓冲要确有两份空间。只有资源可并行、依赖满足时，稳态每 tile 时间才可能接近 max(T_load,T_compute,T_store) |
| Cache 几何 | sets、ways、line_bytes、address_bits、metadata bit/line | payload=sets·ways·line_bytes；在 2 的幂且相应地址索引假设下，tag_bits=address_bits−log2(sets)−log2(line_bytes)；tag/ECC 不含在 payload 内 |
| Cache 行为（按需） | replacement、write-through/back、write-allocate、prefetch；MSHR/writeback entry | 缺失率、预取准确率/覆盖率、脏回写和伪共享是负载相关结果；必须计新增流量及 MSHR/端口竞争 |
| AMAT（分析指标） | hit time、miss rate、增量 miss penalty | 单层阻塞近似 AMAT=t_hit+miss_rate·penalty；多层按局部缺失率递推。并行访存的程序时间不等于访问数×AMAT |
| CAM / TCAM（按需） | entry、key bit、mask、search port、search L/II、J/search | 属于按内容匹配的结构/行为；底层可有不同实现，不简单归为“SRAM 类型” |

### 5.3 DDR / LPDDR / GDDR / HBM / eDRAM

归属：[DRAM 组织](chipmodel/memory/dram/UNITS.md)、[控制器](chipmodel/memory/controllers/UNITS.md)。时序术语交叉核对 [R2]；具体合法值必须来自相应器件/标准版本。

| 参数 / 专业术语 | 单位 | 关键关系与使用条件 |
| --- | --- | --- |
| 设：channel、subchannel/pseudo-channel、rank、bank group/bank、row/column | 各层计数 | Rank 是共享命令/数据组织的一组器件，不是列；每 channel 的独立资源和共享部分须声明。当前代码的 banks_per_rank 已含 bank-group 展开 |
| 推：组织容量 | B | 当前等宽 payload 组织 C=channels·ranks·banks·rows·columns·payload_width_bits/8；columns 是每行 payload-width 位置数，不是 burst 数。器件级 x4/x8/x16 需先聚合成相应接口 |
| 设/标：Data Rate、有效数据位宽、Burst Length BL | MT/s、bit/transfer、transfer/burst | B_peak=Σchannel(rate·10⁶·payload_bits/8)；burst_bytes=BL·payload_bits/8。MT/s 已计 DDR 边沿，不能再乘 2；共享总线的 rank 数不乘带宽 |
| 标：tCK、CL/RL、CWL/WL | s 或明确的 CK/WCK cycle | 固定时钟域内 t=cycles·tCK；不同代际命令/数据时钟关系与模式不同，不能统一设成 data_rate/2 |
| 标：tRCD、tCL、tRP | s/cycle | tRCD：ACT→RD/WR 的相关最小间隔；tCL：RD→首数据；tRP：PRE→下一 ACT。读写 tRCD 可不同 |
| 标：tRAS、tRC | s/cycle | tRAS：同 bank ACT→PRE 最小活跃时间；tRC：同 bank ACT→ACT 最小间隔。需同时满足 tRAS/tRP 等约束，不把 tRAS 当单次读延迟 |
| 标：tCCD_S/L、tRRD_S/L、tFAW | s/cycle | 分别限制列命令间隔、不同 bank 激活间隔、滚动四激活窗口；S/L 的 bank-group 适用关系按器件定义 |
| 标：tWR、tRTP、tWTR、tRTW | s/cycle | 写恢复、读到预充、写读/读写切换；计时起点可能涉及数据尾与命令，不能仅靠名称套统一加法 |
| 标：tRFC、tREFI、刷新模式 | s、枚举 | tRFC 为相应 refresh 操作的忙/恢复时间，tREFI 为刷新间隔；全 bank/每 bank、温度和刷新策略会改变阻塞与功耗 |
| 设/观：地址映射、页策略、行状态 | 枚举；hit/closed/conflict 比例 | row-buffer 命中依赖地址流、调度和初态；DRAM 激活整行到感放，外部读写按列/burst/掩码进行，并非每次写完整行 |
| 设/标：请求队列、调度、读写切换、refresh/powerdown 控制 | entry、策略、s | bank-level/queue-level 并行、tFAW 和总线周转共同决定持续带宽；刷新与低功耗退出不是常数“效率损失” |
| 设/标：PHY、训练、ODT、VDD/VDDQ、电流 profile | bit、V、A、s | 架构层优先使用有效速率、额外时延、能量与合法模式；DQS、ZQ、leveling、眼图等细节仅在 PHY/信号可行性研究中展开 |
| 设/标：HBM stacks、memory dies、channels、pseudo-channels、TSV | stack、die、channel、bit、µm | 按代际/模式记录数据位宽和共享命令资源；HBM4 产品已采用 2048-bit 数据接口，不能把 HBM 固定为 1024 bit [R3]。堆叠层数增加不自动倍增外部带宽 |
| 设/标：LPDDR/GDDR/eDRAM 特性 | 版本、clock ratio、低功耗模式、refresh、s/J | LPDDR 关注低功耗状态及退出；GDDR 的调制/编码/速率依版本；eDRAM 仍需保持/刷新模型。不能只换技术标签而保留全部时序 |

隔离读的简化检查：当起点 PRE/ACT 已合法、无刷新/其他请求时，首数据延迟依次为 hit：tCL；closed：tRCD+tCL；conflict：tRP+tRCD+tCL。整次请求还需 burst 序列时间；该式不替代完整命令合法性或控制器排队。

带宽手算：独立 64-bit payload 接口、5600 MT/s → 44.8×10⁹ B/s=44.8 GB/s。增加共享该接口的 rank 可能改善可调度性和容量，接口峰值仍为 44.8 GB/s。

### 5.4 NOR / NAND / HBF

归属：[Flash](chipmodel/memory/flash/UNITS.md)；控制器、ECC/映射和物理放置分别组合。NAND 裸介质的 ONFI/Toggle DDR 与主机 NVMe、UFS/eMMC/SD 处于不同边界，不能作为同一层互换接口。

| 对象 / 专业术语 | 核心参数与单位 | 关键关系与边界 |
| --- | --- | --- |
| NOR 组织与访问 | capacity B、program word/page B、erase sector/block B | 随机字节寻址能力不等于任意字节擦除；program/erase 受具体对齐、位状态转换和次数限制。SPI/parallel、SDR/DTR、dummy cycle 分开 |
| NOR 命令与 XIP | address bit、data lane、clock Hz、command/dummy cycle、read/program/erase s | XIP=Execute In Place（就地执行），可经控制器从片外 NOR 取指；CFI=Common Flash Interface 查询规范，不是另一种物理总线。具体 page/sector 例见 [R5] |
| NAND cell 与组织 | bits/cell、layer、plane、LUN/die、block/plane、page/block、B/page | SLC/MLC/TLC/QLC/PLC 的编码位数影响阈值窗口、成本与可靠性，但不决定通用时序。LUN、die、plane 按器件定义，不能总是逐层相乘 |
| NAND 容量 | data B/page、spare/OOB B/page、页/块、块数、预留比例 | raw payload=数据页大小×数据页数；OOB、ECC 和坏块/超额预留分别记账。当前几何模型用其明确的层次，不自动推断 FTL 用户容量 |
| NAND 读/编程/擦除 | tR、tPROG、tBERS [s]；transfer rate [B/s] | 页从 array 读到 page buffer 后再做数据输出；编程含输入与内部 program，擦除按 block。三类延迟独立取值，不能共用一个“10–100 µs”范围；器件也可能采用 tRD/tPP/tBE 等命名 [R11] |
| NAND 并行与粒度 | page buffer、cache read/program、multi-plane、interleave、queue | 页是核心阵列操作单位；外部列读取/部分页传输和部分编程限制依器件。共享 bus、LUN 忙状态、页/plane 约束决定是否可并行 |
| NAND 控制器（按需） | ECC codeword/latency、retry、FTL mapping、GC、wear leveling | WAF=介质实际 program bytes/主机逻辑 write bytes；声明窗口和是否含元数据/搬迁。GC、TRIM、掉电保护属于相应控制/设备边界，不是 cell 参数 |
| Flash 可靠性 | P/E cycle、retention s、raw BER、uncorrectable error rate、坏块数 | 耐久与保持绑定产品、温度、已循环次数、编程模式/ECC 条件；读/编程干扰、read retry 增加误差或访问成本；不预置统一寿命范围 |
| HBF 方案 | Flash profile、通道/堆叠、容量、粒度、带宽、控制时延、功耗 | 按明确来源的高带宽 Flash 方案建模；不从名称推断统一命令、HBM 级随机访问、耐久或直接 CIM 能力 |

### 5.5 其他介质：只保留会影响架构的参数

这些是可选技术 profile，不要求预先建立所有器件的类或电路仿真器。没有写入/保持/成本依据时，先标未知。

| 介质 / 专业术语 | 架构层优先参数 | 器件级条件参数与边界 |
| --- | --- | --- |
| MRAM（STT/SOT 等） | 容量/粒度、读写 L/II、J/access、retention、write endurance、错误率 | MTJ/TMR、switching current [A]、热稳定因子 Δ [1]、读裕度；不同写入机制单独特征化 |
| ReRAM/RRAM | 电导状态/可用精度、SET/RESET/verify 延迟与能量、耐久/保持/变异 | forming、compliance current [A]、读扰动、selector、漂移；不假定所有 RRAM 都由同一种 filament 机制实现 |
| PCM | 读/SET/RESET 时延能量、状态分布、漂移/保持、耐久 | 电阻漂移可在已标定区间用 R(t)=R(t0)·(t/t0)^ν，t≥t0>0；不是所有状态/器件通用律。3D XPoint 是产品技术名，不等同全部 PCM |
| FeRAM / FeFET | 读写时延能量、保持、耐久、错误率 | 极化/阈值状态、矫顽场、材料/结构需明确；传统电容型 FeRAM 的破坏性读及恢复不能推广到全部铁电存储 |
| ROM / OTP / eFuse | 容量、读取 L/II/能量、编程次数与粒度 | 区分 mask ROM 与一次性可编程机制；只在启动/配置或权重存储路径相关时启用 |

SRAM/DRAM 不使用 Flash 的 P/E 寿命指标；“刷新次数≈擦写耐久”“SRAM 耐久无限/10¹⁵+”不能作为模型参数。普通 DRAM 常见 1T1C，6T/8T/10T 是 SRAM 单元类型示例，不是全部易失存储的通用结构。

## 6 互连、数据搬运与同步

片内协议/NoC、D2D 在 [interconnect](chipmodel/interconnect/UNITS.md)，DMA/TMA 在 [control](chipmodel/control/UNITS.md)；板级 PCIe/CXL/NIC 组合在 systemmodel，节点网络在 clustermodel。硬件逻辑类可复用，实例归属和链路范围独立声明。

| 参数 / 专业术语 | 单位 | 关键关系与使用条件 |
| --- | --- | --- |
| 设：拓扑 Topology、端点、路由、独立方向 | node、edge、port、hop；枚举 | bus/ring/mesh/torus/tree/fat-tree/crossbar 描述连接；CIM 电导 crossbar 与网络交换 crossbar 是不同资源 |
| 推/观：直径、平均跳数、二分/割带宽 | hop、B/s | 平均跳数需流量权重；割带宽按跨割独立链路的方向与容量相加。端点 NIC、交换机和上行超售仍会限制可用吞吐 |
| 设/标：链路宽度、lane 数、线路速率、调制/编码 | bit/beat、lane、bit/s/lane、symbol/s | 先区分 parallel beat 与 serial lane。若已给实际 line bit/s，则只乘 lane 数；若从 baud 推导，再按调制有效 bit/symbol 与编码/FEC 处理 |
| 推：线路与 payload 带宽 | B/s | B_wire=Σlane bit_rate/8；B_payload≤B_wire·η_coding·η_packet，η_packet=payload/(payload+header+trailer+padding)。效率项不能重复覆盖同一开销 |
| 设：packet/flit/beat、最大 payload、对齐 | B/packet、B/flit、B/beat | Packet 为协议包，flit 为流控单位，beat 为一次总线传输；小包和尾部填充须取整。广播/多播按实际复制位置计链路字节 |
| 标/观：序列化、传播、router/bridge、仲裁/排队时延 | s、cycle/domain | 序列化时间=本段传输位数/本段线路位率；wormhole/cut-through/store-and-forward 的跨跳重叠不同，不能都按 hop×完整 packet 时间 |
| 推：无争用 NoC 路径时间 | cycle、s | 当前同构路径 H hop、F flit：C=H·(L_router+L_link)+(F−1)II；头尾计时约定、相同链路服务率、无背压为前提 |
| 设/标：buffer、VC、credit、在途上限 | flit/VC、VC、credit、B/request | 长时延链路若靠 credit 滑窗供给，维持目标速率通常要求可用窗口≥B_target·T_credit_roundtrip；还需计粒度和返回规则，BDP 不保证无拥塞 |
| 设：仲裁/流控/路由/QoS | 策略；weight、B/s、s | RR/priority、credit/ready-valid、虚拟通道隔离、路由/死锁约束显式配置。带宽/延迟保证须有流量约束和调度依据 |
| 标/观：误码、重传、FEC、链路功耗 | BER、packet error、J/bit、W、s | 原始 BER 不能直接等于丢包概率；重试及 FEC 影响开销与尾延迟。重试次数、独立/相关错误假设要明确 |
| 设/标：D2D、UCIe/BoW/AIB、SerDes | 版本/profile、lane、B/s、s、J/bit | 使用具体协议模式、编码、速率与封装条件；不能把某代 PCIe/UCIe 的固定开销复制到其他代际 |
| 设/标：DMA、scatter/gather、TMA | channel、descriptor、B/burst、在途 request、启动 s | 独立服务摘要 T≈T_start+D/B_service；显式拆出源存储/链路/目的存储后，应按依赖与共享资源组合，避免再计一遍摘要时间 |
| 设：张量地址生成、layout transform | shape、stride B、tile、swizzle、边界策略 | 描述源/目标、padding、转置、越界行为；逻辑字节、访存 transaction 与总线传输字节分别统计 |
| 设/标：MMU/TLB/IOMMU、页表遍历（按需） | address bit、page B、entry、walker、s | TLB reach 的简单形式=entry·page_bytes；多页大小/关联度另算。翻译 miss 产生额外访问，DMA 地址空间与权限边界明确 |
| 设：一致性、内存序、原子与 barrier（按需） | 协议、scope、ordering；entry、s | Coherence 管同址副本，Consistency/Ordering 管访存可见顺序；directory/snoop/atomic 会增加流量与串行依赖。Publish-subscribe 不作为通用缓存一致性参数 |

最关心：每条边的实际流量、有效带宽、在途窗口、共享瓶颈、完成时的数据可见性。GPIO/UART/I2C 等只有出现在研究路径上才加入速率/事务开销模型；通常不影响主要 AI 数据路径。

## 7 时钟、电源、封装、热与成本

### 7.1 时间、能耗与物理可行性

| 参数 / 专业术语 | 单位 | 关键关系与使用条件 |
| --- | --- | --- |
| 设/标：时钟域、目标/可达频率、CDC | Hz、s、cycle/domain | 不同域 cycle 先换为时间；CDC/FIFO 的采样相位和同步级引入延迟。时钟抖动/偏斜/PLL 锁定仅在影响时序裕量或切换时展开 |
| 设/标：power domain、DVFS、clock/power gating | V、Hz、state、s、J | V/f 必须是已知合法工作点或明确假设；切换/唤醒时间能量、状态保持容量与泄漏分别计入 |
| 标：动态动作能量与背景功率 | J/action、W | E_total=Σn_a·E_a+∫P_background(t)dt；动作能量若已含背景，要先统一口径，不能重复计数 |
| 标/推：开关、短路与漏电功耗 | W、F、V、A | 简化 P_switch=Σα_01·C·V²·f，其中 α_01 是每周期 0→1 活动率；P_leak=V·I_leak。不能同时把 switching 再作为已含它的 dynamic 的独立加项 |
| 设/观：power budget、峰值/平均功率、TDP | W；测量窗口 s | P_avg=E_window/T_window；峰值需窗口/采样定义。TDP 是产品热设计约定，不直接等于实测平均/瞬时峰值功率 |
| 设/标：供电限制、IR drop、电流密度 | V、Ω、A、A/mm² | 一阶 DC 压降 ΔV≈IR；droop、电源完整性和 Vmin 决定合法频率/错误边界。详细电网/EM 分析作为特征化输入 |
| 设/标：工艺 profile、PVT、工艺角/OCV | 工艺/库/角标识；V、°C；分布 | Process Node 名称不等于物理 Gate Length；FinFET/GAA 是器件类型，不能仅由“nm”标签推导时延/面积/能耗缩放 |
| 设/标/推：Die/Macro 面积、几何与布线余量 | mm²、mm、µm、layer | A_die=width·height；宏面积求和需再考虑互连、空白/布线、时钟电源/控制开销。晶体管数或 cell area 不能单独给出可布通 die 面积 |
| 设/标：2.5D/3D、chiplet、interposer/bridge、TSV/bump/bond | die、layer、µm pitch、link/mm、mm² | 几何包含/重叠、边缘与布线通道、连接数量、堆叠顺序约束配置；连线带宽/能量归实际链路，面积归实际物理对象 |
| 标/设：热阻 Rθ、热容 Cθ、环境/结温 | K/W、J/K、°C、W/mm² | 一阶 Cθ·dT/dt=P−(T−T_a)/Rθ；τ=RθCθ；恒功率稳态 T∞=T_a+P·Rθ。θJC、θJA 的参考边界不同，不可混用 |
| 推/观：热瞬态、热点、节流 | °C、s、Hz | 恒功率单节点 T(t)=T∞+(T0−T∞)exp(−t/τ)；3D 邻层耦合/空间热点需要多节点或校准模型，平均功率密度不能证明无热点 |
| 标/观：可靠性与错误（按需） | FIT、error/bit/access、s、失败概率 | ECC/重试/备用资源/老化影响有效工作和寿命时才展开；失败率要注明每 bit、器件还是系统以及时间/温度条件，不能把 MTBF 当无故障保证 |

归属：[geometry](chipmodel/packaging/geometry/UNITS.md)、[thermal](chipmodel/packaging/thermal/UNITS.md)、costmodel；clock/power 控制行为在 control。PDK/SPICE、RTL/STA、宏编译器、实测提供条件数据，当前参数公式模型不能替代这些物理校准。

### 7.2 顶层 PPA 与经济指标

| 指标 / 专业术语 | 单位 | 定义与比较条件 |
| --- | --- | --- |
| 性能 Performance | task/s、token/s、op/s、s/task | 按相同任务、精度/质量和 SLO 比较，标明延迟还是吞吐目标；不把不同精度 TOPS 直接排序 |
| 能效 Performance per Watt | task/J、token/J、op/J | 稳态且窗口一致时 throughput/P_avg；单任务直接用 work/E_task。芯片/板卡/节点/集群边界必须一致 |
| 面积效率 Area Efficiency | task/s/mm²、op/s/mm² | throughput/A；声明 die、macro 或 package 面积，CIM 是否含外围；相同 workload 与精度才有可比性 |
| 成本效率 Performance per Dollar | (task/s)/货币 | throughput/指定购置成本；不同于摊销后的货币/task，也不同于每峰值 FLOP 的采购价格 |
| 制造与集成成本（按需） | 货币/wafer、货币/die、yield [0..1] | 简化良 die 成本≈wafer_cost/(gross_dies·die_yield)；边缘损失、测试、封装、组装良率和 NRE 按成本模型补充，不把独立性当默认事实 |
| 摊销与 TCO（按需） | 货币、h、货币/kWh | 单位任务成本=(同窗口资本摊销+能耗+运维等成本)/合格完成任务数；NRE 分摊用明确产量，能源费用用实际功耗/运行时间 |
| PPA / 延迟-吞吐权衡 | 多目标集合 | 先满足质量、容量、热和延迟约束，再比较 Pareto 候选；不默认把 W、s、mm²、货币任意加权成唯一分数 |

掩膜/晶圆尺寸/晶体管密度/良率是成本或实现可行性输入，不是每次架构仿真的必填项。“暗硅”“内存墙”“功耗墙”是现象描述，应由相应资源/功率约束表达。

## 8 AI 训练/推理的资源账本与指标

场景入口分别为 [trainingArch](trainingArch/README.md) 与 [inferArch](inferArch/README.md)，其参数导航见 [训练 UNITS](trainingArch/UNITS.md) / [推理 UNITS](inferArch/UNITS.md)。目前两者是文档入口，未实现独立分析器。它们组织场景假设、资源账本与指标，复用 workloads/compiler/runtime 的职责以及公共硬件模型，不复制底层资源参数。

### 8.1 训练

| 参数 / 专业术语 | 单位 | 关键关系与使用条件 |
| --- | --- | --- |
| 参数量、层/hidden/head/expert 规模、序列与 batch | parameter、layer、element、token、sample | 总参数与每 token 激活参数分开；MoE 的 top-k、expert 分布、capacity/padding/丢弃策略影响工作量和路由负载 |
| Forward / Backward / Optimizer 工作 | FLOP/op、B、action/step | 逐算子计工作量与流量；常用“训练≈若干倍前向”只作明确结构下近似，不覆盖任意 attention、稀疏、重计算和优化器 |
| 权重、梯度、master weights、optimizer states | B/rank | 未分片的 P 参数混合精度 Adam 示例：M=P·(b_w+b_g+b_master+b_m+b_v)/8；是否存在 master、m/v 及其精度由算法定义 |
| 激活、临时 workspace、通信 buffer、峰值显存 | B/rank、s/lifetime | M_peak=max_t Σ活跃对象 allocated_bytes(t)，再计未包含在对象中的固定预留；不能把每类对象各自峰值简单相加当作同时峰值 |
| 激活重计算 Checkpointing / Recomputation | 保存 B、新增 FLOP、B/step | 用算力与访存交换驻留容量；algorithmic activation checkpoint 与故障恢复检查点不同，若研究恢复再计持久化流量 |
| DP/TP/PP/EP/CP、microbatch、梯度累积 | rank、stage、microbatch、step | 每个参数/激活/KV/优化器对象分别标 sharded/replicated/owner；不能把全部内存统一除以 GPU 数。流水 bubble 与 stage 不平衡依具体调度 |
| All-Reduce / All-Gather / Reduce-Scatter / All-to-All | B/collective、rank、s | 明确参与组、每 rank 输入/输出和链路字节。理想 p-rank ring all-reduce 每 rank 发送 2(p−1)D/p B，D 是每 rank 原始消息大小 |
| 集合通信时间、计算通信重叠 | s、比例 | 无争用等速 ring 近似 T≈2(p−1)α+2(p−1)D/(pB)，α 为每轮固定开销；忽略本地 reduce 等额外成本。真实映射、端口共享和依赖限制重叠 |
| MFU / Hardware FLOPs Utilization | 比例 | MFU=同阶段有用模型 FLOPs/(T·所选硬件峰值)；重计算不计入有用模型工作。HFU 需定义实际执行 FLOPs 口径，不能把两者混称 [R8] |
| 训练完成率与效率 | sample/s、token/s、s/step、J/step | 同时记录有效 token、padding、global batch、梯度累积与更新频率；step 的定义统一后比较 |

### 8.2 推理

| 参数 / 专业术语 | 单位 | 关键关系与使用条件 |
| --- | --- | --- |
| Prefill / Decode、请求长度、batch 与到达负载 | token、request、request/s、s | 分别记录 prompt/output/context 长度分布、活跃请求与调度批次；prefill 不必总是算力受限，decode 不必总是带宽受限 |
| 权重驻留、读取与量化 | B、bit/weight、B/token | 位宽缩减需加 scales/zero-points、解量化工作和对齐；每 token 读一次全部权重只是特定 batch/cache/映射下的近似 |
| KV cache 有效容量 | B/rank | 未分片、无量化元数据时：M_KV=Σ层lΣ请求r L_r·h_KV,l·(d_K,l·b_K,l+d_V,l·b_V,l)/8；相同 K/V 为常见 2·layers·ΣL_r·h_KV·d_head·b/8 |
| MHA / GQA / MQA、KV 精度 | query head、KV head、bit | KV 用 KV head 数，不是 query head 数；GQA 介于 MHA 与 MQA，MQA 可仅一个 KV head [R9]。TP 是否分片/复制由具体布局决定 |
| KV 物理分配、分页/前缀共享、淘汰 | token/block、B/page、refcount、B | 分页按 ceil(L/block_tokens) 分配，另计 metadata/scale/padding；共享页按唯一物理对象计容量，COW 和交换流量单独记 |
| KV 访问与 PD 分离 | B/step、B/request、s | 全注意力需访问有效上下文，window/sparse/复用会改变流量；PD 传输记录实际 KV payload、布局转换、同步与链路资源 |
| TTFT、TPOT、ITL | s/request、s/token | t_first−t_arrival 为所选观测边界的 TTFT；N_out>1 时 TPOT=(t_last−t_first)/(N_out−1)；ITL_i=t_i−t_(i−1)。单输出 token 的 TPOT 不定义 |
| 端到端、排队、P50/P99 | s；分位数 | 明确服务端/客户端时间戳和完成定义；token 流的最后 token 时间可作为一种终点。尾延迟需要请求/运行分布，不能从均值公式直接推出 |
| Throughput / Goodput、并发 | token/s、request/s、request | 声明输入/输出 token 及聚合/单请求口径；Goodput 只计满足指定质量/SLO 的完成量。稳态均值下 Little 定律 N=λ·W，不能用于直接推导 P99 |
| 投机解码、稀疏、融合等策略 | 接受率、draft token、FLOP、B | 必须计 draft/verify/reject 工作及数据复用变化；PTQ 是训练后量化，QAT 是量化感知训练，均不保证无精度损失 |
| Energy per Token / Cost per Token | J/output-token、货币/10⁶ token | E_token=指定窗口能量/有效输出 token；说明是否含 prefill、空闲、主机和网络。成本使用相同窗口、功耗与完成量 |

### 8.3 怎样判断系统瓶颈

先对每个阶段列出计算工作、每级数据流量、同时活跃容量、依赖、同步和功率约束，再判断瓶颈。训练/推理名称只能提示常见压力方向，不能代替这份账本。

理想稳态瓶颈可由资源工作量/服务率比较；有限批次的严格界还需说明初始可用服务与突发能力。[现有组合模型](chipmodel/composition/UNITS.md)使用供给包络 W(T)≤b+rT，给出 T≥max(0,(W−b)/r)，并与任务 DAG 关键路径下界取最大值。它不自动得到真实调度完成时间，也不把所有阶段时间无条件相加或取最大。

## 9 设计时的十项检查与首批路径

1. **任务完整吗？** 输出、精度、训练 step/prefill/decode、有效工作和质量目标已定义。
2. **资源边界明确吗？** 计算/存储/控制/互连有唯一所有者；局部台架的外部输入与输出能力明确。
3. **量纲一致吗？** bit/B、MT/s/Hz、不同域 cycle、MAC/op、有效/物理字节没有混算。
4. **容量可行吗？** 权重、激活、KV、部分和、元数据、在途和双缓冲的生命周期都能放下。
5. **服务能力够吗？** L、II、lane、bank、端口、队列、ADC 共享和链路窗口分别检查。
6. **数据路径完整吗？** 每次数据生成、读取、写入、移动、复制和归约都能找到资源与计量边界。
7. **时间关系成立吗？** 依赖、样本保持、可见性、刷新、唤醒和背压；重叠有条件，下界不是完成时间。
8. **物理取值有依据吗？** profile/PVT、精度、访问活动与来源一致；没有拼接互不兼容的最佳指标。
9. **误差与成本影响结论吗？** 不确定参数做敏感性检查；结果对 ADC 精度/写成本/热等敏感时再细化模型。
10. **复杂度值得吗？** 新参数改变哪个结果，有什么独立证据；先公式/纯函数，必要时加状态、事件或 RTL 校准。

首批 **CIM array + DAC/ADC + 缓冲** 按以下最小集合查表即可，不需要先搭完整 CPU/GPU/DDR 系统：

| 边界 | 最少要明确什么 | 可查的现有入口 |
| --- | --- | --- |
| 工作负载与编码 | MatVec 维度、输入/权重幅度位宽、符号、期望误差、位切片/输入相位 | [encoding](chipmodel/compute/cim/encoding/UNITS.md) |
| 阵列与电压/电流路径 | G/V 范围、行列/活跃行、差分、TIA 增益/偏置、各阶段服务时序 | [arrays](chipmodel/compute/cim/arrays/UNITS.md) |
| DAC/ADC 与读出 | 量化传递函数、量程、lane、L/II、共享、保持容量/有效期 | [periphery](chipmodel/compute/cim/periphery/UNITS.md) |
| 缓冲与数字结果 | 输入/权重/部分和/输出字节、槽/端口、累加/溢出、读写时刻 | [memory](chipmodel/memory/UNITS.md)、[encoding](chipmodel/compute/cim/encoding/UNITS.md) |
| 外部台架 | 数据是否预驻留、外部供数/接收限制、测量起止、时钟；能耗未知则不报告完整能效 | [系统级设计](chipmodel/docs/system_model_design.md)、[composition](chipmodel/composition/UNITS.md) |

当问题变成外存供数是否饱和时，再接 DDR/HBM/HBF 及其控制路径；当问题变成真实争用或电路可实现性时，再提升相应模型精度。参数参考不等于要求现在实现全部机制。

## 10 核对记录、参考依据与维护

### 10.1 本次重点修正

| 原材料容易造成的误解 | 本清单采用的口径 |
| --- | --- |
| 所有名词都算参数，每种技术都对应一个类 | 分开资源、机制、技术 profile、场景输入和结果；只为独立行为建模型 |
| SRAM/DRAM/NOR/NAND 统一给速度、耐久、容量范围 | 组织/命令/产品条件分别给定，不把经验量级当可计算默认值 |
| Rank=列；tRAS=读取延迟；tRFC=刷新间隔 | Rank 与 column 分开；tRAS 为 ACT→PRE；tRFC 与 tREFI 分开 |
| DRAM 整行写；MT/s 还需乘 2；rank 倍增总线带宽 | 激活行后按列/burst 访问；有效速率不再乘 DDR 系数；只累加独立接口 |
| HBM 固定 1024 bit；HBF 可直接复用 HBM 行为 | 位宽/通道/命令绑定技术版本与方案；Flash 服务约束保留 |
| NOR XIP 是片内执行；CFI 是物理总线 | 就地执行不限制片内/片外；CFI 是查询规范 |
| NAND 裸接口与 NVMe/UFS/eMMC 都是同层协议 | 分开介质接口、控制器、受管设备和主机协议 |
| CAM/TCAM 是普通 SRAM 类型；PCM=3D XPoint | 分开匹配行为、底层介质与产品技术名 |
| 推理一定带宽受限、训练一定算力/通信受限 | 按阶段、batch、布局、流量、并行映射、依赖和 SLO 判断 |
| occupancy=利用率；MFU=HFU；query heads=KV heads | 各自定义分子/分母与存储对象；不互换 |
| nominal ADC bits=ENOB=任务精度；QAT=量化感知量化 | 三种精度分别验证；QAT 正确名称为 Quantization-Aware Training |
| TDP=实测功率；节点 nm=栅长；工艺缩小可自动等比缩放 | 使用明确物理/测量边界及特征化 profile |

### 10.2 来源与核查范围

引用用于核对定义、公式和建模边界，不把开源项目热度或论文等级当成参数精度证明。动态网页和分支以本次访问为准；真正采用某个数值时，另记精确器件修订或 commit。

| 编号 | 一手资料 / 实现参考 | 本清单使用范围 |
| --- | --- | --- |
| R1 | Williams、Waterman、Patterson，Roofline，CACM 2009，[DOI](https://doi.org/10.1145/1498765.1498785)；[NERSC Roofline 文档](https://docs.nersc.gov/tools/performance/roofline/) | 本轮读取 NERSC 的定义与工作量/流量测量说明；原论文正文未取得。用于核对运算强度和资源上界，不提供完整队列/尾延迟模型 |
| R2 | [gem5 DRAMInterface.py](https://github.com/gem5/gem5/blob/stable/src/mem/DRAMInterface.py) | 本轮读取 stable 源码，核对 bank/rank/burst、时序和刷新定义；不是所有 JEDEC 标准的替代品 |
| R3 | [Micron HBM4](https://www.micron.com/products/memory/hbm/hbm4) | 本轮核对产品页的 2048-pin 数据接口说明；不作为所有 HBM 的默认参数 |
| R4 | [ONFI 规范入口](https://onfi.org/specs.html) | NAND 原始接口查证入口；本轮网站拒绝访问，未完成规范正文核验，具体命令/时序须再查选定版本/器件 |
| R5 | [Winbond W25Q128JV，Revision F，2018-03-27](https://www.winbond.com/resource-files/w25q128jv%20revf%2003272018%20plus.pdf) | 本轮读取数据手册，核对 serial NOR 的 XIP、页编程、sector/block 擦除分离；规格只适用于该产品 |
| R6 | ADI [MT-001](https://www.analog.com/media/en/training-seminars/tutorials/MT-001.pdf)、[MT-003](https://www.analog.com/media/en/training-seminars/tutorials/MT-003.pdf) | 本轮核对量化噪声、正弦 SNR、SINAD/ENOB 的条件；不将理想转换器公式当完整 CIM 精度模型 |
| R7 | [CUDA C++ Best Practices Guide](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html#occupancy) | 本轮核对 occupancy 的定义及其不等于性能的限制；厂商 warp/SM 组织不作为通用 GPU 常数 |
| R8 | Chowdhery 等，[PaLM，§4.1 / Appendix B](https://arxiv.org/html/2204.02311v5) | 本轮核对 MFU 排除 rematerialization 与 HFU 的区分；不沿用其特定模型规模/设备峰值 |
| R9 | Ainslie 等，[GQA，§2](https://arxiv.org/html/2305.13245v3) | 本轮核对 KV head 分组与 MQA 边界，支撑 KV 容量按 KV heads 统计 |
| R10 | [Timeloop](https://github.com/NVlabs/timeloop)、[DNN+NeuroSim V1.4](https://github.com/neurosim/DNN_NeuroSim_V1.4) | 本轮核对项目文档中的架构/映射与器件/外围职责、引用文献和能力条件；未验证其所有成本数据 |
| R11 | [Winbond W25N01GV，Revision L，2018-05-09](https://www.winbond.com/resource-files/w25n01gv%20revl%20050918%20unsecured.pdf) | 本轮读取 serial SLC NAND 数据手册，核对 Page Data Read、Data Buffer、Program Execute、Block Erase 与独立时序；不替代 ONFI/Toggle 接口规格 |

本次核查不包括完整 JEDEC/ONFI 时序表、所有新型存储的器件模型或未指定工艺的物理成本。它们作为需要来源的候选参数保留。表内其他计数、容量、时间与能量关系依据所写假设推导，不声称全部来自同一论文或已通过实测校准。

### 10.3 与已有文档的分工

- **选参数与查关系**：本清单；新设计先从这里筛选相关项。
- **查参数背景与工具**：[原结构参数手册](docs/reference/architecture_parameters.md)；保留为背景参考，不复制本清单作为第二份维护源。
- **查单元放在哪里**：[硬件组件目录](docs/reference/hardware_component_catalog.md)、[chipmodel 单元覆盖清单](chipmodel/docs/component_inventory.md)。
- **查实际字段/公式/调用**：[UNITS.md](chipmodel/UNITS.md) 与代码；生成字段表从代码更新，本清单不重命名或覆盖公共接口。
- **查可执行范围**：[STATUS](docs/STATUS.md)；技术候选和参考公式不作为实现完成的证明。

新增参数时先说明它改变的结果、单位、资源所有者、依赖和证据；规则见 [AGENTS.md](AGENTS.md)。若发现定义冲突，接口语义以公共契约与代码为准，先修正对应维护源，再同步本清单的参考关系。

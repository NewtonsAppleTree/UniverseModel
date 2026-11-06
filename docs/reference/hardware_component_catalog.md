# 硬件组件分类 接口与指标目录

本目录为组件建模提供覆盖清单，优先服务 CIM array + DAC/ADC + 缓冲的局部仿真，再按研究需要扩展。它不表示所有组件已实现，也不要求每次实验实例化整个清单。通用管理、端口与指标见[组件接口提案](../interfaces/component_protocols.md)。

实现归属沿用 chipmodel 到 Package、systemmodel 到 Node、clustermodel 管跨节点 fabric。下表的“建议路径”可能包含尚未创建的子目录；有实现时再同步 modules.json。参数均需单位、范围、条件与来源，不提供脱离工艺和组织方式的通用延迟常数。

按 chipmodel 的八个直接子目录逐项检查内部单元，见[子系统与单元覆盖清单](../../chipmodel/docs/component_inventory.md)。本文重点维护跨模块类型、输入输出和指标；该清单进一步展开处理器前端、内存控制器/PHY、管理、调试测试与物理条件。两份清单都是按研究范围扩展的设计资料。

## 1 先消除名称的多义性

| 名称 | 建议解释 | 不应默认推导 |
| --- | --- | --- |
| CPU/GPU/NPU | 可包含多类引擎、存储、控制和互连的复合设备 | 一个统一 core_count 或 TOPS 足以表示行为 |
| SFU | 特殊函数执行资源，具体操作集由能力定义 | 必然支持所有非线性算子或相同精度 |
| TMA | 本项目可采用张量搬运加速能力类；具体厂商 TMA 通过专用能力扩展 | 任意 TMA 都支持相同描述符、转置和同步 |
| TSU | 用户暂未限定含义，先保留可命名的控制单元类型 | 擅自固定缩写、指令或发射行为 |
| L0/L1/L2/L3 | 存储层级/作用域标签 | 自动等于 cache；需要区分 cache、scratchpad 和寄存器 |
| buffer | 存储区域、FIFO 或带协议的缓冲组件 | 名称本身说明物理介质、容量或访问成本 |
| ping-pong buffer | 两槽/多槽所有权轮转策略及存储配置 | 自动使吞吐翻倍或消除端口冲突 |
| array | 按用途区分数字 PE 阵列、存储阵列和 CIM 阵列 | 三者可以用一个 rows×cols 性能模型替代 |
| crossbar | 互连交换结构，或电阻/存储交叉阵列 | 一定执行模拟矩阵乘法 |
| core/tile | 可发射或组织工作的复合层级 | CPU Core、GPU SM、NPU Tile 具有相同单位能力 |
| chip/die | chip 可作为用户显示名；物理包含使用明确的 Die/Package | 一个逻辑设备必然等于一个裸片 |
| DDR/LPDDR/GDDR | DRAM 技术与接口族，按代际和配置选择 profile | 相同控制命令、时钟、PHY 或持续带宽；Double Data Rate 的字面含义不足以定义模型 |
| HBM/HBF | 分别描述具体 DRAM 堆叠接口/组织与 Flash 方案能力 | 相同访问粒度、写入机制、一致性或 CIM 能力 |

每种组件用 type_id、capabilities、mechanism 和实现版本定义行为。名称用于检索；不能仅靠字符串判断内部技术。TSU 在操作集合未定义前保持占位设计，不生成有耗时的虚构执行单元。

## 2 计算资源

| 组件族 | 输入 → 输出 | 关键技术指标与动态状态 | 建议路径 |
| --- | --- | --- | --- |
| CPU 设备/核心 | ISA 指令或工作摘要 → 退休结果/访存/事件 | ISA、issue/retire、流水线、ROB、分支、执行端口、缓存/TLB；按精度选择 | chipmodel/compute/cpu |
| GPU 设备/SM/CU | kernel/warp/指令 → 计算结果与访存 | warp 宽度、调度器、寄存器、shared memory、占用、合并访存、分歧、屏障 | chipmodel/compute/gpu |
| NPU/数字矩阵引擎 | tensor/tile → 部分和/结果 | PE 阵列、每发射 MAC、数据流、填充排空、累加位宽、利用掩码 | chipmodel/compute/npu |
| SIMD/向量/标量 ALU | 元素/向量操作 → 结果 | lanes、操作/周期、向量长度、掩码、精度、L/II、寄存器端口 | compute 下按复用需要新增 vector/scalar |
| SFU | exp/log/reciprocal/rsqrt 等声明操作 → 近似结果 | 操作覆盖、近似方法、范围、误差、L/II、共享队列 | compute 下建议新增 sfu |
| 归约/扫描/累加 | 输入流或部分和 → sum/max/prefix 等 | 树结构、fan-in、归约次序、位宽、缓冲、段边界 | compute 下建议新增 reduction |
| 激活/量化/转换 | tensor → 格式或数值变换结果 | rounding、scale、zero point、saturation、打包/解包、吞吐 | compute 下建议新增 transform |
| gather/scatter/置换/转置 | 索引与数据 → 重排结果及访存 | 对齐、步长、bank 冲突、缓冲、越界与重复地址语义 | compute/transform 或搬运子组件，按状态归属选择 |
| 稀疏/压缩单元 | 值、索引、掩码 → 编解码流或跳过计划 | 格式、元数据、非零分布、索引解析、数据相关延迟 | compute 下建议新增 sparse |
| 数字 CIM | 位/字与存储状态 → 数字部分和 | 单元计算机制、字线/位线组织、位串行、读写共享、累加 | chipmodel/compute/cim/arrays |
| 模拟/混合信号 CIM | 驱动与权重状态 → 电流/电荷/等效部分和 | cell 位数、行列、映射、器件非理想、驱动/负载、稳定时间 | chipmodel/compute/cim/arrays |

softmax、LayerNorm、attention 等通常是复合工作，由 reduction、SFU、向量操作及存储共同完成。若使用一个整体摘要模型，应声明已包含这些环节，避免又把内部资源执行一遍。

CPU/GPU 可以仅提供已校准的任务服务模型，用于研究外部路径；只有研究分支、warp 调度、cache feedback 等内部机制时，才需要相应细节。GPU SM 和 NPU tile 的资源限制不能由统一利用率常数代替。

## 3 CIM 外围与首批组件

| 组件 | 输入 → 输出 | 必需参数与状态 | 建议路径 |
| --- | --- | --- | --- |
| 权重编码与映射 | 逻辑权重 → 差分/位切片/阵列坐标 | signed 编码、cell bits、冗余、坏单元、切片位权、物理容量 | compute/cim/encoding；映射选择由 compiler 或手工计划提供 |
| 编程/校验控制器 | 目标权重状态 → 有效编程版本 | program/verify 次数、写入粒度、占用、能量、失败/耐久模型 | compute/cim/periphery 与 control |
| 输入编码器与 DAC/脉冲源 | 数字码/位序列 → 电压/脉冲 | 通道数、分辨率、settling、驱动负载、输出范围、误差 | compute/cim/encoding、periphery/dac（建议） |
| 行/列选择与 MUX | 通道/地址选择 → 路由后的驱动/信号 | fan-in/out、并发、切换时间、共享、负载/寄生条件 | compute/cim/periphery |
| 参考与读写驱动 | 参考/校准配置与行列命令 → 偏置、驱动与读写条件 | Vref/电流参考、参考噪声、wordline/bitline 驱动、编程电压及稳定时间 | compute/cim/periphery；物理供电条件引用 packaging |
| 感测/积分/TIA | 电流/电荷 → 可采样信号 | 物理量转换、增益、带宽、积分窗、噪声、饱和 | compute/cim/periphery |
| 差分求值 | 正/负阵列信号 → 差值信号或数字差 | 模拟/数字位置、范围、失配、转换次数 | compute/cim/periphery 或数字 transform |
| 采样保持 | 列信号 → 有有效期的样本 | 保持槽数、采样时刻、droop、复用顺序、有效窗 | compute/cim/periphery/sample_hold（建议） |
| ADC | 样本 → 数字码与饱和标记 | resolution、input range、采样率、L/II、共享、校准、架构相关能量 | compute/cim/periphery/adc（建议） |
| 移位累加与后处理 | 切片数字码 → 最终值 | 切片位权、符号、累加位宽、舍入、饱和、吞吐 | 可复用 compute/reduction/transform；CIM 配置组合它们 |
| 输入/输出/部分和缓冲 | 分配/读写/槽控制 → 数据与可见事件 | 容量、bank、端口、租约、元数据、部分和格式 | chipmodel/memory；策略引用存储实例 |

ADC 位数不等于权重位数或结果位数；名义分辨率不等于实际有效精度。输入范围、列和动态范围、噪声与校准共同决定饱和和误差。CIM 的目标质量应从逐阶段误差传播到最终任务，而不只检查某个转换器参数。

DAC 通道数、物理行数和同时激活行数分别保存；ADC 数、物理列数和每次转换的逻辑输出数也不同。共享 ADC 可能需要保持电路、重复阵列求值或流水缓冲，三种选择有不同成本。

模拟器首版可用离散数值和阶段事件表示模拟链条。它必须声明未覆盖的电路动态；不需要为每个输入向量启动晶体管仿真。数字 CIM 不要求 DAC/ADC，按实际机制删除阶段。

## 4 存储与层级

| 组件族 | 输入 → 输出 | 关键技术指标与行为 | 建议路径 |
| --- | --- | --- | --- |
| 寄存器文件/累加寄存器 | 编号、掩码、读写 → 操作数/结果 | 容量、读写端口、bank、bypass、位宽、占用 | memory 下建议新增 register_file |
| SRAM/scratchpad | 地址、读写、字节使能 → 数据/完成 | 容量、bank、bank 映射、端口模式、粒度、L/II、冲突 | chipmodel/memory/sram |
| CAM/TCAM 与关联查找 | key/mask、查找/更新 → 命中集合或优先匹配 | entries、key 宽度、多匹配语义、更新冲突、L/II、能量 | memory 下可新增 associative；TLB/目录或路由表按用途组合 |
| FIFO/elastic buffer | 入队/出队 → 数据/流控 | 深度、元素宽、读写并发、credit、空满、跨时钟能力 | memory 下建议新增 buffers |
| 双缓冲/环形缓冲 | 槽申请、生产/消费/归还 → 可用槽 | 槽数、地址区域、所有权、填充/排空、预留容量 | memory/buffers 策略；软件轮转归 runtime，硬件轮转归 control |
| L0/L1/L2/L3 cache | load/store/维护事务 → 命中结果或下级事务 | line、sets、ways、替换、MSHR、写策略、写回、预取、一致性 | memory 下建议新增 cache |
| TLB/地址翻译 | 虚拟地址/权限 → 物理地址或缺页 | 页大小、TLB 容量、walk 资源、权限、ASID、IOMMU 域 | 芯片 MMU 放 chipmodel；节点 IOMMU 放 systemmodel/io |
| 一致性目录与 home agent | 访存/snoop → 数据授权、失效与确认 | sharer/owner、目录容量、事务队列、原子性、内存顺序 | memory 下建议 coherence；传输由实际互连提供 |
| DRAM 介质 | 命令/访问 → 数据、完成与状态 | channel/rank/bank/row、burst、读写转向、激活/预充电、刷新 | chipmodel/memory/dram |
| DDR SDRAM | 控制器命令与数据 → 返回数据、bank/row 状态 | 按 DDR3/DDR4/DDR5 等具体代际声明时序、rank/bank group、burst、刷新、低功耗 | memory/dram 下建议 ddr profile |
| LPDDR SDRAM | 版本化命令/访问 → 数据与状态 | 按 LPDDR4/4X/5/5X 等配置声明 channel、功耗状态、CK/WCK 关系及实际访问时序 | memory/dram 下建议 lpddr profile；独立控制器/PHY 能力 |
| GDDR SDRAM | 图形存储访问/命令 → 数据与状态 | 按 GDDR6/GDDR7 等具体配置声明通道、信号/数据率、读写时序与误差保护 | memory/dram 下建议 gddr profile；不复用未经验证的 DDR 时序 |
| HBM 组织 | 控制器请求 → 堆叠 DRAM 服务 | stack/die/channel/pseudo-channel、bank、接口宽度与速率、访问时序 | memory/dram 原语 + composition/package 与控制器 |
| DRAM 内存控制器 | 地址/读写请求 → ACT/RD/WR/PRE/REF 等命令与完成 | 地址映射、队列、命令合法性、调度、页策略、刷新、读写切换与 QoS | chipmodel/memory/controllers |
| 内存 PHY 与训练 | 控制器侧命令/数据 → 物理接口传输与状态 | 协议/时钟比、DQ/DQS/时钟、校准训练、有效位宽、启动/唤醒及功耗 | memory 下建议 phy；物理通道引用封装或板级连接 |
| NOR Flash | 声明粒度的读/编程/擦除 → 数据/状态 | 读取接口、页/字编程、块擦除、并行、读写干扰、耐久 | chipmodel/memory/flash；具体 NOR provider |
| NAND Flash | page read/program、block erase → 页数据/状态 | die/plane、页/块、命令队列、ECC、坏块、编程限制、磨损 | chipmodel/memory/flash；具体 NAND provider |
| Flash 控制器/FTL | 逻辑访问 → 介质命令及返回 | 映射、buffer、GC、wear leveling、写放大、ECC、元数据 | memory/controllers；按模型覆盖启用 FTL |
| HBF 方案 | 具体接口的读写/预取 → 数据/完成 | Flash 技术、封装、控制器、粒度、带宽、限制与来源版本 | flash + controllers + 拓扑组合；不另复制通用 Flash 状态 |
| eDRAM/RRAM/PCM/MRAM 等 | 技术相关访问 → 数据/状态 | 读写不对称、保持、刷新、耐久、错误、物理条件 | memory 对应 provider；具备 CIM 才组合计算能力 |
| ROM/OTP/eFuse | 读取或受限制的配置/编程 → 常量或配置状态 | 一次性/只读规则、读取粒度、保护、初态与持久性 | memory 原语；boot/校准/修复逻辑由对应控制单元使用 |
| ECC/parity 与 scrub | 数据/校验码与错误状态 → 校验/纠错/poison | 码宽、覆盖边界、延迟、纠错能力、后台访问及错误传播 | memory/controllers 或对应介质/缓存组件，计费范围唯一 |

cache 是行为和组织，SRAM 是常见实现介质。可以让 cache 拥有标签/替换/MSHR 状态并调用 SRAM 成本或端口服务，但必须明确哪个层级计入命中延迟、能量和容量，避免双重收费。

NAND 不应直接模拟成可任意原位覆盖的 SRAM。若上层看到字节或块接口，中间控制器需要解释页、擦除、缓存和写放大；未研究这些行为时可采用有适用范围的摘要，结果仍需声明覆盖。

HBM 与 HBF 是具体组织/方案能力集合。峰值链路带宽不能代替持续服务率；HBF 的实现和接口随具体来源确定，不预设统一参数或已标准化的通用命令。

### 4.1 DDR 等存储子系统的五个建模边界

| 边界 | 输入 → 输出 | 需要保持的状态 |
| --- | --- | --- |
| 访问前端 | 地址、读写、大小、优先级 → 已接收请求或背压 | 请求/写入缓冲、权限/顺序、分拆与合并 |
| 控制器 | 前端请求 → 合法 DRAM 命令及返回 | 地址映射、读写队列、调度、刷新债务、低功耗管理 |
| PHY | 控制器接口事务 → 引脚/通道行为或等效服务 | 训练/锁定、时钟比、传输占用、模式和唤醒 |
| 通道/连接 | 电气传输或模型事务 → 对端交付 | 拓扑、rank 共享、总线转向、端点和实际带宽 |
| DRAM 器件 | 命令 → 数据、完成及约束状态 | 开启行、bank、时序计分、刷新和功耗状态 |

这五个边界可以在一个经过校准的摘要组件中合并，也可展开做局部研究。展开时上层不能再收取包含这些阶段的完整内存延迟。只检查 DDR 命令时序时，PHY 可采用明确的延迟与吞吐摘要，不必做电气波形仿真。

控制器需要维护对已发命令的时序视图，介质维护物理状态；两者通过命令/响应一致推进。不能出现两份可被各自独立修改、互相矛盾的 bank 状态。

### 4.2 参数与统计不能只剩带宽

| 参数族 | 应记录内容 |
| --- | --- |
| 技术与来源 | 标准/器件版本、速度档、工作电压/温度、器件组织、参数来源 |
| 组织 | channel/subchannel、rank、device width、bank group/bank、row/column、burst；按实际技术条件启用 |
| 时间与速率 | controller clock、DRAM tCK、PHY/数据时钟与比例、有效数据率、payload 宽度；不同域 cycles 分开 |
| 命令约束 | 适用的 RL/WL 或 CL/CWL、tRCD、tRP、tRAS、tRC、tRRD、tFAW、tCCD、tWR、tWTR、tRTP 等 |
| 刷新与低功耗 | tRFC/tREFI 等具体刷新约束、刷新粒度/策略、power-down/self-refresh、进入与退出时间 |
| 控制策略 | 地址交织、page policy、请求调度、write drain、QoS、请求/返回队列和在途数 |
| 容量与保护 | 逻辑可用容量、ECC/冗余/保留空间、错误与修复范围；on-die ECC 与通道 ECC 分开 |
| 统计 | 请求延迟分布、排队/命令/传输等待、row hit/miss/conflict、bank 并行、刷新阻塞、读写转向、实际字节与功耗 |

各技术和代际不一定使用相同字段，参数合法性由具体 profile 校验。改变速率不能简单把所有物理时间常数按比例缩放；器件时序表可能同时有时间和周期约束。

以一个假设的 DDR 配置为例：有效数据率 5600 MT/s、合计 payload 数据位宽 64 bit，理想单方向数据带宽为 `5600×10^6×64/8 = 44.8×10^9 B/s`，即十进制 44.8 GB/s。若这 64 bit 已是两个 32-bit subchannel 的总宽度，不能再乘一次 2；MT/s 已是有效传输率，也不能因 DDR 再乘 2。

rank 数增加不自动增加共享数据总线宽度。读写共享通道上的理想带宽也不能按读/写各算一份同时相加。持续带宽还受访问局部性、命令约束、刷新、读写切换和控制器调度影响；ECC 线宽不能无条件当作 payload。

DDR 控制器研究可直接输入地址轨迹，观察命令和请求完成，无需 CPU/GPU。若要研究缓存反馈、程序依赖或访存改变调度，则使用闭环驱动。DIMM/板载器件和板级拓扑由 systemmodel 组合，DRAM/控制器/PHY 代码按可复用组件保留。

## 5 搬运 控制与同步

| 组件族 | 输入 → 输出 | 关键指标与约束 | 建议路径 |
| --- | --- | --- | --- |
| 片内 DMA | 传输描述符 → 分块读写与完成 | 启动开销、通道、队列、burst、对齐、散集、在途数 | chipmodel/control 下建议 dma，数据端口连接片内存储/互连 |
| 节点 DMA/RDMA 引擎 | 主机/设备区域 → I/O 事务与完成 | IOMMU、权限、协议、队列、路径、共享注入能力 | systemmodel/io/dma、io/nic；复用通用搬运语义 |
| TMA/张量地址生成 | tensor 描述符 → 访问流、目标缓冲与通知 | 维度、stride、tile、layout、swizzle、越界规则、同步 | 片内 control/tma（建议）；可调用 DMA 和地址生成原语 |
| 描述符/指令前端 | 指令或队列项 → 解码后操作 | fetch/decode/issue、队列、依赖、异常、发射宽度 | chipmodel/control |
| 计分板/依赖跟踪 | 读写集合和完成 → 可发射资格 | token、hazard、容量、唤醒延迟、死锁诊断 | chipmodel/control |
| 硬件 barrier/semaphore | arrive/wait/signal → 释放事件 | 参与范围、世代、计数、内存顺序、错误退出 | chipmodel/control |
| TSU 类控制单元 | 明确定义的命令 → 选定控制动作 | 操作集、队列、发射/同步规则、L/II，待场景定义 | chipmodel/control 中的可注册类型 |
| 预取/调度策略 | 可观测状态 → 访问或发射决策 | 观察延迟、资源预算、准确率、额外流量 | 硬件策略在所属组件，软件策略在 runtime |
| 时钟/电源/复位控制 | 事件/域策略 → 状态变化 | clock domains、CDC、gate、DVFS、唤醒、reset epoch | control + packaging；统一时间仍由 simulator 管 |

片内 DMA 不应为复用名字而放到 systemmodel，使单个 CIM 宏强制依赖整机。反之，节点 IOMMU/RDMA 的权限与 I/O 路径也不应塞进普通片内 DMA。两者共用描述符语义，按实际边界添加协议能力。

TMA、DMA、layout 转换可以由一个复合实现完成；若开启内部细分，外层不再另计一次完整搬运。硬件控制请求与 runtime 的软件策略区分，防止由宿主驱动免费替代目标硬件发射瓶颈。

## 6 总线 互连与通信

| 组件族 | 输入 → 输出 | 技术指标与状态 | 建议路径 |
| --- | --- | --- | --- |
| 共享总线/交叉开关 | 主设备事务 → 目标事务/响应 | 宽度、频率、仲裁、地址/数据通道、outstanding、背压 | chipmodel/interconnect 下建议 bus/crossbar |
| AXI/AHB/APB/TileLink 等协议适配 | 协议事务或握手 → 公共请求/响应 | 版本、burst、ID/顺序、响应码、原子/一致性能力 | 对应互连适配器；仅实现实际所需协议子集 |
| NoC router/link | flit/packet → 路由输出 | 拓扑、flit 宽、VC、buffer、credit、路由、仲裁、死锁规则 | chipmodel/interconnect/noc |
| D2D/Chiplet 链路 | 端点事务/包 → 跨裸片交付 | lanes、编码、PHY 延迟、有效速率、重传、封装、功率 | chipmodel/interconnect/d2d |
| 3D 垂直连接 | 层间事务 → 相邻层/裸片 | TSV/混合键合、可用密度、端点共享、距离、热/几何条件 | d2d + packaging/geometry |
| PCIe/CXL/其他设备互连 | 节点 I/O/内存事务 → 设备或主机 | 版本、lanes、payload/协议、root/switch 共享、访问语义 | systemmodel/io 与 topology |
| NIC | 本地描述符/消息 → 网络注入/接收 | 端口、DMA 路径、队列、注入率、协议、offload、CQ | systemmodel/io/nic |
| Fabric link/switch | 包/消息 → 下一跳/目标 | 拓扑、路由、队列、流控、拥塞、oversubscription | clustermodel/fabric |
| collective | 组操作 → P2P 与本地规约 | 算法、chunk、参与者、顺序、重叠、数值 | runtime/communication；硬件资源按实际能力提供 |

总线协议、拓扑和物理链路是不同维度。AXI 名称不直接给出带宽；需要数据宽度、时钟、有效发射、burst 和实际仲裁。CXL 名称不自动授予所有组件统一一致性。

串行数据率、有效载荷带宽和按方向汇总的带宽分开；共享 PHY、端口、交换上行和 NIC 不能按逻辑链路数量重复扩容。CDC、重传、credit 往返和缓冲可能支配小消息延迟。

## 7 Core Die Package 与物理条件

Core/Tile、Die、Package、Board、Node 是组合层。它们导出外部端口、能力与约束，引用内部资源；只有真实存在的控制、互连或热资源才增加状态和成本。

3D 至少区分阵列内部层数、die stack depth 和计算裸片数。CIM-on-logic、多个计算 Die 堆叠、3D 存储阵列的接口和热条件不同，不能共用一个 layers 倍率。

物理模型按问题加入几何、floorplan、互连长度、供电、热 RC、工艺/电压/温度、制造差异、良率和寿命。架构事件模型可以消费这些条件，不能凭目录结构推断已经满足时序或热签核。

## 8 每种组件的最小文档模板

首次实现某种组件时，至少提供以下内容；公共规则用链接引用，避免在每个目录复制一份协议。

1. 研究用途、抽象范围、未覆盖行为，以及原语/复合组件关系。
2. 输入输出端口、操作集、完成条件、合法初态、数据/资源所有权。
3. 参数表：类型、单位、默认是否有依据、范围、派生关系、来源条件与版本。
4. 功能算法、数值规则、资源状态机、L/II/occupancy、争用与错误行为。
5. 动作/流量/存储/时间/能量的计数范围，与上下级模型的互斥计费规则。
6. 单组件调用样例、一个局部组合样例、最小合法例和关键非法例。
7. 独立参考、手算时序、校准证据、误差和模型替换限制。

优先为 DAC、array、sample/hold、ADC、shift-accumulate、buffer/control 建立这些说明。其余组件按研究敏感性增加；目录中的一个名称不构成可用能力。

# chipmodel 子系统与单元覆盖清单

本清单逐一展开 chipmodel 的 composition、compute、control、interconnect、memory、packaging、registry 和 docs。现有目录能够容纳主要职责，但目录名称及上一版组件表尚不足以作为完整的单元清单；DDR/LPDDR/GDDR、控制器/PHY、处理器内部机制及管理单元需要显式列出。

这里列出候选单元及职责，不表示已经实现，也不要求每次仿真全部启用。实际进度见 [STATUS](../../docs/STATUS.md)。首批仍选择 CIM array + DAC/ADC + 缓冲；其他单元按研究问题和边界需要加入。

共享输入输出与指标定义见[组件接口](../../docs/interfaces/component_protocols.md)，跨芯片、节点和集群的类型目录见[硬件组件目录](../../docs/reference/hardware_component_catalog.md)。下文建议的新子目录在首次有实现时再创建并同步 modules.json。

## 1 怎样判断覆盖是否足够

完整性应针对一条研究路径判断。每条路径检查八类内容：计算、数据存储、地址与一致性、搬运互连、发射同步、时钟电源、物理条件、观测与故障。对每一类说明实际模型、摘要边界或不适用，不能靠一长串器件名称宣称覆盖全部行为。

| 层次 | 清单应该记录什么 | 示例 |
| --- | --- | --- |
| 技术或协议族 | 版本、子类型、参数条件 | DDR5、LPDDR5、GDDR6、HBM、AXI |
| 可拥有状态的单元 | 输入输出、容量、队列、时间与错误 | DRAM bank、内存控制器、PHY、ADC |
| 机制或策略 | 所属单元、可替换规则、额外工作量 | 地址映射、预取、替换、仲裁、双缓冲 |
| 复合结构 | 实例引用、连接、共享约束 | CPU core、CIM macro、Die、Package |
| 软件基础设施 | 注册、创建、文档与配置入口 | registry、docs |

机制不一定需要独立组件。只有独立状态、资源竞争、可替换边界或单独研究的需要，才拆出模型。代码目录也不等于物理位置：片外 DDR 器件可复用 chipmodel/memory 的实现，实际实例由所在 Package、Board 或 Node 组合持有。

## 2 compute 计算与处理器内部单元

compute 既保存可复用执行原语，也可保存 CPU/GPU/NPU 的专用组织。复用同一物理执行单元时只有一份状态；外层设备摘要和内部展开模型互为替代层级。

| 分组 | 可进一步包含的单元或机制 | 需要观察的资源与行为 |
| --- | --- | --- |
| CPU 前端 | PC/取指、分支预测、BTB、返回栈、指令预取、解码、可选微操作缓存 | 取指/解码宽度、分支恢复、队列与前端停顿 |
| CPU 重命名与乱序 | rename map、物理寄存器分配、free list、ROB、保留站/issue queue、wakeup/select、提交 | 容量、依赖、发射端口、精确异常与恢复；顺序核可省略相应机制 |
| CPU 执行 | 整数 ALU、乘除、FPU、SIMD/vector、分支单元、地址生成 AGU | 支持精度、L/II、并发、寄存器端口与 bypass |
| CPU 访存接口 | LSU、load/store queue、store buffer、load forwarding、replay、原子操作 | 内存顺序、推测回滚、地址就绪与访存并发；cache/TLB 引用 memory 实例 |
| GPU 任务与线程组织 | 工作组/CTA 分配、warp/wave 调度、scoreboard、分歧/重汇合、屏障 | 驻留数、线程/寄存器/shared memory 约束、调度与等待 |
| GPU 执行与访存 | SIMT lanes、矩阵/tensor 单元、SFU、load/store、地址合并 coalescer、异步 copy | 指令支持、事务合并、bank 冲突、发射瓶颈与重叠 |
| GPU 图形扩展 | texture/sampler、rasterizer、ROP/blend、深度测试、可选光追遍历/求交 | 仅图形研究需要；各单元有独立任务、精度和存储访问 |
| NPU 数据通路 | PE/MAC、systolic/tensor 阵列、权重/激活分发、累加树、数据重用与填充排空 | 实际有效 MAC、数据流、边界 tile、部分和和供数限制 |
| NPU 后处理 | activation、pooling、reduce、normalization 所需原语、重排、量化与格式转换 | 数值规则、L/II、额外访存；复合算子按选定摘要或细化方式计量 |
| 可复用数字原语 | scalar、vector、SFU、reduction/scan、transform、稀疏索引与压缩/解压 | 操作覆盖、掩码、精度、数据相关工作量与队列 |
| DSP/专用加速 | FFT、FIR、复数 MAC、视频编解码、ISP、密码/哈希等 | 场景可选；复用算术和存储，专用状态归具体加速器 |
| CIM | 数字/模拟阵列、输入/权重编码、DAC、MUX、感测/TIA、sample/hold、ADC、移位累加 | 位切片、共享外围、保持窗口、编程/校准与误差 |

CPU/GPU 专用控制如 rename、warp scheduler 可以就近保留在对应模型中；跨引擎共享的描述符队列、DMA 和控制器放 control。寄存器文件、cache、shared memory 等物理存储引用 memory 原语，不因出现在两张设计图里就复制容量。

通用 TSU 暂不固定缩写和操作集；TMA 按张量搬运能力处理。SFU、tensor core 等名称只表示能力类别，具体语义和精度依实现声明。

## 3 memory 存储 地址与一致性

仅有 sram/dram/flash/controllers 四个目录不能直观看出完整路径。应按存储技术、访问组织、控制协议和地址/一致性分别登记。

| 分组 | 应考虑的单元或机制 | 关键参数及作用 |
| --- | --- | --- |
| 寄存器/寄存器文件 | operand register、accumulator、物理/架构寄存器文件 | 位宽、端口、bank、读写竞争和 bypass 边界 |
| 本地存储 | SRAM、scratchpad、TCM、GPU shared memory、片上 ROM | 容量、bank 映射、访问粒度、读写端口、L/II；不因层级名而自动加入 cache 行为 |
| 关联存储与查找 | CAM、TCAM、tag lookup、匹配/优先编码 | 条目数、key/mask 宽度、多匹配规则、更新、查找吞吐和能量；具体 TLB/路由查找可复用 |
| 缓冲 | FIFO、elastic/skid buffer、队列存储、ping-pong、多槽/ring buffer | 深度、元素宽、并发、源租约、满空/credit、槽归还 |
| Cache 阵列与控制 | instruction/data/unified cache、L0/L1/L2/L3/LLC、tag/data、victim cache | sets/ways/line、tag/data 访问、替换与端口 |
| Cache 未命中路径 | MSHR、miss/fill queue、write buffer、writeback queue、预取队列 | 合并请求、下级并发、脏行逐出、填充争用与额外流量 |
| 地址翻译 | TLB、page-walk cache、页表遍历器、权限检查、MMU | 页大小、容量、walk 并发、地址空间、异常与下级访存 |
| 一致性与原子性 | coherence controller、directory、snoop filter、home agent、atomic/ordering | sharer/owner 状态、失效确认、作用域、原子冲突；消息传输由互连承担 |
| DRAM 技术族 | SDR SDRAM、DDR 系列、LPDDR 系列、GDDR 系列、HBM、按需 eDRAM | 明确代际和配置；bank/row、burst、刷新、读写时序与低功耗状态 |
| DRAM 控制器 | 地址映射、读写队列、命令调度、页策略、刷新与低功耗管理 | channel/rank/bank 竞争、row hit/miss/conflict、读写转向、QoS |
| 内存 PHY | DDR/LPDDR/GDDR/HBM 的对应 PHY、训练/校准状态、数据/时钟接口 | 时钟比、有效位宽、数据率、训练、功耗及适用时序；摘要不必模拟模拟波形 |
| 非易失存储 | NOR、NAND、RRAM、PCM、MRAM、ROM/OTP/eFuse | 读/编程/擦除或一次性配置语义、保持、耐久；不自动赋予 CIM 能力 |
| Flash 子系统 | 控制器、页缓存、ECC、坏块管理、FTL、GC、wear leveling | 访问放大、后台工作、恢复与寿命；算法和介质状态分开 |
| RAS 数据保护 | ECC/parity、scrubber、poison、spare row/column、修复重映射 | 校验位和逻辑容量、纠错代价、后台占用与错误传播 |

建议新增子目录时考虑 register_file、buffers、cache、translation、coherence、phy。DDR/LPDDR/GDDR/HBM 的具体 profile 放在 dram 中，控制器放 controllers，对应 PHY 放 phy；不要按所有商业型号建立平行代码树。

### DDR 需要展开成一条路径

```text
load/store 或 DMA 请求
  → 地址翻译与权限检查（按需）
  → cache/coherence 或直接访存路径（按需）
  → 内存控制器 地址映射 读写队列 命令调度
  → 控制器与 PHY 接口（采用时明确 DFI 等协议版本）
  → PHY 与 DDR 信号通道
  → DRAM 器件 rank bank group bank row column
  → 返回数据与目标可见事件
```

其中 bank group、subchannel、rank 等是否存在及如何组织取决于技术和代际。DIMM/SODIMM、板载颗粒、板级布线属于实际系统/板卡组合；HBM 的堆叠与封装连接属于对应 Package 组合。不能把所有物理位置都放进处理器 Die。

研究内存模块或初始化时，还需按实际产品考虑 SPD/SPD hub、可选 RCD/数据缓冲器、模块 PMIC、ODT/终端与训练条件；这些并非所有 DIMM 或 DDR 系统都具备。它们的物理实例位于相应模块、器件或控制器侧，按实际边界归属 systemmodel、memory/phy 或供电模型。

可以只研究控制器 + DRAM：用访问轨迹替代 CPU，控制器输出 ACT/RD/WR/PRE/REF 等命令及低功耗动作，介质模型处理 bank/row 状态和时序约束。也可直接查询 DRAM 成本，或以经验证的服务摘要替代整个子系统。每种方式都要说明省略哪些排队、PHY 与刷新成本。

完整参数与带宽口径见[组件目录中的存储子系统说明](../../docs/reference/hardware_component_catalog.md)。DDR 不应只增加一个 bandwidth 字段而省略控制器和访问模式。

## 4 interconnect 通信路径与适配

| 分组 | 可包含的单元 | 关键行为 |
| --- | --- | --- |
| 点到点/流接口 | wire/link 摘要、ready/valid、stream、FIFO adapter | 位宽、L/II、容量、背压、消息边界 |
| 共享总线与 crossbar | arbiter、地址译码、mux/demux、请求/响应路由 | 主从并发、访问授权、占用与共享瓶颈 |
| 协议适配 | AXI/AXI-Lite、AHB、APB、TileLink、按需 ACE/CHI 类一致性接口 | 版本与支持子集、burst、ID、顺序、响应、原子/一致性事务 |
| NoC | NI/network adapter、packetizer、router、link、VC、输入/输出 buffer、credit | 路由、flit、仲裁、头阻塞、公平性、死锁与拥塞 |
| 桥接 | 位宽转换、协议桥、clock-domain bridge、地址/ID 转换 | 切分合并、转换延迟、顺序、缓冲、跨域同步 |
| D2D/chiplet | die-to-die controller/adapter、链路层、PHY、lane 管理 | UCIe 等具体协议能力、lane 数、重试、训练、功耗与可用率 |
| 物理通道 | 并行 I/O、SerDes、PCS/PMA、按协议需要的 CRC/FEC/replay | 编码、误码/恢复、端点瓶颈；不为所有链路默认启用同一机制 |
| 可选芯片外设接口 | GPIO、SPI/QSPI、I2C、UART、JTAG，或高速 I/O 原语 | 控制/boot/校准需要时建模；板级设备和拓扑归 systemmodel |

可考虑 bus、bridges、protocols、phy 子目录。DDR 专用 PHY 就近放 memory/phy；互连 PHY 放 interconnect/phy，确有共同原语时复用，不能各维护一份同一链路状态。

PCIe/CXL 的板级拓扑、Root Complex、交换和设备访问继续由 systemmodel 组合；NIC 与网络 fabric 按现行 systemmodel/clustermodel 边界维护。片内 PHY/协议原语代码可以复用，不因此移动整套系统状态。

## 5 control 发射 管理与可观测性

| 分组 | 可包含的单元 | 关键行为 |
| --- | --- | --- |
| 命令前端 | CSR/MMIO register block、doorbell、descriptor fetch、指令解码、command queue | 提交与发射分离、队列容量、权限、非法命令和回读 |
| 数据搬运 | 片内 DMA、scatter/gather、TMA、tensor descriptor、地址生成 | 对齐、stride/swizzle、burst、在途数、数据可见与出错 |
| 发射与依赖 | 硬件 scheduler、scoreboard、event/token、资源预留与仲裁 | dependency、RAW/WAR/WAW、多资源获取、公平性与无进展 |
| 同步 | barrier、semaphore、mutex/atomic 协调、fence | 参与范围、世代、顺序、取消和复位后的残留事件 |
| 中断和异常 | interrupt controller、completion queue、fault/status registers | 触发/合并、服务延迟、错误传播、清除与重试 |
| 系统管理 | timer、watchdog、boot/初始化状态机、可选管理微控制器 | 初始化、超时、固件动作、显式管理开销；微控制器核心复用 compute |
| 时钟与复位 | PLL/DLL 行为、分频/门控、clock domain、reset controller | lock/wakeup 延迟、频率切换、CDC/RDC 条件、epoch；模拟电路行为按需校准 |
| 电源控制 | power state machine、DVFS、power gating、retention、isolation 控制 | 状态转换、唤醒时间/能量、在途工作与保持数据 |
| 性能观测 | performance counters、event monitor、trace buffer、timestamp | 目标硬件计数和追踪开销；与 simulator 的宿主观测分开 |
| 调试与测试 | debug registers、JTAG TAP、scan 控制、MBIST/LBIST、repair/BISR | 调试/测试模式、吞吐损失、测试时间和修复；场景可选 |
| 可靠性与安全控制 | RAS 管理、错误中断、访问防火墙、隔离/保护配置、安全启动控制 | 有关故障/保护/启动研究时启用；介质错误仍由资源组件维护 |

PMU 可能表示性能监测，也可能表示电源管理，模型应使用明确的 performance_monitor 或 power_controller 名称。TSU 同样先按操作和状态定义，避免缩写决定错误归属。

时钟/电源控制器发出动作；packaging 保存物理供电和热条件；simulator 维护全局时间。CDC FIFO 可能属于互连桥，不能在 control 中再次复制它。组件本地状态机不必全部抽成一个全局控制器。

## 6 composition 组合与外部视图

| 组合层 | 可能包含的实例 | 组合需要提供 |
| --- | --- | --- |
| Engine/Macro | 阵列、外围、局部缓冲、控制 | 宏操作、外部端口、内部资源及成本覆盖 |
| Core/Tile/SM | 计算引擎、寄存器、本地存储、控制、网络端口 | 能力、发射范围、共享容量与时钟域 |
| Compute cluster | 多核/多 tile、共享 cache/SRAM、互连与管理 | 集群内部共享瓶颈；这里不同于多机 clustermodel |
| Die | compute、uncore、memory controller、PHY、I/O、clock/power 管理 | 外部端口、资源身份、面积与热源分布 |
| Chiplet | 计算、I/O、cache、存储或混合用途的 Die | 功能角色、D2D 端点、封装引用，不另复制 Die |
| Package | 一个或多个 Die、HBM 等存储、interposer/bridge、封装连接 | 外部视图、2.5D/3D 拓扑、共享功率及封装边界 |

uncore 是便于组织内存/互连/管理资源的组合名称，不是一个自动产生服务时间的通用组件。只在确有物理工作时计时；组合容器不能凭空增加时延、容量或能量。

如果 CPU/GPU 专用模型已拥有某组内部实例，composition 引用该实例图或把它作为整体模型。展开时必须关闭重叠摘要费用，保持唯一所有者。

## 7 packaging 几何 供电 热与制造

| 分组 | 应考虑的内容 | 进入模型的条件 |
| --- | --- | --- |
| 几何/布局 | die 尺寸、位置、floorplan/block placement、面积边界、keep-out | 线长、容量和物理约束影响候选选择 |
| 封装互连 | substrate、interposer、silicon bridge、microbump、hybrid bonding、TSV/RDL | 2.5D/3D、端点密度、布线和链路成本 |
| 热 | 功耗源、热 RC、TIM、heat spreader/heatsink 边界、温度传感位置 | 热限制、ADC/CIM 温敏误差、降频反馈 |
| 供电 | power domain、voltage rail、PDN、稳压/供电边界、IR drop/droop 摘要 | 供电约束、瞬态或电压对服务/误差的影响 |
| 时序和工作条件 | 工艺/PVT、频率适用域、时序裕量、局部约束 | 校准服务时间与判断目标频率是否物理可行 |
| 制造与可靠性 | KGD、组装良率、测试条件、热应力/老化摘要 | 研究经济性、可用性、寿命或物理可靠性 |

packaging 保存物理关联、约束与必要动态状态；costmodel 计算条件面积、能量和制造成本。实际转换器、链路和逻辑执行仍属于各组件，避免把这些对象在物理层再建一份。

板上 VRM、散热与机架冷却按所属系统层组合；chipmodel 可提供可复用物理模型。关闭某项物理机制表示结果不覆盖它，不能当成已证明该条件无影响。

## 8 registry 与 docs 是工程基础设施

registry 不代表片上注册表硬件。它应支持类型/实现 ID、版本、参数定义、端口协议、能力和模型精度、工厂创建、条件约束、成本 provider 绑定及显式别名解析。CPU/GPU/CIM 不应依靠模块导入顺序自动注册和执行。

registry 保存描述和创建入口，不保存所有运行共享的组件动态状态。create 应产生独立实例；共享资源由实例图显式表达。未知类型、版本或能力要给出诊断。

docs 保存职责、参数字典、接口、状态机、指标口径、局部样例、参考/校准依据和验证条件。每类组件的最小文档模板见[硬件组件目录](../../docs/reference/hardware_component_catalog.md)。README 负责导航，不另维护一张与 STATUS 不同的完成清单。

## 9 与当前目录的衔接

保留现有八类入口，优先在需要实现的父目录下细化。可以形成以下候选分组；这是规划，不是现有目录树或已经导出的 API：

```text
compute/       cpu gpu npu cim vector scalar sfu reduction transform sparse dsp
memory/        register_file sram buffers cache translation coherence
               dram/{ddr,lpddr,gddr,hbm} flash controllers phy
interconnect/  bus crossbar noc d2d bridges protocols phy
control/       command dma tma scheduling synchronization interrupts
               clock_reset power monitoring debug_test management
composition/   macro core tile compute_cluster die package
packaging/     geometry thermal power reliability
registry/      类型 能力 版本 校验器 工厂和成本适配绑定
docs/          设计 参数 接口 局部样例和验证说明
```

自定义存储访问协议、模拟光子计算、RF/SerDes 等新技术仍可能引入新单元；没有一份静态清单能穷尽所有芯片。判断是否需要扩展时，看新技术是否增加新的状态、资源、端口语义或可观察行为。

首批 CIM 路径应检查编码、阵列、DAC、感测/保持、ADC、数字累加、缓冲、搬运和最小控制。研究外存供数时，再加入 DDR/LPDDR/GDDR/HBM/HBF 中的实际候选及其控制路径；研究缓存/一致性或功耗时，再引入相关机制。所有未建模因素在结果范围中明确记录。

# Unit 类 参数与执行接口设计

本文把[单元覆盖清单](component_inventory.md)落实为可讨论的代码组织：语言选择、类与实例、参数和公式、单位、状态、接口及调用顺序。首批对象仍是 CIM array、DAC/ADC、采样保持、数字累加和缓冲。

本文规定各 Unit 的共同设计方式；系统推导见[系统级设计](system_model_design.md)，所有子模块的代码与参数从 [UNITS.md](../UNITS.md) 进入。[全仓库规则](../../docs/development/model_rules.md)要求每个 class/def 前有用途/公式说明，每个字段旁有专业含义与单位。实际进度见 [STATUS](../../docs/STATUS.md)；公共事件消息仍沿用[组件接口提案](../../docs/interfaces/component_protocols.md)。

## 1 Python 与 C++ 的分工

建议首先用 Python 实现可验证的小规模功能与事件模型。Python 的 dataclass、类型提示、清楚的字段名和普通函数适合展示参数、单位及公式，也便于交互实验。C++ 同样可以显式建模；语言不决定模型是否清晰或准确。

| 工作 | 首批建议 | 何时考虑其他实现 |
| --- | --- | --- |
| 参数定义、校验、装配、实验和分析 | Python | 通常继续保留 Python 用户入口 |
| 数值参考与 CIM 编码/量化 | Python，小例子可用标准库；批量数组采用 NumPy 等 | 大规模非向量化计算或已有可靠库时使用原生计算内核 |
| 组件状态机与有限资源事件 | Python，先记录事件数和宿主开销 | 性能分析表明事件调度/状态更新成为主要开销时细化 |
| 大型 cache/NoC/DRAM 或逐周期模型 | 按验证规模先选可维护实现 | 高频小事件、内存占用或复杂热点需要时采用 C++ |
| 外部工具与 RTL | 通过显式适配器 | 使用对应工具的原生语言与执行机制 |

Python 对象和大量解释器调用有开销，但应先控制建模粒度：不要为每个 bit/cell 创建一个宿主对象并每周期调用一次。矩阵状态用数组，互不影响的动作可在证明语义等价后批量处理，稀疏事件无需遍历所有空闲组件。

优化顺序建议为：测量宿主 wall time/内存/事件数 → 改数据布局与事件粒度 → 向量化/批量化 → 将确定的热点迁往 C++。不同实验可进程级并行；不假定 Python 线程能自动加速所有计算。

跨语言边界宜是一次批量计算、一个局部子图或一批事件，避免每个 cell/每条边都来回调用 Python。绑定需要固定 dtype、shape、布局、端序、数据生命周期、错误映射、随机性和事件排序。公共配置和结果格式继续保持一致。

目标芯片时间与宿主耗时分开。Python 花 1 秒算出 71 cycles，含义仍是模拟 71 cycles；不能用 Python/C++ 函数实际运行时间当成硬件服务延迟。

## 2 什么应该成为一个类

| 对象 | 推荐表达 | 例子 |
| --- | --- | --- |
| 有独立状态和资源竞争的行为类型 | Unit 模型类 | ADC bank、SRAM bank、DMA、DRAM controller |
| 同种类型的物理实例 | 同一模型类的不同实例 | 两个不同容量的 SRAM、两组 ADC |
| 技术/参数变体 | 参数 profile；行为变化足够大时选择不同模型实现 | DDR4/DDR5 profile，理想 ADC 与含校准误差的 ADC |
| 纯推导或纯数值操作 | 普通函数或可替换策略 | 位容量、量化、地址映射、调度比较规则 |
| 大量同质微单元 | 数组或批量状态结构 | conductance 矩阵、cell 编程状态、cache tag 表 |
| 复合硬件 | 组合对象及实例图 | CIM macro、Tile、Die、Package |

一个类描述一种模型行为，不意味着每个型号、每个实例都新写一个类。ADC bank 可以用一个对象管理多路转换资源；独立的每路状态可以是数组/记录。需要单独研究某一路时，也可实例化 lane_count=1 的模型。

按能力组合接口，避免让所有 Unit 继承一个包含几十个无关方法的巨大基类。可以使用小型 Protocol 描述请求/事件能力；功能函数、纯成本查询和时序组件不必实现相同的运行方法。

首批可以在一个实现文件中放少量明确的 dataclass 和一个模型类，不要求每个概念都拆成一个文件。共享语义成熟后再抽取公共类型。

## 3 一个 Unit 需要分清哪些数据

| 类别 | 谁提供或更新 | 示例 | 可变性 |
| --- | --- | --- | --- |
| 类型描述 Descriptor | 模型/参数定义注册 | type_id、版本、端口、能力、参数解释 | 定义随版本变化 |
| 配置草稿 Params | 用户或实验覆盖 | ADC bits、lane_count、输入范围、队列容量 | 创建新实验前可编辑 |
| 已解析规格 ResolvedSpec | configuration 与纯推导/校验 | 单位归一、派生值、完整来源与配置身份 | 单次运行内冻结 |
| 初态 InitialState | 用户、初始化器或兼容快照 | 权重、校准、冷/热存储、初始随机状态 | 初始化阶段消费 |
| 动态状态 State | 当前 Unit | 待处理队列、转换槽、权重世代、输出缓冲 | 只通过该 Unit 的协议修改 |
| 指标 Metrics | 唯一计数方 | 转换次数、等待时间、溢出次数、动作量 | 随事件更新；观察不改变执行 |
| 服务 Services | 装配方注入 | 时间/事件、成本、数据访问、随机子流 | 服务引用固定，按服务契约使用 |

Unit 的属性可以是 `spec`、`state`、`metrics`、`services`，但外部不应取得可任意修改的 state 或内部队列。能力和观测通过只读值对象返回。

frozen dataclass 只防止直接改属性，不会自动冻结嵌套 list、dict 或 NumPy 数组。配置可用不可变 tuple/值对象；运行数组由 Unit 独占或遵守显式共享/租约协议。浅拷贝不能作为完整的实验隔离或快照。

固定频率可在规格中给出；启用 DVFS 后实际频率是受控制事件更新的域状态。温度、权重年龄、噪声子流位置、校准版本也可能是动态状态，不能一概当成固定参数。

## 4 参数怎样显式定义与推导

每个公开参数至少记录字段名、类型、单位、作用域、值的来源、合法范围、默认值依据、依赖和变更效果。字段名相同但实例/条件不同，不可混作全局参数。

| 参数类别 | 处理规则 | 示例 |
| --- | --- | --- |
| 用户设计量 | 必须显式给出或采用有名称/版本的 profile | rows、columns、ADC 数、queue depth |
| 确定性派生量 | 使用带版本的纯函数，校验输入和单位 | 物理 bit 容量、码阶数、分组数 |
| 条件特征量 | 从 costmodel 查询公式、表格或测量依据 | 转换时间、settling、动作能量、面积、误差 |
| 策略选择 | policy_id/version 与参数 | 调度、替换、分组和取消规则 |
| 运行量 | 由执行得到，不能预先写成“正确答案” | 等待、实际吞吐、饱和率、峰值活跃容量 |

同一量可以有不同来源模式。例如 ADC 服务时间可选“给定周期数”或“校准物理时间”；必须显式选定一种权威来源。不能同时独立编辑 latency_cycles 和 latency_seconds，随后让二者矛盾。

廉价且无副作用的派生可以写成只读 property；需要反复使用、记录来源或纳入配置身份的派生值在解析阶段集中计算并保存。两者都不提供独立 setter。按当前队列得出的 busy 等运行观测不属于冻结的配置派生量。

纯派生遵循依赖顺序，如 frequency → period、bits/range → code_count/step。用户修改依赖后重算、重新检查成本适用域并生成新配置。温度与功耗反馈属于动态模型，不加入静态公式环。

首批优先普通 Python 函数，复杂表格插值作为成本 provider。需要用户编辑表达式时，只允许带单位检查的受限表达式；不使用任意 eval。也不必为了几条简单公式引入完整符号计算框架。

### 字段与公式的写法

参数、派生值、结果和内部状态在声明处紧跟短注释，统一写“专业含义 + 单位 + 必要区别”；派生字段再写公式。每个 class/def 前必须有简短 `#` 说明（在装饰器前），覆盖用途与公式或不变量；docstring 可补充输入输出和假设，不能代替前置注释。较长论证放各目录 UNITS.md。例如 resolution 与 ENOB、latency 与 II 要明确区分，不能只翻译字段名称。

物理量在字段名使用 `_v`、`_s`、`_hz` 等后缀；计数写清是 lane、sample、byte 还是 request。布尔量说明成立条件。公式中的 N、P、L、II、f 在首次出现处定义。必填设计量不提供未经说明的默认值；单位字符串和 NumPy 类型适配留在输入边界。

### 可直接运行的 ADC 例子

完整字段、注释和公式维护在 [adc.py](../compute/cim/periphery/adc.py)，本页只展示调用，避免复制一份会过时的类定义。

```python
from dataclasses import replace
from chipmodel.compute.cim.periphery.adc import AdcParams, IdealAdc

params = AdcParams(
    resolution_bits=10,  # Nominal resolution [bit]。
    lane_count=4,  # 并行转换通道 [lane]。
    conversion_cycles=2,  # Conversion latency L [cycle]。
    initiation_interval_cycles=2,  # 每 lane 的 II [cycle]。
    input_min_v=0.0,  # 输入下限 [V]。
    input_max_v=1.0,  # 输入上限 [V]。
)
adc = IdealAdc(params=params, frequency_hz=1e9)  # 固定转换时钟 [Hz]。
sample = adc.convert(0.5)  # 已采样电压 [V] → code=512，无越限。
batch = adc.estimate_batch(16)  # 16 samples → 理想完成时间 8 cycles / 8 ns。
wider = replace(adc, params=replace(params, lane_count=8))  # 重算派生量；原实例保留。
```

该配置的 K=1024、LSB=0.9765625 mV、单样本延迟 2 ns、bank 稳态上限 2×10^9 conversion/s。L/II 与频率是示例假设，不能从 bits 推导真实电路时序。调用顺序、数值边界、解析公式和覆盖限制见 [ADC 模型说明](adc_model.md)，完整运行入口见 [adc_demo.py](../../example/adc_demo.py)。

这是均匀 offset-binary 电压 ADC；既有 CIM 手算例使用带符号、无量纲等效列和 ADC。连接二者需要明确量纲、缩放与编码适配。

## 5 单位约定

用户可输入带单位的值，解析阶段归一到公共单位。第一次实现宜选择明确的字段后缀和集中换算；不在每个 Unit 中各写一套单位解释器。单位检查放在边界，事件热点可使用已验证的数值表示。

| 量 | 公共表示建议 | 注意事项 |
| --- | --- | --- |
| 时间 | second；引擎内部整数 tick 或精确表示 | tick 需绑定 resolution，物理时间映射到 tick 的舍入规则固定 |
| 时钟 | hertz、clock_domain_id；cycles 绑定该域 | 不混加不同域 cycles；DVFS 分段换算 |
| 容量/流量 | byte、bit 分开，计数使用整数 | GB/GiB、有效字节/物理分配/协议字节分别声明 |
| 电压/电流 | volt、ampere | 等效列和为 dimensionless，需适配才能成为物理电压 |
| 电导/电阻/电容 | siemens、ohm、farad | I=G×V 只在采用的物理模型假设下有效 |
| 电荷/频率 | coulomb、hertz | 采样率与数据/控制时钟不默认相等 |
| 能量/功率 | joule、watt | 动作能量、静态功率、功率状态积分分开 |
| 温度/面积 | kelvin、square_millimeter | 摄氏度输入需显式转换；面积范围含哪些外围要说明 |
| 分辨率/次数 | bit 位数、元素数、请求数、MAC 数 | 位数不是数据占用；MAC 是否按两次 ops 必须声明 |
| 带宽/速率 | byte/second、bit/second、conversion/second | B/cycle 必须绑定时钟，MT/s 不与 MHz 混用 |

公共契约现有单位清单需在首次电气接口 schema 冻结时显式扩展 volt/ampere/siemens 等量纲；不能因为 Python 字段能存 float 就跳过契约。物理值未知使用明确的 unavailable/unknown 状态，不能以零代替。

## 6 以 ADC bank 明确参数 属性与请求

一个 ADC bank 管理若干转换通道，外部请求可以包含一组待转换样本。控制器/策略决定分组，bank 维护可用通道与在途转换；大样本批次不表示无限并行。

| 类别 | 示例字段 | 单位/语义 |
| --- | --- | --- |
| 身份与模型 | instance_id、model_id/version、schema_version、clock_domain_id | 稳定引用；理想/误差/时序模型能力分别声明 |
| 数值参数 | resolution_bits、input_kind、input_range、code_format、rounding/saturation | bit；输入量纲与范围；signed/unsigned/offset-binary 不混用 |
| 结构参数 | lane_count、input_queue_capacity、output_buffer_capacity、inflight_capacity | 分别是通道数、请求数、样本数或已声明槽位；不能统称 depth |
| 时序参数 | conversion_latency、initiation_interval、sampling_window、source_release_policy | second 或绑定域的 cycles；L 与 II 独立 |
| 条件参数 | calibration_ref、temperature_ref、noise_model、cost_profile_ref | 引用及适用范围；动态量从所属服务/状态读取 |
| 派生属性 | code_count、code_step、理想通道服务率、某请求的 group_count | 只读；group_count 依请求样本数，不是所有请求共有常数 |
| 动态属性 | 输入队列、各 lane 在途项、最早发射时间、输出占用、随机状态 | Unit 私有状态；与配置分离 |
| 请求字段 | request_id、样本引用/量纲、sample_time/valid_until、目标引用、完成标识 | 含数据版本、分配世代、数量/形状与有效范围 |
| 输出字段 | 码值引用、编码信息、饱和/溢出标志、完成时间、诊断 | 不把整数码当成未经缩放的物理量 |
| 统计属性 | accepted/completed、converted_samples、queue_wait、busy_slot_time、clipped_samples | 请求数、转换次数、时间与异常计数分别记录 |

`busy` 可以是由 lane/queue 状态计算出的观测属性，不另维护一个可能失配的全局开关。`queue_capacity=4 requests` 不等于 `4 samples`，也不等于 `4 conversions in flight`。

流水线模型中 L 可以大于 II。若希望每 lane 每 II 接收一个样本，内部在途容量必须支撑相应重叠，且输出不会覆盖旧结果；也允许 II 大于 L 的恢复/周转模型。不要写成所有组件都必须 L=II。

source_consumed 应由模型声明：有内部采样锁存时可能在采样结束释放外部源；无内部保持时可能需要持续保持到转换结束。不能把 ADC 接收请求等同于可以覆盖 sample/hold。

转换结束但下游阻塞时，已产生的数据由有限输出缓冲或仍占用的执行槽保存。必须明确资源何时释放；不能丢弃结果，也不能凭空拥有无限完成队列。完成事件的可见边界在端口协议中定义。

## 7 其他首批 Unit 的参数与状态

| Unit | 显式参数与条件 | 可推导/可查询属性 | 私有状态及主要接口 |
| --- | --- | --- | --- |
| DAC/输入驱动 | 通道数、输入编码位数、输出量纲/范围、时序、驱动负载、参考与校准 | 码到输出映射；条件 settling/能量；不是仅按分辨率猜测 | 通道占用、当前输出/有效窗；drive 请求 → 稳定驱动事件 |
| CIM array | rows/columns、cell_bits、机制、映射、读写方式、工作条件 | 物理 bit 容量；按编码计算有效容量；条件求值/编程成本 | conductance/等效权重数组、program_epoch、有效区、老化；program/evaluate |
| Sample/hold | 槽数、采样/保持时间、路由、误差模型 | 最大同时保留样本、按条件的保持误差 | 槽中样本、世代、有效期、租约；capture/read/release |
| Shift/accumulate | lane 数、累加位宽、切片位权规则、L/II、溢出策略 | 位宽范围与理想服务率；请求组数 | 部分和、已完成切片、输出槽；accumulate/finalize |
| SRAM/buffer | 容量 B、bank/端口、地址映射、读写粒度、L/II | 组织容量与合法地址范围；条件面积/能量 | 内容/版本、分配、端口队列、槽租约；read/write/allocate 等已声明能力 |
| DMA/TMA | 通道、队列、最大 burst、对齐、张量布局能力、启动/传输模型 | 简单隔离条件下的传输服务需求 | 描述符、已传范围、在途读写；copy → 源释放与目的可见 |
| 最小控制器 | 可执行操作、队列、token/屏障容量、发射策略 | 能力与规则，不自动拥有额外吞吐 | 就绪队列、token 世代、等待集合；命令 → 阶段请求 |
| DDR 子系统 | 具体 DRAM profile、组织、命令时序、刷新、队列、PHY/通道条件 | 组织容量、接口峰值；成本查询 | bank/row/刷新、控制器队列、读写转向；访问请求或命令接口 |

buffer 是存储和策略的组合，ping-pong 也可能仅是两个区域的所有权策略；不强制与 SRAM 各算一遍存储服务。CIM 的每个 cell 通常是数组元素，除非其独立事件确实会影响研究结论。

## 8 对外与对内接口

| 层面 | 建议调用/数据 | 谁可以调用 |
| --- | --- | --- |
| 描述与配置 | describe、validate、纯 derive、create | 配置器、注册工厂、用户脚本 |
| 装配与初态 | bind/连接描述、initialize | 台架装配方，运行前完成 |
| 功能入口 | evaluate(data, numeric_spec) → result | 小规模数值检查；是否纯函数由该能力明确 |
| 时序入口 | submit(Request, SimContext) → Acceptance | 驱动器、runtime 或上游协议适配器 |
| 事件入口 | on_event(Event, SimContext) | 引擎分发或协议适配，不允许调用方伪造未来完成 |
| 观测与结束 | observe、finalize；可选 cancel/snapshot/restore | 外部只读取公开视图，改变状态须通过协议 |
| 内部实现 | 仲裁、分组、状态转换、成本查询、结果生成 | Unit 自身，外部不依赖私有方法与队列布局 |

对内又分两种：可替换子组件之间采用公共端口协议；同一个实现内部的辅助函数保持私有。没有必要为每条 Python 内部调用序列化 JSON，也没有必要把所有寄存器都暴露为用户可写字段。

大数据通过 DataRef 或明确所有权的数组接口传递。宿主共享内存不等于目标芯片零成本传输；功能内容可在宿主提前计算，但目标结果只能在协议规定的时间发布，且使用符合版本/租约的输入快照。

同一时刻各 Unit 的调用顺序不能由 Python 容器遍历顺序决定结果。事件阶段、delta round 与仲裁策略由引擎/组件各自明确；稳定排序只保证确定性，不自动保证公平性。

## 9 使用顺序

纯查询可以只调用 describe/derive/estimate；纯功能可以只构造数值规则并 evaluate。一次局部事件仿真的建议顺序为：

1. 确定作用域与覆盖：例如只研究 ADC 共享，输入用已采样向量，外部保持/接收条件明确。
2. 选择模型与 profile，编辑 Params，解析单位和覆盖来源。
3. 执行纯推导、字段约束、成本适用域检查，形成冻结规格。
4. 创建独立 Unit 实例，注入时间、数据、成本、随机与指标服务。
5. 绑定端口、地址域、时钟和外部边界，校验整体连接及共享资源。
6. 初始化数据、权重、校准及控制状态；生成初态身份。
7. 驱动器提交请求，处理 accepted/backpressured/rejected；保持正确的重试身份。
8. 引擎推进时间，组件仲裁并处理到期事件，分阶段发布源释放、结果就绪与目标可见。
9. 停止注入后按规则排空或截断，保留未完成请求与有效测量窗口。
10. 读取结果、指标和诊断；需要复现时保存配置、初态、数据/模型版本与随机方案。

不能用 `dac.run(); array.run(); adc.run()` 的顺序调用直接代表有重叠和背压的硬件时序。这样的函数链适合纯功能参考；事件仿真必须让独立资源按依赖和时刻交互。

静态派生依赖应无环，但物理连接图可以有环，例如 ring NoC 和反馈协议。不能为了调用顺序把所有连接图强制转为 DAG；应分别检查包含关系、公式依赖、操作依赖和协议死锁条件。

## 10 还需考虑的问题

这部分约束所有模块的代码和实验解释。下表列出共同约束及本轮基础实现的例子；事件模型和完整硬件/AI 执行链仍须独立验证。系统层的完整清单见[全局规则](../../docs/development/model_rules.md)。

| 问题 | 本次已落实 | 后续扩展与验收 |
| --- | --- | --- |
| 对象隔离与配置更新 | 冻结的标量配置与结果；`replace` 重新校验并推导，原实例不变 | 有状态 Unit 独占数组/队列；共享硬件通过实例图引用，不能隐式复制 |
| 数值边界与单位 | ADC/DAC 编码和端点、array 电流/跨阻、bit/byte/MT/s、cache 地址位和 TMA stride 显式；拒绝非法标量与范围 | dtype、端序、实际状态别名及其他编码由适配器明确；等效列和不能直接当 volt |
| 输入相关行为 | 每个真实电压产生码值与越限标志；样本数仅用于理想时序 | 稀疏、压缩、噪声和数据相关延迟须消费真实数据或明确分布；不能由固定利用率代替 |
| 确定性与随机性 | 无随机状态；重复转换与读取属性不改变结果 | 制造差异、编程误差、读噪声采用不同随机子流；记录种子、算法与流位置，明确跨版本复现范围 |
| 源与目标所有权 | 返回独立的不可变结果；功能调用不占用模拟缓冲 | sample/hold 有效期、source_consumed、有限输出容量、背压、取消和复位世代必须通过事件验证 |
| 时钟与资源容量 | 固定 ClockDomain；L/II 独立；GPU 驻留/存储容量单独校验；组合层用带初始 credit 的供给包络推导下界 | CDC、DVFS、同 tick 排序；在途/输出槽不足和真实共享争用必须由相应模型计算 |
| 计费与观测 | 无全局累计计数；组合选择拒绝同一口径下的摘要/后代重叠计费；逻辑 MAC、cell 动作、ADC 次数、协议/线路量分开 | 更细的阶段/时间窗口/能量归属仍需成本覆盖清单；trace 开关不改变执行 |
| 缓存与参数来源 | 每个新实例重新推导；不复用跨实验结果缓存 | 成本/数值模型版本、初态、输入数据、配置及校准条件都进入缓存身份；设计假设与测量值分开 |
| 快照与恢复 | 当前无事件或随机状态，可由显式配置重建 | 恢复需覆盖事件、数据、资源、随机和外部模型；pickle 一个 Unit 不等于完整快照 |
| 版本、错误与外部 ABI | `model_id` 标明语义版本；类型错误为 TypeError，域错误为 ValueError 并携带字段名 | JSON/schema、单位解析、注册工厂和跨语言 ABI 再统一；不能把 Python 私有布局直接当公共协议 |
| 独立验证 | 手算阈值/容量/DDR 带宽/突发、CIM 功能链、热 RC、布局、资源包络、依赖环和实例隔离 | 再加入真实争用、背压、完整数值路径与外部校准；功能通过不代表物理成本准确 |
| 性能与模型精度 | 初始化推导一次；不创建每 lane/cell 对象；精确量化保护阈值边界 | 大批量路径经测量后向量化或移到 C++，保留边界参考；事件聚合需保持因果与可见性 |
| 物理适用域与不确定性 | 分辨率不冒充 ENOB；L/II 是给定假设；不输出缺乏依据的能量/面积 | PVT、输入负载、带宽、settling、SNR/SNDR、INL/DNL、校准与误差相关性需要来源和适用范围 |

不要现在就给每个 Unit 填满上述字段：某模型没有状态、噪声或成本时，应明确覆盖边界。只有研究问题需要相应机制、并且能提供验证依据时，再引入字段与实现。

## 11 文件放置与首批实现范围

公共身份、端口、请求、结果与单位归 contracts；参数元数据和解析规则归 configuration；类型工厂在 chipmodel/registry；具体状态机和内部状态在对应 Unit 实现；条件成本归 costmodel；统一时间和驱动适配在 simulator。

类型专用参数的公开字段与元数据应只有一个维护定义。首批可以用 dataclass 加字段描述和显式校验函数，后续由同一描述生成 CLI/UI/文件 schema；不要分别为界面、JSON 和模型手写三套默认值。跨组件约束由装配阶段校验，特定模型的能力约束由模型注册描述提供，避免 configuration 反向依赖硬件实现。

本次以极简参数/公式和必要功能参考覆盖所有子模块，具体入口见各目录 UNITS.md；没有为每个器件名称生成类。CIM 已有 array/DAC/ADC、位权累加和静态 buffer/保持约束；下一步只有在研究结论需要时再加入有限资源事件、源租约、背压和完整 MatVec 夹具。DDR 命令调度、完整 CPU/GPU ISA 仍不作为局部研究的前置实现。

第一批交付应包含可运行小例子、明确参数表、独立数值参考、单请求/并发/背压时序与错误诊断。没有必要先为清单中的每个名称生成空类，或者同时维护一份 Python 和一份 C++ 实现。

## 12 参考做法与来源

参考重点是参数语义、模型边界和验证依据。下面资料支持这些工程做法；本项目的字段旁注释格式是本地约定，论文并不规定 Python dataclass 的写法。链接内容于 2026-11-06 核对，分支内容可能继续变化。

| 来源 | 采用的做法 | 在本项目中的落实 |
| --- | --- | --- |
| [gem5 DRAMInterface.py](https://github.com/gem5/gem5/blob/stable/src/mem/DRAMInterface.py) | Param.Latency/Voltage/Current 与参数描述相邻，tRCD/tCL/tRP 等时序分别定义 | 字段旁注明专业含义、单位、范围；L/II 分开；类型提示之外执行校验 |
| [Ramulator2](https://github.com/CMU-SAFARI/ramulator2)，*Ramulator 2.0: A Modern, Modular, and Extensible DRAM Simulator*，IEEE Computer Architecture Letters，2023 | 接口与实现分离；结构/时序 preset 可覆盖；未知参数与时序约束需要验证 | 行为模型和参数组合；局部调用不要求完整系统；暂不为一个 ADC 引入大型工厂框架 |
| [Timeloop](https://github.com/NVlabs/timeloop)，ISPASS 2019；其 Sparseloop 扩展见项目引用的 MICRO 2022 论文 | 使用显式架构与工作量做分析预测；稀疏行为需要专门的统计模型 | `estimate_batch` 明确无争用假设；输入相关误差与实际吞吐需要额外模型，不能只给峰值 |
| [DNN+NeuroSim](https://github.com/neurosim/DNN_NeuroSim_V1.4)，*DNN+NeuroSim: An End-to-End Benchmarking Framework for Compute-in-Memory Accelerators with Versatile Device Technologies*，IEDM，2019；*NeuroSim simulator for compute-in-memory hardware accelerator: validation and benchmark*，2021 | 器件、外围、技术节点与验证条件影响 CIM 结果；功能与硬件成本有不同依据 | 物理特征值留给有来源的 costmodel/profile；理想 ADC 不凭分辨率生成延迟、能量或面积 |

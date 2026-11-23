# controllers：绑定profile的隔离DRAM读路径

DramReadTiming是可手算路径模型，DramReadProfile将其与[组织/地址](../dram/UNITS.md)、CK和数据时钟（可为WCK）绑定。所有cycle均以CK计。R=fdata*transfers_per_data_clock，MT/s=R/10^6；burst_bytes=BL*payload_width/8，burst_cycles/fCK=BL/R。当前burst须可表示为整数CK周期；同一clock domain ID不可有两频率，技术名不隐含比例。

行命中前缀为CL，关闭为tRCD+CL，冲突为tRP+tRCD+CL；每额外burst等待max(tCCD,tBURST)，末尾加完整burst时间。起点PRE/ACT须已合法，所用tCCD适合当前bank-group关系；没有残余tRAS/tWR/tRTP等待、刷新、转向或其他请求。

profile→MemoryAccess→estimate_dram_access：单行入口拒绝越行/越容量/写操作。未对齐范围覆盖floor(start/burst)至ceil(end/burst)的完整burst。estimate_dram_span在行界拆分并保持逻辑byte守恒，逐channel累计burst量；条件界取max(接口需求界,最慢独立片段条件时间)。每段row_state均由调用方给定，不更新open-row，不累加片段宣称连续队列执行时间。max_fragments为宿主展开上限。

敏感参数为真实地址、burst、row_state、CK/数据时钟和命令间隔。可接[搬运/缓存组合](../../composition/UNITS.md)；队列、页策略、完整命令约束、刷新及返回可见性仍未实现，写服务不能套读profile。PHY成本若已包含在特征参数中不可重复计费。独立地址、时钟、burst、行界和共享总线证据见[测试](../../../tests/chipmodel/test_memory.py)，来源/复现见[指南](../../docs/memory_access.md)。

<!-- model-fields:start -->

### [dram_read.py](dram_read.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `DramReadTiming` | `t_rcd_cycles` | `int` | cycle | tRCD：ACT→RD 最小间隔 [cycle]。 |
| `DramReadTiming` | `t_cl_cycles` | `int` | cycle | CL：RD→首个数据传输 [cycle]。 |
| `DramReadTiming` | `t_rp_cycles` | `int` | cycle | tRP：PRE→下次 ACT [cycle]。 |
| `DramReadTiming` | `t_ccd_cycles` | `int` | cycle | 本次适用 bank/group 关系下的 RD→RD 间隔 [cycle]。 |
| `DramReadTiming` | `burst_cycles` | `int` | cycle | 一次 burst 占用数据接口的时间 [cycle]。 |
| `DramReadTiming` | `burst_bytes` | `int` | B | 一次 burst 的 payload 大小 [B]。 |
| `DramReadEstimate` | `transferred_bytes` | `int` | B | ceil(payload_bytes/burst_bytes)*burst_bytes [B]。 |
| `DramReadEstimate` | `completion_cycles` | `int` | cycle | PRE/ACT/RD 前缀+(bursts−1)*max(tCCD,tBURST)+tBURST [cycle]。 |
| `DramReadEstimate` | `completion_time_s` | `float` | s | completion_cycles/f_dram [s]。 |
| `DramReadProfile` | `organization` | `DramOrganization` | —（结构/对象） | 独立channel、共享rank和行/列有效数据组织。 |
| `DramReadProfile` | `timing` | `DramReadTiming` | —（结构/对象） | 全部cycle字段以ck为基准，burst_cycles也是CK周期数。 |
| `DramReadProfile` | `ck` | `ClockDomain` | Hz | 命令时序时钟CK [Hz]。 |
| `DramReadProfile` | `data_clock` | `ClockDomain` | Hz | 数据时钟 [Hz]；可与CK同频或为显式WCK。 |
| `DramReadProfile` | `transfers_per_data_clock` | `int` | transfer/cycle | 每数据时钟有效传输次数 [transfer/cycle]，例如DDR为2。 |
| `DramReadProfile` | `burst_transfers` | `int` | transfer/burst | 每burst有效数据传输次数 [transfer/burst]。 |
| `DramReadProfile` | `profile_source` | `str` | 1（标识/枚举） | 模式、时序与关系的来源/假设；不是自动器件校准。 |
| `DramReadProfile` | `row_order` | `tuple[str, ...]` | 1（标识/枚举） | 行块地址低→高的混合进制维度。 |
| `DramReadProfile` | `channel_bandwidth_bytes_per_s` | `float` | B/s | 只读派生属性；单channel有效数据速率 [B/s]；rank不乘带宽，数据时钟因子只使用一次。 |
| `DramAccessEstimate` | `request_id` | `str` | 1（标识/枚举） | 当前行片段身份。 |
| `DramAccessEstimate` | `address_bytes` | `int` | B | 当前片段的原始地址 [B]。 |
| `DramAccessEstimate` | `logical_bytes` | `int` | B | 有效请求数据 [B]。 |
| `DramAccessEstimate` | `location` | `DramAddress \| None` | —（结构/对象） | 非空请求的起点坐标；空请求为None。 |
| `DramAccessEstimate` | `row_state` | `str` | 1（标识/枚举） | 声明的hit/closed/conflict隔离条件。 |
| `DramAccessEstimate` | `first_burst_address_bytes` | `int \| None` | B | 对齐后的首burst地址 [B]。 |
| `DramAccessEstimate` | `burst_count` | `int` | burst | 覆盖偏移与长度所需完整burst数 [burst]。 |
| `DramAccessEstimate` | `transferred_bytes` | `int` | B | burst_count*burst_bytes [B]，包括头尾多传数据。 |
| `DramAccessEstimate` | `completion_cycles` | `int` | CK cycle | 在PRE/ACT已合法且无其他请求的条件下 [CK cycle]。 |
| `DramAccessEstimate` | `completion_time_s` | `float` | s | 上述条件服务时间 [s]，非请求队列完成时间。 |
| `DramSpanEstimate` | `fragments` | `tuple[DramAccessEstimate, ...]` | —（结构/对象） | 行片段，byte范围无重叠且覆盖原请求。 |
| `DramSpanEstimate` | `channel_transferred_bytes` | `tuple[tuple[int, int], ...]` | B | 每channel完整burst数据量 [B]。 |
| `DramSpanEstimate` | `interface_lower_bound_s` | `float` | s | max(channel_bytes/channel_rate) [s]，数据总线必要条件。 |
| `DramSpanEstimate` | `lower_bound_s` | `float` | s | max(接口界,所有隔离片段时间) [s]，依赖声明的行状态条件。 |
| `DramSpanEstimate` | `execution_time_s` | `None` | s | 连续命令/队列执行时间 [s]，未知。 |
| `DramSpanEstimate` | `unknown_reason` | `str` | 1（标识/枚举） | 缺少调度、刷新及完整时序合法性，不隐含免费状态重置。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `DramReadTiming` | 同一 DRAM 时钟域下的读路径特征值；由具体器件/profile 提供。 |
| `DramReadEstimate` | 单个隔离请求的尾数据到达时间，访问字节按 burst 向上取整。 |
| `estimate_dram_read(p: DramReadTiming, clock: ClockDomain, *, payload_bytes: int, row_state: str)` | row_state=hit/closed/conflict 分别需要 RD、ACT+RD、PRE+ACT+RD；请求必须处于同一行。 |
| `DramReadProfile` | 组织、CK命令时序、数据时钟和burst是一份绑定profile；技术名不隐含DDR/WCK比例。 |
| `DramReadProfile.channel_bandwidth_bytes_per_s` | 单channel有效数据速率 [B/s]；rank不乘带宽，数据时钟因子只使用一次。 |
| `DramAccessEstimate` | 单行范围与真实burst覆盖；row_state为调用方给出的隔离起点条件，不由历史猜测。 |
| `estimate_dram_access(profile: DramReadProfile, access: MemoryAccess, *, row_state: str)` | 单行入口明确拒绝越行；未对齐请求覆盖floor(start/burst)到ceil(end/burst)的完整burst。 |
| `DramSpanEstimate` | 跨行请求拆为独立条件片段；只给必要服务界，不假装已实现连续命令调度。 |
| `estimate_dram_span(profile: DramReadProfile, access: MemoryAccess, *, row_state: str, max_fragments: int=100000)` | row_state显式适用于每个独立行片段；不从前一个片段的模型返回值更新open-row状态。 |

<!-- model-fields:end -->

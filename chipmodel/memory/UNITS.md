# memory：容量、访问语义和数据驻留

容量约束回答“能否同时放下”，访问模型回答“怎样读写”，服务模型回答必要时间约束。三者不能缩成一个bandwidth参数；L0/L1/L2标签不自动产生cache行为。研究问题、独立接口与证据见[CH7指南](../docs/memory_access.md)。

| Unit/子模块 | 实现边界 | 关键量 |
| --- | --- | --- |
| BufferParams / BufferReservation | 固定槽与唯一backing区间预留 | slots、bytes、offset；禁止重叠/越界，无动态生命周期 |
| MemoryAccess | 显式byte地址/长度和read/write身份 | 半开范围；没有数据值或隐含成本 |
| CacheGeometry / CacheParams / CacheState / trace_cache | 几何、精确LRU/write-back/write-allocate、可恢复元数据 | sets/ways/line、实际访问、逐行hit/miss、整行回填/写回 |
| [SRAM](sram/UNITS.md) | Bank/word、独立R/W或共享RW、显式事务与隔离服务 | word放大、bank分布、L/II及掩码写能力 |
| [DRAM](dram/UNITS.md) | 显式组织、行块地址映射、接口速率 | rank共享总线、独立channel、payload宽度/MT/s |
| [controllers](controllers/UNITS.md) | DRAM读profile绑定、burst覆盖、跨行拆分 | CK/data clock、行状态、命令前缀；条件界 |
| [Flash](flash/UNITS.md) | NAND几何、单die单页缓冲及串行读路径 | 阵列页读与外部data/OOB列输出分别计量 |

使用顺序：任务/布局与活跃集合→容量/地址→介质/profile→显式访问→独立分析→[搬运/缓存组合](../composition/UNITS.md)。Buffer不重复拥有SRAM，cache容量和承载它的SRAM不重复相加。权重、activation、梯度、optimizer、KV需求由上层映射，不假定固定内存比例。

`trace_cache(params, accesses, initial_state=..., flush=...)`只执行元数据功能。默认冷缓存，恢复须显式给出同profile快照。所有miss（含整行覆盖写）先整行读入；脏逐出先写回再填充。flush按地址序写回dirty但不失效，默认保留deferred dirty bytes。动作ID在本次调用内唯一，跨批组合应增加批身份或重命名。

敏感量为sets/ways/line_bytes和地址局部性。命中统计按line touch，跨行请求可产生多次触及；零touch不定义命中率。稀疏LRU状态只分配实际使用的set，max_line_touches保护宿主展开，不是MSHR容量。CacheGeometry.metadata_bits不含替换元数据、ECC或电路成本。数据值、一致性、预取、lookup/回填时序未建模。

Register file、TLB/MMU、directory、MSHR、ECC、PHY和NOR仍为候选Unit，不能从SRAM/NAND参数自动获得。独立时间戳LRU参考、逐byte枚举、脏回写顺序及快照分批等价性见[测试](../../tests/chipmodel/test_memory.py)。

<!-- model-fields:start -->

### [access.py](access.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `MemoryAccess` | `request_id` | `str` | 1（标识/枚举） | 本批唯一访问身份。 |
| `MemoryAccess` | `address_bytes` | `int` | B | 当前backing的本地byte地址 [B]，非负。 |
| `MemoryAccess` | `length_bytes` | `int` | B | 请求有效数据长度 [B]，允许0。 |
| `MemoryAccess` | `direction` | `Literal['read', 'write']` | —（结构/对象） | 读或写意图；具体介质必须检查支持能力。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `MemoryAccess` | 实际访问范围与方向；同一结构可送缓存轨迹或选定介质的适配入口。 |

### [buffer.py](buffer.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `BufferParams` | `slot_count` | `int` | slot | 可保留独立批次的槽数 [slot]。 |
| `BufferParams` | `slot_bytes` | `int` | B/slot | 每槽预留空间 [B/slot]。 |
| `BufferParams` | `capacity_bytes` | `int` | B | 只读派生属性；总保留容量 C=slot_count*slot_bytes [B]。 |
| `BufferReservation` | `reservation_id` | `str` | 1（标识/枚举） | 此次装配内唯一预留身份。 |
| `BufferReservation` | `backing_id` | `str` | 1（标识/枚举） | 唯一底层存储资源 ID。 |
| `BufferReservation` | `offset_bytes` | `int` | B | 第一个槽在 backing 中的地址 [B]。 |
| `BufferReservation` | `buffer` | `BufferParams` | B | 连续等长槽；覆盖 slot_count*slot_bytes [B]。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `BufferParams` | 固定大小槽的保留容量，不复制底层 SRAM，不维护 ready/free 生命周期。 |
| `BufferParams.capacity_bytes` | 总保留容量 C=slot_count*slot_bytes [B]。 |
| `BufferParams.validate_payload(self, payload_bytes: int)` | 单槽装载边界：0≤payload_bytes≤slot_bytes；返回不表示实际占有槽位。 |
| `BufferReservation` | 一组连续槽仅引用 backing 地址，不新增物理容量或存储时延。 |
| `validate_reservations(backing_id: str, capacity_bytes: int, reservations: tuple[BufferReservation, ...])` | 半开区间 [offset,offset+capacity) 不得重叠；此接口不声明别名或动态释放。 |

### [cache.py](cache.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `CacheGeometry` | `sets` | `int` | set | Set 数 S [set]。 |
| `CacheGeometry` | `ways` | `int` | line/set | 每 set 相联路数 A [line/set]。 |
| `CacheGeometry` | `line_bytes` | `int` | B/line | Cache-line 数据大小 B [B/line]。 |
| `CacheGeometry` | `address_bits` | `int` | bit | 此 cache 实际使用的地址宽度 [bit]。 |
| `CacheGeometry` | `status_bits_per_line` | `int` | bit/line | 显式状态位预算，如 valid/dirty [bit/line]。 |
| `CacheGeometry` | `capacity_bytes` | `int` | B | 只读派生属性；数据阵列容量 S*A*B [B]；标签和控制位另计。 |
| `CacheGeometry` | `tag_bits` | `int` | bit/line | 只读派生属性；Tag 宽度=address_bits−log2(S)−log2(B) [bit/line]。 |
| `CacheGeometry` | `metadata_bits` | `int` | bit | 只读派生属性；标签与显式状态的总存储量 [bit]；不含替换元数据或 ECC。 |
| `CacheParams` | `geometry` | `CacheGeometry` | —（结构/对象） | 数据/tag容量与地址划分；至少包含valid和dirty两个状态bit。 |
| `CacheParams` | `profile_source` | `str` | 1（标识/枚举） | 策略/几何来源或实验假设，不代表电路校准。 |
| `CacheParams` | `policy` | `str` | 1（标识/枚举） | 所有miss整行读入，写命中置dirty；不优化整行覆盖写。 |
| `CacheState` | `params` | `CacheParams` | —（结构/对象） | 状态绑定的几何/策略/来源，恢复时须完全一致。 |
| `CacheState` | `lru_lines` | `tuple[int, ...]` | B | 有效行的对齐byte地址 [B]；跨set顺序无语义，set内为LRU→MRU。 |
| `CacheState` | `dirty_lines` | `tuple[int, ...]` | B | dirty行地址 [B]，必须为有效行的子集。 |
| `CacheTouch` | `request_id` | `str` | 1（标识/枚举） | 来源访问身份。 |
| `CacheTouch` | `line_address_bytes` | `int` | B | 触及行的起始byte地址 [B]。 |
| `CacheTouch` | `set_index` | `int` | —（结构/对象） | (address/line_bytes) mod sets。 |
| `CacheTouch` | `hit` | `bool` | 1（布尔） | 此次触及前该行是否有效驻留。 |
| `CacheTouch` | `evicted_line_address_bytes` | `int \| None` | B | 被替换行起始地址 [B]；未替换为None。 |
| `CacheTouch` | `dirty_eviction` | `bool` | 1（布尔） | 被替换行是否需要整行写回。 |
| `CacheTrace` | `touches` | `tuple[CacheTouch, ...]` | —（结构/对象） | 按原访问及行地址顺序的功能轨迹。 |
| `CacheTrace` | `backing_accesses` | `tuple[MemoryAccess, ...]` | —（结构/对象） | 有序整行写回/读入；dirty eviction先写再填充。 |
| `CacheTrace` | `final_state` | `CacheState` | —（结构/对象） | 调用方显式传给下批，默认不flush。 |
| `CacheTrace` | `line_hits` | `int` | touch | 命中行触及数 [touch]。 |
| `CacheTrace` | `line_misses` | `int` | touch | 缺失行触及数 [touch]。 |
| `CacheTrace` | `fill_bytes` | `int` | B | miss*line_bytes [B]，含write allocate。 |
| `CacheTrace` | `writeback_bytes` | `int` | B | dirty eviction及显式flush的整行输出 [B]。 |
| `CacheTrace` | `deferred_dirty_bytes` | `int` | B | 留在最终缓存内尚未写回的dirty行数*line_bytes [B]。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `CacheGeometry` | 地址分为 tag/index/offset；sets 和 line_bytes 为 2 的幂。 |
| `CacheGeometry.capacity_bytes` | 数据阵列容量 S*A*B [B]；标签和控制位另计。 |
| `CacheGeometry.tag_bits` | Tag 宽度=address_bits−log2(S)−log2(B) [bit/line]。 |
| `CacheGeometry.metadata_bits` | 标签与显式状态的总存储量 [bit]；不含替换元数据或 ECC。 |
| `CacheParams` | 固定可验证策略：精确LRU、write-back/write-allocate；几何本身不携带命中率。 |
| `CacheState` | 可恢复的元数据状态；每set按LRU→MRU保存有效行，未出现的set为空。 |
| `CacheTouch` | 每次行触及的结果；跨行请求可产生多个hit/miss，不能当作原请求命中率。 |
| `CacheTrace` | 功能元数据与外存事务；不提供数据值、lookup时序、MSHR或一致性模型。 |
| `trace_cache(params: CacheParams, accesses: tuple[MemoryAccess, ...], *, initial_state: CacheState \| None=None, flush: bool=False, max_line_touches: int=100000)` | 按byte范围拆行并执行精确LRU；flush只写回并清dirty，不使有效行失效；host限制非硬件容量。 |

<!-- model-fields:end -->

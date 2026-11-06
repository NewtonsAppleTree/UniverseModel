# memory：容量、访问语义和数据驻留

容量约束回答“能否同时放下”，访问模型回答“怎样读写”，端口/时序回答“何时可用”。三者不能缩成一个 bandwidth 参数；存储层级 L0/L1/L2 是标签，不自动产生 cache 行为。

| Unit/子模块 | 实现边界 | 关键量 |
| --- | --- | --- |
| BufferParams | 固定大小槽的预留与单槽容量校验 | slot count、slot bytes；ping-pong 为两槽 |
| CacheGeometry | Set/way/line 容量与 tag/index/offset | sets、ways、line bytes、地址宽度；没有命中率 |
| [SRAM](sram/UNITS.md) | Bank/字/独立端口组织 | 数据容量、bank 映射、每方向上限 |
| [DRAM](dram/UNITS.md) | 显式组织与接口速率 | rank/bank/row/column、payload 宽度、MT/s |
| [controllers](controllers/UNITS.md) | 隔离的 DRAM 读前缀时序 | 行状态、tRCD/CL/tRP/tCCD/burst |
| [Flash](flash/UNITS.md) | NAND page/block/plane/die 组织与串行特征时间 | 数据/spare、read/program/erase 粒度 |

Register file、TLB/MMU、coherence/directory、MSHR、ECC、PHY 和 NOR 仍是候选 Unit，尚无独立行为代码。分别需要寄存器端口、页大小/地址域、共享者/原子范围、在途项、保护开销、电气/训练条件、技术专用读写规则；不能由 SRAM/NAND 参数自动获得这些能力。

最关心逻辑有效字节、物理分配字节、真实访问字节与生命周期。AI 权重、activation、梯度、optimizer state、KV cache 的存储需求由上层映射传入；本模块不假定训练或推理的固定内存比例。

使用顺序：先定义对象/布局与活跃集合 → 校验容量/地址 → 明确介质/访问粒度 → 独立分析 → 接上控制器与路径。Buffer 不重复拥有一份 SRAM，cache data 容量和底层 SRAM 也不能重复相加。

<!-- model-fields:start -->

### [buffer.py](buffer.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `BufferParams` | `slot_count` | `int` | slot | 可保留独立批次的槽数 [slot]。 |
| `BufferParams` | `slot_bytes` | `int` | B/slot | 每槽预留空间 [B/slot]。 |
| `BufferParams` | `capacity_bytes` | `int` | B | 只读派生属性；总保留容量 C=slot_count*slot_bytes [B]。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `BufferParams` | 固定大小槽的保留容量，不复制底层 SRAM，不维护 ready/free 生命周期。 |
| `BufferParams.capacity_bytes` | 总保留容量 C=slot_count*slot_bytes [B]。 |
| `BufferParams.validate_payload(self, payload_bytes: int)` | 单槽装载边界：0≤payload_bytes≤slot_bytes；返回不表示实际占有槽位。 |

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

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `CacheGeometry` | 地址分为 tag/index/offset；sets 和 line_bytes 为 2 的幂。 |
| `CacheGeometry.capacity_bytes` | 数据阵列容量 S*A*B [B]；标签和控制位另计。 |
| `CacheGeometry.tag_bits` | Tag 宽度=address_bits−log2(S)−log2(B) [bit/line]。 |
| `CacheGeometry.metadata_bits` | 标签与显式状态的总存储量 [bit]；不含替换元数据或 ECC。 |

<!-- model-fields:end -->

# sram：Banked SRAM 的组织与端口

Unit 为 SramParams、SramAccess、SramService；存储容量是 bank_count*words_per_bank*word_bits/8。低位 word-interleaving 的 bank 为 floor(address/word_bytes) mod bank_count。这里仅分析地址与容量，不存储实际字节数组。

独立R/W或共享RW二选一，单方向峰值为 banks*ports*word_bytes*f/II。共享RW的读写合计受同一端口约束，不能同时使用两个方向峰值。该方向专用与共享端口均为零时不支持访问。混合专用+共享暂不接受。

最关心访问粒度、bank 冲突、端口共享与实际并行度。`peak_sram_bandwidth` 假设各 bank 均匀供数，没有模拟地址轨迹、读后写时序、ECC、低功耗或外围能量。ClockDomain 必须是此 SRAM 的访问时钟。

`analyze_sram(params, clock, accesses)`先验证身份、范围与写掩码，再统计每请求触及的word；不跨请求合并。非对齐读计全word，部分写须supports_byte_write。每bank独立端口G=max(ceil(R/Pr),ceil(W/Pw))，共享端口G=ceil((R+W)/P)，隔离C=L+(G−1)II；空工作C=0。输入就绪和无相关性是隔离服务前提；没有存储内容或队列。独立逐byte枚举与1/4-cycle、1R1W/1RW反例见[验证](../../../tests/chipmodel/test_foundation.py)。

<!-- model-fields:start -->

### [access.py](access.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `SramAccess` | `request_id` | `str` | 1（标识/枚举） | 本批唯一访问身份。 |
| `SramAccess` | `address_bytes` | `int` | B | SRAM 本地字节地址 a [B]。 |
| `SramAccess` | `length_bytes` | `int` | B | 逻辑有效字节 D [B]；允许零请求。 |
| `SramAccess` | `direction` | `Literal['read', 'write']` | —（结构/对象） | 读或写；写掩码能力由 SRAM profile 声明。 |
| `SramService` | `logical_read_bytes` | `int` | B | 读请求有效字节之和 [B]。 |
| `SramService` | `logical_write_bytes` | `int` | B | 写请求有效字节之和 [B]。 |
| `SramService` | `bank_reads` | `tuple[int, ...]` | word transaction | 每 bank 的整字读事务 [word transaction]。 |
| `SramService` | `bank_writes` | `tuple[int, ...]` | word transaction | 每 bank 的整字/掩码写事务 [word transaction]。 |
| `SramService` | `read_service_bytes` | `int` | B | sum(bank_reads)*word_bytes [B]；含读放大。 |
| `SramService` | `write_service_bytes` | `int` | B | sum(bank_writes)*word_bytes [B]；写掩码仍占一次整字服务。 |
| `SramService` | `bank_issue_groups` | `tuple[int, ...]` | group | 独立端口 max(ceil(R/Pr),ceil(W/Pw)) 或共享 ceil((R+W)/P) [group]。 |
| `SramService` | `completion_cycles` | `int` | cycle | max_bank(L+(groups-1)*II) [cycle]；空工作为零。 |
| `SramService` | `completion_time_s` | `float` | s | completion_cycles/f_sram [s]。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `SramAccess` | 每个请求独立触及其覆盖的 word；重复访问按实际次数计量。 |
| `SramService` | 所有请求起点就绪时的隔离服务；也是忽略因果依赖后的必要服务条件。 |
| `analyze_sram(p: SramParams, clock: ClockDomain, accesses: tuple[SramAccess, ...])` | 非对齐读触及全部覆盖 word；写只在声明 byte-enable 时允许部分 word。 |

### [bank.py](bank.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `SramParams` | `bank_count` | `int` | bank | 独立存储 bank 数 B [bank]。 |
| `SramParams` | `words_per_bank` | `int` | word/bank | 每 bank 数据字数 W [word/bank]。 |
| `SramParams` | `word_bits` | `int` | bit/word | 每数据字位宽 D [bit/word]；必须是 8 的倍数。 |
| `SramParams` | `read_ports_per_bank` | `int` | port/bank | 每 bank 独立读端口数 [port/bank]。 |
| `SramParams` | `write_ports_per_bank` | `int` | port/bank | 每 bank 独立写端口数 [port/bank]。 |
| `SramParams` | `access_ii_cycles` | `int` | cycle | 每端口的访问发起间隔 II [cycle]。 |
| `SramParams` | `shared_rw_ports_per_bank` | `int` | port/bank | 共用读写端口 [port/bank]；不能同时配置独立 R/W。 |
| `SramParams` | `access_latency_cycles` | `int` | cycle | 单 word 访问完成延迟 L [cycle]；默认理想单周期。 |
| `SramParams` | `supports_byte_write` | `bool` | 1（布尔） | 是否提供逐字节写使能；否则拒绝非整字写。 |
| `SramParams` | `capacity_bytes` | `int` | B | 只读派生属性；数据容量 B*W*D/8 [B]；不含 ECC、冗余及外围面积。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `SramParams` | B 个 bank，每 bank W 个数据字；独立 R/W 与共享 RW 二选一。 |
| `SramParams.capacity_bytes` | 数据容量 B*W*D/8 [B]；不含 ECC、冗余及外围面积。 |
| `SramParams.bank_for_address(self, address_bytes: int)` | 低位 word-interleaving：bank=floor(address/word_bytes) mod bank_count。 |
| `peak_sram_bandwidth(p: SramParams, clock: ClockDomain, *, write: bool)` | 全 bank 均匀供数时的单方向上限 B*ports*word_bytes*f/II [B/s]。 |

<!-- model-fields:end -->

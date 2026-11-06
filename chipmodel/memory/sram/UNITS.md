# sram：Banked SRAM 的组织与端口

Unit 为 SramParams；存储容量是 bank_count*words_per_bank*word_bits/8。低位 word-interleaving 的 bank 为 floor(address/word_bytes) mod bank_count。这里仅分析地址与容量，不存储实际字节数组。

独立读端口与独立写端口分开，单方向峰值为 banks*ports*word_bytes*f/II。零读或写端口表示确实不支持该方向，带宽为零；至少一个方向存在。共享 1RW 端口不能用独立 1R1W 参数替代。

最关心访问粒度、bank 冲突、端口共享与实际并行度。`peak_sram_bandwidth` 假设各 bank 均匀供数，没有模拟地址轨迹、读后写时序、ECC、低功耗或外围能量。ClockDomain 必须是此 SRAM 的访问时钟。

<!-- model-fields:start -->

### [bank.py](bank.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `SramParams` | `bank_count` | `int` | bank | 独立存储 bank 数 B [bank]。 |
| `SramParams` | `words_per_bank` | `int` | word/bank | 每 bank 数据字数 W [word/bank]。 |
| `SramParams` | `word_bits` | `int` | bit/word | 每数据字位宽 D [bit/word]；必须是 8 的倍数。 |
| `SramParams` | `read_ports_per_bank` | `int` | port/bank | 每 bank 独立读端口数 [port/bank]。 |
| `SramParams` | `write_ports_per_bank` | `int` | port/bank | 每 bank 独立写端口数 [port/bank]。 |
| `SramParams` | `access_ii_cycles` | `int` | cycle | 每端口的访问发起间隔 II [cycle]。 |
| `SramParams` | `capacity_bytes` | `int` | B | 只读派生属性；数据容量 B*W*D/8 [B]；不含 ECC、冗余及外围面积。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `SramParams` | B 个 bank，每 bank W 个数据字；读写端口在本模型中物理独立。 |
| `SramParams.capacity_bytes` | 数据容量 B*W*D/8 [B]；不含 ECC、冗余及外围面积。 |
| `SramParams.bank_for_address(self, address_bytes: int)` | 低位 word-interleaving：bank=floor(address/word_bytes) mod bank_count。 |
| `peak_sram_bandwidth(p: SramParams, clock: ClockDomain, *, write: bool)` | 全 bank 均匀供数时的单方向上限 B*ports*word_bytes*f/II [B/s]。 |

<!-- model-fields:end -->

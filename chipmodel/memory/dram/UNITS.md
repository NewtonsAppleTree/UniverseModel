# dram：DDR/LPDDR/GDDR/HBM的组织、地址与接口上限

DramOrganization描述显式payload组织和有效数据率；technology只记录来源标签。每channel是独立接口，rank共享该接口；bank已经展开bank-group，column是payload-width传输位置，不是burst。

容量=channels*ranks*banks*rows*columns*payload_width/8 [B]；峰值=channels*MT/s*10^6*payload_width/8 [B/s]。5600 MT/s×64 bit/8=44.8 GB/s，不能再乘DDR的2或rank数。两个32-bit subchannel应写2×32，不能写2×64。

`decode_dram_address`采用整行连续布局：先取row_bytes=columns_per_row*payload_width_bits/8内偏移，再按row_order指定的低→高维度解析行块索引，支持非2幂bank数。只覆盖行块交织，没有XOR映射或行内channel交织；column与byte_in_column分别是传输位置及其byte偏移。

组织→地址→[DramReadProfile](../controllers/UNITS.md)→单行/span读是独立调用顺序。敏感量为容量维度、有效接口宽度、数据率、映射和实际局部性；当前请求能否利用全部channel须看地址分布。tRAS/tRC/tRRD/tFAW/tWR/tWTR/tRFC/tREFI、PHY/DFI与低功耗状态未进入执行模型；峰值不是可持续带宽。

DDR DIMM/板载布局归systemmodel，HBM堆叠归Package。HBF按Flash介质和控制路径定义，不强制套DRAM。全部24种维度排列由笛卡尔积坐标枚举验证，rank容量/共享带宽与跨channel工作见[测试](../../../tests/chipmodel/test_memory.py)；来源与合成夹具边界见[CH7指南](../../docs/memory_access.md)。

<!-- model-fields:start -->

### [organization.py](organization.py)

| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |
| --- | --- | --- | --- | --- |
| `DramOrganization` | `technology` | `str` | 1（标识/枚举） | 技术/器件 profile 名；不自动导入 JEDEC 时序。 |
| `DramOrganization` | `channel_count` | `int` | channel | 独立 channel 或 pseudo/subchannel 数 [channel]。 |
| `DramOrganization` | `ranks_per_channel` | `int` | rank/channel | 每 channel 共享总线的 rank 数 [rank/channel]。 |
| `DramOrganization` | `banks_per_rank` | `int` | bank/rank | 每 rank 的 bank 总数，已含 bank-group 展开 [bank/rank]。 |
| `DramOrganization` | `rows_per_bank` | `int` | row/bank | 每 bank 行数 [row/bank]。 |
| `DramOrganization` | `columns_per_row` | `int` | column/row | 每行 payload-width 数据位置数 [column/row]；不是 burst 数。 |
| `DramOrganization` | `payload_width_bits` | `int` | bit/transfer | 每 channel 每次传输的有效数据宽度 [bit/transfer]，排除 ECC。 |
| `DramOrganization` | `data_rate_mt_s` | `float` | MT/s | 已含 DDR 边沿因素的有效传输率 [MT/s]。 |
| `DramOrganization` | `row_bytes` | `int` | B/row | 只读派生属性；单bank行的有效数据量 columns*payload_width/8 [B/row]。 |
| `DramOrganization` | `capacity_bytes` | `int` | B | 只读派生属性；组织容量 channels*ranks*banks*rows*columns*payload_width/8 [B]。 |
| `DramOrganization` | `peak_bandwidth_bytes_per_s` | `float` | B/s | 只读派生属性；接口峰值 channels*MT/s*10^6*payload_width/8 [B/s]；不再乘 DDR 系数或 rank 数。 |
| `DramAddress` | `channel` | `int` | channel | 独立数据接口索引 [channel]。 |
| `DramAddress` | `rank` | `int` | rank | 共享该接口的rank索引 [rank]。 |
| `DramAddress` | `bank` | `int` | bank | rank内已展开bank-group的bank索引 [bank]。 |
| `DramAddress` | `row` | `int` | row | bank内行号 [row]。 |
| `DramAddress` | `column` | `int` | column | 行内payload-width传输位置 [column]。 |
| `DramAddress` | `byte_in_column` | `int` | B | 一次有效数据传输内的byte偏移 [B]。 |
| `DramAddress` | `row_offset_bytes` | `int` | B | 行内有效数据偏移 [B]。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `DramOrganization` | 每个 channel 是独立数据接口；rank 共享该接口，增加容量但不倍增接口带宽。 |
| `DramOrganization.row_bytes` | 单bank行的有效数据量 columns*payload_width/8 [B/row]。 |
| `DramOrganization.capacity_bytes` | 组织容量 channels*ranks*banks*rows*columns*payload_width/8 [B]。 |
| `DramOrganization.peak_bandwidth_bytes_per_s` | 接口峰值 channels*MT/s*10^6*payload_width/8 [B/s]；不再乘 DDR 系数或 rank 数。 |
| `DramAddress` | 一条行内byte地址的组织坐标；没有实际open-row状态。 |
| `validate_row_order(row_order: tuple[str, ...])` | row_order按低位到高位排列完整行的混合进制维度；不支持行内channel交织或XOR哈希。 |
| `decode_dram_address(p: DramOrganization, address_bytes: int, *, row_order: tuple[str, ...]=('bank', 'row', 'rank', 'channel'))` | 完整行连续映射，先分离byte/column，再按显式维度顺序解码，无2幂尺寸要求。 |

<!-- model-fields:end -->

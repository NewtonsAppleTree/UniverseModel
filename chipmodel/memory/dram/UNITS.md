# dram：DDR/LPDDR/GDDR/HBM 的组织与接口上限

DramOrganization 只描述显式 payload 组织和有效数据率；technology 是来源标签。每个 channel 是一条独立接口，多个 rank 共享该接口。bank 数已经展开 bank-group；column 是每次 payload-width 数据的位置，不是 burst。

容量=channels*ranks*banks*rows*columns*payload_width/8 [B]。峰值=channels*MT/s*10^6*payload_width/8 [B/s]。5600 MT/s×64 bit/8=44.8 GB/s；不能再乘 DDR 的 2，不能因增加 rank 数再乘接口带宽。若采用两个 32-bit subchannel，应输入 2×32，而非 2×64。

最关心容量组织、有效接口宽度、访问局部性与刷新/转向。读路径连接 [controller](../controllers/UNITS.md)。tRAS/tRC/tRRD/tFAW/tWR/tWTR/tRFC/tREFI、PHY 训练、DFI 比例、低功耗状态尚未进入执行模型；器件 profile 应保留这些真实约束，不能把接口峰值当可持续带宽。

DDR DIMM/板载布局归 systemmodel；HBM 堆叠归 Package 组合。HBF 没有在此强制当作 DRAM，需按实际 Flash 介质和控制路径定义。

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
| `DramOrganization` | `capacity_bytes` | `int` | B | 只读派生属性；组织容量 channels*ranks*banks*rows*columns*payload_width/8 [B]。 |
| `DramOrganization` | `peak_bandwidth_bytes_per_s` | `float` | B/s | 只读派生属性；接口峰值 channels*MT/s*10^6*payload_width/8 [B/s]；不再乘 DDR 系数或 rank 数。 |

| 类型 / 接口 | 用途、公式与边界 |
| --- | --- |
| `DramOrganization` | 每个 channel 是独立数据接口；rank 共享该接口，增加容量但不倍增接口带宽。 |
| `DramOrganization.capacity_bytes` | 组织容量 channels*ranks*banks*rows*columns*payload_width/8 [B]。 |
| `DramOrganization.peak_bandwidth_bytes_per_s` | 接口峰值 channels*MT/s*10^6*payload_width/8 [B/s]；不再乘 DDR 系数或 rank 数。 |

<!-- model-fields:end -->

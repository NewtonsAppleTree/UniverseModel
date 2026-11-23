"""DDR/LPDDR/GDDR/HBM 的显式组织与接口上限；技术标签不提供隐式参数。"""

from dataclasses import dataclass
from fractions import Fraction

from chipmodel.common import count, finite_fraction, identifier, positive, typed_tuple


# 每个 channel 是独立数据接口；rank 共享该接口，增加容量但不倍增接口带宽。
@dataclass(frozen=True, slots=True, kw_only=True)
class DramOrganization:
    technology: str  # 技术/器件 profile 名；不自动导入 JEDEC 时序。
    channel_count: int  # 独立 channel 或 pseudo/subchannel 数 [channel]。
    ranks_per_channel: int  # 每 channel 共享总线的 rank 数 [rank/channel]。
    banks_per_rank: int  # 每 rank 的 bank 总数，已含 bank-group 展开 [bank/rank]。
    rows_per_bank: int  # 每 bank 行数 [row/bank]。
    columns_per_row: int  # 每行 payload-width 数据位置数 [column/row]；不是 burst 数。
    payload_width_bits: int  # 每 channel 每次传输的有效数据宽度 [bit/transfer]，排除 ECC。
    data_rate_mt_s: float  # 已含 DDR 边沿因素的有效传输率 [MT/s]。

    # 数据位宽按 byte 对齐；technology 仅记录身份，不假定通用速率/时钟比例。
    def __post_init__(self) -> None:
        identifier("technology", self.technology)
        for name in ("channel_count", "ranks_per_channel", "banks_per_rank", "rows_per_bank",
                     "columns_per_row", "payload_width_bits"):
            count(name, getattr(self, name))
        if self.payload_width_bits % 8:
            raise ValueError("payload_width_bits must be byte aligned")
        object.__setattr__(self, "data_rate_mt_s", positive("data_rate_mt_s", self.data_rate_mt_s))

    # 单bank行的有效数据量 columns*payload_width/8 [B/row]。
    @property
    def row_bytes(self) -> int:
        return self.columns_per_row * (self.payload_width_bits // 8)

    # 组织容量 channels*ranks*banks*rows*columns*payload_width/8 [B]。
    @property
    def capacity_bytes(self) -> int:
        return (self.channel_count * self.ranks_per_channel * self.banks_per_rank
                * self.rows_per_bank * self.columns_per_row * (self.payload_width_bits // 8))

    # 接口峰值 channels*MT/s*10^6*payload_width/8 [B/s]；不再乘 DDR 系数或 rank 数。
    @property
    def peak_bandwidth_bytes_per_s(self) -> float:
        return finite_fraction("peak_bandwidth_bytes_per_s", self.channel_count * Fraction(self.data_rate_mt_s)
                               * 1_000_000 * (self.payload_width_bits // 8))


# 一条行内byte地址的组织坐标；没有实际open-row状态。
@dataclass(frozen=True, slots=True)
class DramAddress:
    channel: int  # 独立数据接口索引 [channel]。
    rank: int  # 共享该接口的rank索引 [rank]。
    bank: int  # rank内已展开bank-group的bank索引 [bank]。
    row: int  # bank内行号 [row]。
    column: int  # 行内payload-width传输位置 [column]。
    byte_in_column: int  # 一次有效数据传输内的byte偏移 [B]。
    row_offset_bytes: int  # 行内有效数据偏移 [B]。


# row_order按低位到高位排列完整行的混合进制维度；不支持行内channel交织或XOR哈希。
def validate_row_order(row_order: tuple[str, ...]) -> tuple[str, ...]:
    order = typed_tuple("row_order", row_order, str)
    if len(order) != 4 or set(order) != {"channel", "rank", "bank", "row"}:
        raise ValueError("row_order must contain channel, rank, bank, row exactly once")
    return order


# 完整行连续映射，先分离byte/column，再按显式维度顺序解码，无2幂尺寸要求。
def decode_dram_address(p: DramOrganization, address_bytes: int, *,
                        row_order: tuple[str, ...] = ("bank", "row", "rank", "channel")) -> DramAddress:
    if not isinstance(p, DramOrganization):
        raise TypeError("p must be DramOrganization")
    count("address_bytes", address_bytes, 0)
    order = validate_row_order(row_order)
    if address_bytes >= p.capacity_bytes:
        raise ValueError("DRAM address outside capacity")
    index, offset = divmod(address_bytes, p.row_bytes)
    sizes = {"channel": p.channel_count, "rank": p.ranks_per_channel, "bank": p.banks_per_rank, "row": p.rows_per_bank}
    coordinates = {}
    for dimension in order:
        index, coordinates[dimension] = divmod(index, sizes[dimension])
    column, byte = divmod(offset, p.payload_width_bits // 8)
    return DramAddress(coordinates["channel"], coordinates["rank"], coordinates["bank"], coordinates["row"], column, byte, offset)

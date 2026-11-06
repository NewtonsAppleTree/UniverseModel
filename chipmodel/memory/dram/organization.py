"""DDR/LPDDR/GDDR/HBM 的显式组织与接口上限；技术标签不提供隐式参数。"""

from dataclasses import dataclass

from chipmodel.common import count, identifier, positive


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
        positive("data_rate_mt_s", self.data_rate_mt_s)

    # 组织容量 channels*ranks*banks*rows*columns*payload_width/8 [B]。
    @property
    def capacity_bytes(self) -> int:
        return (self.channel_count * self.ranks_per_channel * self.banks_per_rank
                * self.rows_per_bank * self.columns_per_row * (self.payload_width_bits // 8))

    # 接口峰值 channels*MT/s*10^6*payload_width/8 [B/s]；不再乘 DDR 系数或 rank 数。
    @property
    def peak_bandwidth_bytes_per_s(self) -> float:
        return positive("peak_bandwidth_bytes_per_s", self.channel_count * self.data_rate_mt_s
                        * 1e6 * (self.payload_width_bits // 8))

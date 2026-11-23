"""Banked SRAM 组织；独立 R/W 或共享 RW 端口，访问分析见 access.py。"""

from dataclasses import dataclass

from chipmodel.common import ClockDomain, count, positive


# B 个 bank，每 bank W 个数据字；独立 R/W 与共享 RW 二选一。
@dataclass(frozen=True, slots=True, kw_only=True)
class SramParams:
    bank_count: int  # 独立存储 bank 数 B [bank]。
    words_per_bank: int  # 每 bank 数据字数 W [word/bank]。
    word_bits: int  # 每数据字位宽 D [bit/word]；必须是 8 的倍数。
    read_ports_per_bank: int  # 每 bank 独立读端口数 [port/bank]。
    write_ports_per_bank: int  # 每 bank 独立写端口数 [port/bank]。
    access_ii_cycles: int  # 每端口的访问发起间隔 II [cycle]。
    shared_rw_ports_per_bank: int = 0  # 共用读写端口 [port/bank]；不能同时配置独立 R/W。
    access_latency_cycles: int = 1  # 单 word 访问完成延迟 L [cycle]；默认理想单周期。
    supports_byte_write: bool = False  # 是否提供逐字节写使能；否则拒绝非整字写。

    # 数据容量与端口数合法；不把共享 1RW 端口默认为独立 1R1W。
    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            if name != "supports_byte_write":
                count(name, getattr(self, name), 0 if "ports" in name else 1)
        if type(self.supports_byte_write) is not bool:
            raise TypeError("supports_byte_write must be bool")
        if self.word_bits % 8:
            raise ValueError("word_bits must be byte aligned")
        dedicated = self.read_ports_per_bank + self.write_ports_per_bank
        if dedicated and self.shared_rw_ports_per_bank:
            raise ValueError("choose independent R/W or shared RW ports, not both")
        if dedicated + self.shared_rw_ports_per_bank == 0:
            raise ValueError("SRAM needs at least one access port")

    # 数据容量 B*W*D/8 [B]；不含 ECC、冗余及外围面积。
    @property
    def capacity_bytes(self) -> int:
        return self.bank_count * self.words_per_bank * (self.word_bits // 8)

    # 低位 word-interleaving：bank=floor(address/word_bytes) mod bank_count。
    def bank_for_address(self, address_bytes: int) -> int:
        count("address_bytes", address_bytes, 0)
        if address_bytes >= self.capacity_bytes:
            raise ValueError("address_bytes outside SRAM capacity")
        return (address_bytes // (self.word_bits // 8)) % self.bank_count


# 全 bank 均匀供数时的单方向上限 B*ports*word_bytes*f/II [B/s]。
def peak_sram_bandwidth(p: SramParams, clock: ClockDomain, *, write: bool) -> float:
    if type(write) is not bool:
        raise TypeError("write must be bool")
    ports = (p.write_ports_per_bank if write else p.read_ports_per_bank) + p.shared_rw_ports_per_bank
    if ports == 0:
        return 0.0
    return positive("bandwidth_bytes_per_s", p.bank_count * ports * (p.word_bits // 8)
                    * clock.frequency_hz / p.access_ii_cycles)

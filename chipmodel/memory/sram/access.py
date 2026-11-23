"""有限地址请求的整字服务账本；没有存储内容、队列或跨请求合并。"""

from dataclasses import dataclass
from typing import Literal

from chipmodel.common import ClockDomain, ceil_div, count, identifier, typed_tuple
from chipmodel.memory.sram.bank import SramParams


# 每个请求独立触及其覆盖的 word；重复访问按实际次数计量。
@dataclass(frozen=True, slots=True, kw_only=True)
class SramAccess:
    request_id: str  # 本批唯一访问身份。
    address_bytes: int  # SRAM 本地字节地址 a [B]。
    length_bytes: int  # 逻辑有效字节 D [B]；允许零请求。
    direction: Literal["read", "write"]  # 读或写；写掩码能力由 SRAM profile 声明。

    # 地址与长度非负，方向明确；容量检查属于资源绑定阶段。
    def __post_init__(self) -> None:
        identifier("request_id", self.request_id)
        count("address_bytes", self.address_bytes, 0)
        count("length_bytes", self.length_bytes, 0)
        if self.direction not in ("read", "write"):
            raise ValueError("direction must be read or write")


# 所有请求起点就绪时的隔离服务；也是忽略因果依赖后的必要服务条件。
@dataclass(frozen=True, slots=True)
class SramService:
    logical_read_bytes: int  # 读请求有效字节之和 [B]。
    logical_write_bytes: int  # 写请求有效字节之和 [B]。
    bank_reads: tuple[int, ...]  # 每 bank 的整字读事务 [word transaction]。
    bank_writes: tuple[int, ...]  # 每 bank 的整字/掩码写事务 [word transaction]。
    read_service_bytes: int  # sum(bank_reads)*word_bytes [B]；含读放大。
    write_service_bytes: int  # sum(bank_writes)*word_bytes [B]；写掩码仍占一次整字服务。
    bank_issue_groups: tuple[int, ...]  # 独立端口 max(ceil(R/Pr),ceil(W/Pw)) 或共享 ceil((R+W)/P) [group]。
    completion_cycles: int  # max_bank(L+(groups-1)*II) [cycle]；空工作为零。
    completion_time_s: float  # completion_cycles/f_sram [s]。


# 连续 word 范围对 bank 取模；O(bank_count)，无需枚举每一个 word。
def _bank_counts(first: int, words: int, banks: int) -> tuple[int, ...]:
    full, tail = divmod(words, banks)
    return tuple(full + ((bank - first) % banks < tail) for bank in range(banks))


# 非对齐读触及全部覆盖 word；写只在声明 byte-enable 时允许部分 word。
def analyze_sram(p: SramParams, clock: ClockDomain, accesses: tuple[SramAccess, ...]) -> SramService:
    if not isinstance(p, SramParams) or not isinstance(clock, ClockDomain):
        raise TypeError("SRAM params and clock required")
    accesses = typed_tuple("accesses", accesses, SramAccess)
    if len({a.request_id for a in accesses}) != len(accesses):
        raise ValueError("duplicate SRAM request_id")
    reads, writes = [0] * p.bank_count, [0] * p.bank_count
    logical = {"read": 0, "write": 0}
    word = p.word_bits // 8
    for access in accesses:
        address, length = access.address_bytes, access.length_bytes
        if address + length > p.capacity_bytes:
            raise ValueError("SRAM access outside capacity")
        if not length:
            continue
        ports = p.read_ports_per_bank if access.direction == "read" else p.write_ports_per_bank
        if not ports + p.shared_rw_ports_per_bank:
            raise ValueError("SRAM direction has no port")
        if access.direction == "write" and not p.supports_byte_write and (address % word or length % word):
            raise ValueError("partial word write requires byte-enable profile")
        logical[access.direction] += length
        first = address // word
        words = (address + length - 1) // word - first + 1
        target = reads if access.direction == "read" else writes
        for bank, transactions in enumerate(_bank_counts(first, words, p.bank_count)):
            target[bank] += transactions
    groups = tuple(ceil_div(r + w, p.shared_rw_ports_per_bank) if p.shared_rw_ports_per_bank else
                   max(ceil_div(r, p.read_ports_per_bank) if r else 0,
                       ceil_div(w, p.write_ports_per_bank) if w else 0) for r, w in zip(reads, writes))
    cycles = max((p.access_latency_cycles + (g - 1) * p.access_ii_cycles if g else 0 for g in groups), default=0)
    return SramService(logical["read"], logical["write"], tuple(reads), tuple(writes),
                       sum(reads) * word, sum(writes) * word, groups, cycles, clock.seconds(cycles))

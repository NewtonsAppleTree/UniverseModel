"""Set-associative cache 的容量与地址位划分；不预测命中率或 MSHR 行为。"""

from dataclasses import dataclass

from chipmodel.common import count


# 地址分为 tag/index/offset；sets 和 line_bytes 为 2 的幂。
@dataclass(frozen=True, slots=True, kw_only=True)
class CacheGeometry:
    sets: int  # Set 数 S [set]。
    ways: int  # 每 set 相联路数 A [line/set]。
    line_bytes: int  # Cache-line 数据大小 B [B/line]。
    address_bits: int  # 此 cache 实际使用的地址宽度 [bit]。
    status_bits_per_line: int  # 显式状态位预算，如 valid/dirty [bit/line]。

    # 保证地址划分合法；不默认特定替换策略、ECC 或物理 tag 方案。
    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            count(name, getattr(self, name), 0 if name == "status_bits_per_line" else 1)
        if self.sets & (self.sets - 1) or self.line_bytes & (self.line_bytes - 1):
            raise ValueError("sets and line_bytes must be powers of two")
        if self.tag_bits < 0:
            raise ValueError("address_bits cannot hold index and offset")

    # 数据阵列容量 S*A*B [B]；标签和控制位另计。
    @property
    def capacity_bytes(self) -> int:
        return self.sets * self.ways * self.line_bytes

    # Tag 宽度=address_bits−log2(S)−log2(B) [bit/line]。
    @property
    def tag_bits(self) -> int:
        return self.address_bits - (self.sets.bit_length() - 1) - (self.line_bytes.bit_length() - 1)

    # 标签与显式状态的总存储量 [bit]；不含替换元数据或 ECC。
    @property
    def metadata_bits(self) -> int:
        return self.sets * self.ways * (self.tag_bits + self.status_bits_per_line)

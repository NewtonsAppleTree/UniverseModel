"""NAND 的 page/block/plane/die 组织；不把 page program 等价为任意字节覆盖。"""

from dataclasses import dataclass

from chipmodel.common import count, positive, real


# NAND 介质几何；数据容量与 spare/OOB 字节分开。
@dataclass(frozen=True, slots=True, kw_only=True)
class NandGeometry:
    page_data_bytes: int  # 每页可用数据 [B/page]。
    page_spare_bytes: int  # 每页 OOB/spare [B/page]，可能用于 ECC/管理。
    pages_per_block: int  # 擦除块包含的页数 [page/block]。
    blocks_per_plane: int  # 每 plane 的块数 [block/plane]。
    planes_per_die: int  # 每 die 的 plane 数 [plane/die]。
    die_count: int  # NAND die 数 [die]；不自动代表全部可并行。

    # 几何计数合法；允许无 spare 的简化输入。
    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            count(name, getattr(self, name), 0 if name == "page_spare_bytes" else 1)

    # 页总数 pages/block*blocks/plane*planes/die*dies [page]。
    @property
    def page_count(self) -> int:
        return self.pages_per_block * self.blocks_per_plane * self.planes_per_die * self.die_count

    # 原始数据容量 page_count*page_data_bytes [B]；未扣坏块、FTL 预留和 overprovisioning。
    @property
    def raw_data_bytes(self) -> int:
        return self.page_count * self.page_data_bytes

    # 物理保留字节包含 spare：[data+spare]*page_count [B]。
    @property
    def raw_total_bytes(self) -> int:
        return self.page_count * (self.page_data_bytes + self.page_spare_bytes)


# 一条串行介质路径的已特征化时延；读/写/擦除分别对应不同粒度。
@dataclass(frozen=True, slots=True, kw_only=True)
class NandTiming:
    page_read_s: float  # 单次 page read 服务时间 [s/page]。
    page_program_s: float  # 单次 page program 服务时间 [s/page]。
    block_erase_s: float  # 单次 block erase 服务时间 [s/block]。

    # 物理时间必须显式为正；未知值不填零。
    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            positive(name, getattr(self, name))

    # T=N*t_operation [s]；N 对 read/program 为 page 数，对 erase 为 block 数。
    def estimate_serial(self, operation: str, operation_count: int) -> float:
        count("operation_count", operation_count, 0)
        times = {"read": self.page_read_s, "program": self.page_program_s, "erase": self.block_erase_s}
        if operation not in times:
            raise ValueError("operation must be read, program or erase")
        return real("service_time_s", operation_count * times[operation], minimum=0)

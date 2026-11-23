"""NAND 的 page/block/plane/die 组织；不把 page program 等价为任意字节覆盖。"""

from dataclasses import dataclass
from fractions import Fraction

from chipmodel.common import count, finite_fraction, identifier, positive, real, typed_tuple


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
            object.__setattr__(self, name, positive(name, getattr(self, name)))

    # T=N*t_operation [s]；N 对 read/program 为 page 数，对 erase 为 block 数。
    def estimate_serial(self, operation: str, operation_count: int) -> float:
        count("operation_count", operation_count, 0)
        times = {"read": self.page_read_s, "program": self.page_program_s, "erase": self.block_erase_s}
        if operation not in times:
            raise ValueError("operation must be read, program or erase")
        return finite_fraction("service_time_s", operation_count * Fraction(times[operation]))


# 单die、单页缓冲、串行读取路径；阵列page service与外部data/OOB传输分别计量。
@dataclass(frozen=True, slots=True, kw_only=True)
class NandReadProfile:
    geometry: NandGeometry  # 本路径仅支持一个die，plane不隐含并行。
    timing: NandTiming  # page_read_s只计阵列→页缓冲，program/erase不用于读取。
    output_bytes_per_s: float | None  # 外部输出有效字节速率 [B/s]；None表示未知。
    command_overhead_s: float | None  # 每非空请求的命令/地址总开销 [s]；0须为显式理想假设。
    profile_source: str  # 器件特征或合成实验来源及适用条件。

    # 缓冲容量固定为一个完整物理page；未知接口/命令成本不默认为零。
    def __post_init__(self) -> None:
        if not isinstance(self.geometry, NandGeometry) or not isinstance(self.timing, NandTiming):
            raise TypeError("NAND geometry and timing required")
        if self.geometry.die_count != 1:
            raise ValueError("NAND read path models exactly one die; no implicit die parallelism")
        identifier("profile_source", self.profile_source)
        if self.output_bytes_per_s is not None:
            object.__setattr__(self, "output_bytes_per_s", positive("output_bytes_per_s", self.output_bytes_per_s))
        if self.command_overhead_s is not None:
            object.__setattr__(self, "command_overhead_s", real("command_overhead_s", self.command_overhead_s, minimum=0))


# 页号和data/OOB列范围各自独立；不把spare当作可用数据容量。
@dataclass(frozen=True, slots=True, kw_only=True)
class NandReadRequest:
    request_id: str  # 批内唯一读取身份。
    page_index: int  # 物理页号 [page]，范围由profile约束。
    data_offset_bytes: int = 0  # 数据区起始列 [B]。
    data_bytes: int = 0  # 输出数据区字节数 [B]。
    spare_offset_bytes: int = 0  # OOB区起始列 [B]。
    spare_bytes: int = 0  # 输出OOB字节数 [B]，不隐含ECC计算。

    # 只校验输入计数；与页几何的绑定在读取入口完成。
    def __post_init__(self) -> None:
        identifier("request_id", self.request_id)
        for name in ("page_index", "data_offset_bytes", "data_bytes", "spare_offset_bytes", "spare_bytes"):
            count(name, getattr(self, name), 0)


# 显式页缓冲快照；只描述哪个page有效，不携带数据值或器件隐藏状态。
@dataclass(frozen=True, slots=True, kw_only=True)
class NandReadState:
    profile: NandReadProfile  # 快照绑定的完整profile；恢复时禁止跨profile复用。
    buffered_page: int | None = None  # 有效物理页号 [page]；None为冷缓冲。

    # 初态为调用方声明的已加载page；不代表此前加载没有成本。
    def __post_init__(self) -> None:
        if not isinstance(self.profile, NandReadProfile):
            raise TypeError("state requires NandReadProfile")
        if self.buffered_page is not None:
            count("buffered_page", self.buffered_page, 0)
            if self.buffered_page >= self.profile.geometry.page_count:
                raise ValueError("buffered NAND page outside geometry")


# 单请求服务分项；空请求不触发page读取、命令或传输。
@dataclass(frozen=True, slots=True)
class NandReadStep:
    request_id: str  # 输入读取身份。
    page_buffer_hit: bool | None  # 非空请求的页缓冲命中；空请求为None。
    array_read_pages: int  # 本步阵列读取次数 [page]，miss为1。
    array_loaded_bytes: int  # miss*(page_data_bytes+page_spare_bytes) [B]。
    data_output_bytes: int  # 外部数据区输出 [B]。
    spare_output_bytes: int  # 外部OOB输出 [B]。
    array_service_s: float  # array_read_pages*page_read_s [s]。
    output_service_s: float | None  # (data+OOB)/output_rate [s]；有工作且速率未知时为None。
    command_service_s: float | None  # 非空请求的命令成本 [s]；缺失时为None。


# 同一die串行策略的分析结果；完整时间只在所有分项已知时成立。
@dataclass(frozen=True, slots=True)
class NandReadAnalysis:
    steps: tuple[NandReadStep, ...]  # 请求顺序的逐项服务与命中结果。
    final_state: NandReadState  # 最终缓冲page；可显式恢复。
    array_read_pages: int  # 实际阵列读取总数 [page]。
    data_output_bytes: int  # 累计外部data输出 [B]。
    spare_output_bytes: int  # 累计外部OOB输出 [B]。
    known_service_s: float  # 串行已知分项之和 [s]；缺项时只是条件下界。
    modeled_time_s: float | None  # 无重叠串行策略的总分析时间 [s]；缺项时未知。
    unknown_costs: tuple[str, ...]  # 已触及的缺失接口或命令成本，不以零替代。


# miss整页加载，hit只读输出列；前一请求完成后才开始下一条，没有die/plane并行推断。
def analyze_nand_reads(profile: NandReadProfile, requests: tuple[NandReadRequest, ...], *,
                       initial_state: NandReadState | None = None) -> NandReadAnalysis:
    if not isinstance(profile, NandReadProfile):
        raise TypeError("profile must be NandReadProfile")
    requests = typed_tuple("requests", requests, NandReadRequest)
    if len({r.request_id for r in requests}) != len(requests):
        raise ValueError("duplicate NAND request_id")
    state = NandReadState(profile=profile) if initial_state is None else initial_state
    if not isinstance(state, NandReadState) or state.profile != profile:
        raise ValueError("NAND initial state/profile mismatch")
    page, steps, known, unknown = state.buffered_page, [], Fraction(0), set()
    g = profile.geometry
    for request in requests:
        if (request.page_index >= g.page_count or request.data_offset_bytes + request.data_bytes > g.page_data_bytes
                or request.spare_offset_bytes + request.spare_bytes > g.page_spare_bytes):
            raise ValueError("NAND page/data/OOB range outside geometry")
        output = request.data_bytes + request.spare_bytes
        hit = page == request.page_index if output else None
        reads = int(bool(output) and not hit)
        array = reads * Fraction(profile.timing.page_read_s)
        transfer = (Fraction(output) / Fraction(profile.output_bytes_per_s) if profile.output_bytes_per_s is not None else None) if output else Fraction(0)
        command = (Fraction(profile.command_overhead_s) if profile.command_overhead_s is not None else None) if output else Fraction(0)
        if transfer is None:
            unknown.add("NAND external output rate is unknown")
        if command is None:
            unknown.add("NAND per-request command/address overhead is unknown")
        known += array + (transfer if transfer is not None else 0) + (command if command is not None else 0)
        steps.append(NandReadStep(request.request_id, hit, reads, reads * (g.page_data_bytes + g.page_spare_bytes),
                                  request.data_bytes, request.spare_bytes, finite_fraction("array service", array),
                                  finite_fraction("output service", transfer) if transfer is not None else None,
                                  finite_fraction("command service", command) if command is not None else None))
        if output:
            page = request.page_index
    duration = finite_fraction("NAND known serial service", known)
    return NandReadAnalysis(tuple(steps), NandReadState(profile=profile, buffered_page=page),
                            sum(s.array_read_pages for s in steps), sum(s.data_output_bytes for s in steps),
                            sum(s.spare_output_bytes for s in steps), duration, None if unknown else duration, tuple(sorted(unknown)))

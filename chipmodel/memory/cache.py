"""Set-associative cache几何及显式LRU访问轨迹；不从几何推断命中率或时序。"""

from dataclasses import dataclass

from chipmodel.common import count, identifier, typed_tuple
from chipmodel.memory.access import MemoryAccess


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


# 固定可验证策略：精确LRU、write-back/write-allocate；几何本身不携带命中率。
@dataclass(frozen=True, slots=True, kw_only=True)
class CacheParams:
    geometry: CacheGeometry  # 数据/tag容量与地址划分；至少包含valid和dirty两个状态bit。
    profile_source: str  # 策略/几何来源或实验假设，不代表电路校准。
    policy: str = "lru-write-back-write-allocate/v1"  # 所有miss整行读入，写命中置dirty；不优化整行覆盖写。

    # 限定策略语义和状态位预算；替换元数据的物理成本不由两个状态位代替。
    def __post_init__(self) -> None:
        if not isinstance(self.geometry, CacheGeometry):
            raise TypeError("geometry must be CacheGeometry")
        identifier("profile_source", self.profile_source)
        if self.policy != "lru-write-back-write-allocate/v1" or self.geometry.status_bits_per_line < 2:
            raise ValueError("cache requires supported policy and valid/dirty bit budget")


# 可恢复的元数据状态；每set按LRU→MRU保存有效行，未出现的set为空。
@dataclass(frozen=True, slots=True, kw_only=True)
class CacheState:
    params: CacheParams  # 状态绑定的几何/策略/来源，恢复时须完全一致。
    lru_lines: tuple[int, ...] = ()  # 有效行的对齐byte地址 [B]；跨set顺序无语义，set内为LRU→MRU。
    dirty_lines: tuple[int, ...] = ()  # dirty行地址 [B]，必须为有效行的子集。

    # 拒绝重复、越界、未对齐、超相联度或无有效行的dirty状态。
    def __post_init__(self) -> None:
        if not isinstance(self.params, CacheParams):
            raise TypeError("state requires CacheParams")
        g, occupancy = self.params.geometry, {}
        for name in ("lru_lines", "dirty_lines"):
            values = typed_tuple(name, getattr(self, name), int)
            for address in values:
                count(name, address, 0)
                if address % g.line_bytes or address >= 1 << g.address_bits:
                    raise ValueError("cache state line is unaligned or outside address width")
            if len(set(values)) != len(values):
                raise ValueError("duplicate cache state line")
            object.__setattr__(self, name, values)
        for address in self.lru_lines:
            index = address // g.line_bytes % g.sets
            occupancy[index] = occupancy.get(index, 0) + 1
        if max(occupancy.values(), default=0) > g.ways or not set(self.dirty_lines) <= set(self.lru_lines):
            raise ValueError("cache state exceeds ways or has nonresident dirty line")


# 每次行触及的结果；跨行请求可产生多个hit/miss，不能当作原请求命中率。
@dataclass(frozen=True, slots=True)
class CacheTouch:
    request_id: str  # 来源访问身份。
    line_address_bytes: int  # 触及行的起始byte地址 [B]。
    set_index: int  # (address/line_bytes) mod sets。
    hit: bool  # 此次触及前该行是否有效驻留。
    evicted_line_address_bytes: int | None  # 被替换行起始地址 [B]；未替换为None。
    dirty_eviction: bool  # 被替换行是否需要整行写回。


# 功能元数据与外存事务；不提供数据值、lookup时序、MSHR或一致性模型。
@dataclass(frozen=True, slots=True)
class CacheTrace:
    touches: tuple[CacheTouch, ...]  # 按原访问及行地址顺序的功能轨迹。
    backing_accesses: tuple[MemoryAccess, ...]  # 有序整行写回/读入；dirty eviction先写再填充。
    final_state: CacheState  # 调用方显式传给下批，默认不flush。
    line_hits: int  # 命中行触及数 [touch]。
    line_misses: int  # 缺失行触及数 [touch]。
    fill_bytes: int  # miss*line_bytes [B]，含write allocate。
    writeback_bytes: int  # dirty eviction及显式flush的整行输出 [B]。
    deferred_dirty_bytes: int  # 留在最终缓存内尚未写回的dirty行数*line_bytes [B]。


# 按byte范围拆行并执行精确LRU；flush只写回并清dirty，不使有效行失效；host限制非硬件容量。
def trace_cache(params: CacheParams, accesses: tuple[MemoryAccess, ...], *, initial_state: CacheState | None = None,
                flush: bool = False, max_line_touches: int = 100_000) -> CacheTrace:
    if not isinstance(params, CacheParams):
        raise TypeError("params must be CacheParams")
    accesses = typed_tuple("accesses", accesses, MemoryAccess)
    count("max_line_touches", max_line_touches)
    if type(flush) is not bool:
        raise TypeError("flush must be bool")
    if len({a.request_id for a in accesses}) != len(accesses):
        raise ValueError("duplicate cache access request_id")
    state = CacheState(params=params) if initial_state is None else initial_state
    if not isinstance(state, CacheState) or state.params != params:
        raise ValueError("cache initial state/profile mismatch")
    g, required = params.geometry, 0
    for access in accesses:
        end = access.address_bytes + access.length_bytes
        if end > 1 << g.address_bits:
            raise ValueError("cache access outside address width")
        if access.length_bytes:
            required += (end - 1) // g.line_bytes - access.address_bytes // g.line_bytes + 1
    if required > max_line_touches:
        raise ValueError("cache line materialization exceeds host limit")
    sets, dirty, touches, backing = {}, set(state.dirty_lines), [], []
    for address in state.lru_lines:
        sets.setdefault(address // g.line_bytes % g.sets, []).append(address)
    for access in accesses:
        end = access.address_bytes + access.length_bytes
        for line in range(access.address_bytes // g.line_bytes, (end - 1) // g.line_bytes + 1) if access.length_bytes else ():
            address, index = line * g.line_bytes, line % g.sets
            residents = sets.setdefault(index, [])
            hit, evicted, was_dirty = address in residents, None, False
            if hit:
                residents.remove(address)
            else:
                if len(residents) == g.ways:
                    evicted = residents.pop(0)
                    was_dirty = evicted in dirty
                    if was_dirty:
                        dirty.remove(evicted)
                        backing.append(MemoryAccess(request_id=f"cache/{len(backing)}/writeback", address_bytes=evicted,
                                                    length_bytes=g.line_bytes, direction="write"))
                backing.append(MemoryAccess(request_id=f"cache/{len(backing)}/fill", address_bytes=address,
                                            length_bytes=g.line_bytes, direction="read"))
            residents.append(address)
            if access.direction == "write":
                dirty.add(address)
            touches.append(CacheTouch(access.request_id, address, index, hit, evicted, was_dirty))
    if flush:
        for address in sorted(dirty):
            backing.append(MemoryAccess(request_id=f"cache/{len(backing)}/flush", address_bytes=address,
                                        length_bytes=g.line_bytes, direction="write"))
        dirty.clear()
    final = CacheState(params=params, lru_lines=tuple(a for index in sorted(sets) for a in sets[index]),
                       dirty_lines=tuple(sorted(dirty)))
    hits = sum(t.hit for t in touches)
    return CacheTrace(tuple(touches), tuple(backing), final, hits, len(touches) - hits,
                      sum(a.length_bytes for a in backing if a.direction == "read"),
                      sum(a.length_bytes for a in backing if a.direction == "write"), len(dirty) * g.line_bytes)

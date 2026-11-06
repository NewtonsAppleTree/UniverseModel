"""DMA 服务需求与 TMA 地址生成；实际读/链路/写入由显式连接承担。"""

from dataclasses import dataclass
from math import prod

from chipmodel.common import ClockDomain, ceil_div, count


# 单个 DMA 通道的隔离 copy；多个通道通过多个实例表达，不自动并行一条请求。
@dataclass(frozen=True, slots=True, kw_only=True)
class DmaParams:
    bytes_per_cycle: int  # 本通道数据通路宽度 [B/cycle]。
    max_burst_bytes: int  # 单次 burst 最大 payload [B]。
    startup_cycles: int  # 每请求启动开销 [cycle]；可以为零。
    burst_overhead_cycles: int  # 每 burst 的串行控制开销 [cycle]；不包含外部存储时延。

    # Burst 大小按数据拍对齐，保证按 burst 分拆不产生隐式额外尾拍。
    def __post_init__(self) -> None:
        count("bytes_per_cycle", self.bytes_per_cycle)
        count("max_burst_bytes", self.max_burst_bytes)
        count("startup_cycles", self.startup_cycles, 0)
        count("burst_overhead_cycles", self.burst_overhead_cycles, 0)
        if self.max_burst_bytes % self.bytes_per_cycle:
            raise ValueError("max_burst_bytes must align to bytes_per_cycle")


# DMA 结果只描述该通道服务；没有 accepted/source_consumed/destination_visible 事件。
@dataclass(frozen=True, slots=True)
class DmaEstimate:
    burst_count: int  # ceil(payload_bytes/max_burst_bytes) [burst]。
    completion_cycles: int  # startup+bursts*overhead+ceil(payload/bytes_per_cycle) [cycle]。
    completion_time_s: float  # completion_cycles/f_dma [s]。


# 空请求不发起；非空请求在供数和接收无限制时按串行 burst 计算服务需求。
def estimate_dma(p: DmaParams, clock: ClockDomain, payload_bytes: int) -> DmaEstimate:
    count("payload_bytes", payload_bytes, 0)
    bursts = ceil_div(payload_bytes, p.max_burst_bytes)
    cycles = (p.startup_cycles + bursts * p.burst_overhead_cycles
              + ceil_div(payload_bytes, p.bytes_per_cycle)) if bursts else 0
    return DmaEstimate(bursts, cycles, clock.seconds(cycles))


# TMA 的一般正 stride 地址映射：addr=base+Σ index_i*stride_i；不绑定厂商指令。
@dataclass(frozen=True, slots=True, kw_only=True)
class TensorLayout:
    shape: tuple[int, ...]  # 各维 extent [element]；零维长度表示空张量。
    strides_bytes: tuple[int, ...]  # 各维地址步长 [B]；零 stride 表示广播/别名。
    element_bytes: int  # 存储元素大小 [B/element]；低比特打包需专门适配。
    base_address_bytes: int  # 所属地址域中的起始地址 [B]。

    # 冻结维度与 stride；允许非连续或重叠布局，span 不等于唯一数据量。
    def __post_init__(self) -> None:
        object.__setattr__(self, "shape", tuple(self.shape))
        object.__setattr__(self, "strides_bytes", tuple(self.strides_bytes))
        if not self.shape or len(self.shape) != len(self.strides_bytes):
            raise ValueError("shape and strides_bytes need matching nonzero rank")
        for size, stride in zip(self.shape, self.strides_bytes):
            count("shape extent", size, 0)
            count("stride_bytes", stride, 0)
        count("element_bytes", self.element_bytes)
        count("base_address_bytes", self.base_address_bytes, 0)

    # 逻辑元素存储量 product(shape)*element_bytes [B]；不扣广播重复引用。
    @property
    def logical_bytes(self) -> int:
        return prod(self.shape) * self.element_bytes

    # 从 base 到最后元素末尾的覆盖跨度 [B]，包含 stride 留出的空洞。
    @property
    def span_bytes(self) -> int:
        return (sum((size - 1) * stride for size, stride in zip(self.shape, self.strides_bytes))
                + self.element_bytes) if all(self.shape) else 0

    # 验证坐标并求字节地址；地址空间容量与权限由装配方检查。
    def address(self, indices: tuple[int, ...]) -> int:
        if len(indices) != len(self.shape):
            raise ValueError("indices rank does not match shape")
        for i, size in zip(indices, self.shape):
            count("index", i, 0)
            if i >= size:
                raise ValueError("index outside shape")
        return self.base_address_bytes + sum(i * stride for i, stride in zip(indices, self.strides_bytes))

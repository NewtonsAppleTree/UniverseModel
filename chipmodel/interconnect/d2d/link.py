"""单方向串行链路：分包、协议字节和线路编码分开计量。"""

from dataclasses import dataclass

from chipmodel.common import ceil_div, count, positive, real


# D2D/SerDes 分析参数；lane_rate 已是每 lane 线路 bit rate，不再乘 DDR 系数。
@dataclass(frozen=True, slots=True, kw_only=True)
class SerialLinkParams:
    lane_count: int  # 本方向物理 lane 数 [lane]。
    lane_rate_bps: float  # 单 lane 线路速率 [bit/s/lane]。
    coding_data_bits: int  # 每个码字承载的数据位数 [bit/codeword]。
    coding_wire_bits: int  # 每个码字在线路上的位数 [bit/codeword]。
    max_payload_bytes: int  # 单 packet 最大有效载荷 [B/packet]。
    packet_overhead_bytes: int  # 头/尾/校验等编码前开销 [B/packet]。
    fixed_latency_s: float  # 不随字节数增长的端点/传播时延 [s]。

    # 编码效率必须≤1；每 packet 独立补齐码字，禁止把协议开销当 payload。
    def __post_init__(self) -> None:
        for name in ("lane_count", "coding_data_bits", "coding_wire_bits", "max_payload_bytes"):
            count(name, getattr(self, name))
        count("packet_overhead_bytes", self.packet_overhead_bytes, 0)
        positive("lane_rate_bps", self.lane_rate_bps)
        real("fixed_latency_s", self.fixed_latency_s, minimum=0)
        if self.coding_wire_bits < self.coding_data_bits:
            raise ValueError("coding_wire_bits must be >= coding_data_bits")


# 链路计量守恒：payload+protocol bytes 经编码形成 wire bits，时间按物理速率计算。
@dataclass(frozen=True, slots=True)
class LinkEstimate:
    packet_count: int  # ceil(payload/max_payload) [packet]。
    protocol_bytes: int  # packet_count*packet_overhead_bytes [B]。
    wire_bits: int  # 逐包编码位数再对齐 lane_count [bit]；含末次并行 bit beat 的填充。
    completion_time_s: float  # fixed_latency+wire_bits/(lanes*lane_rate) [s]；无工作时为零。


# 分包尾部独立取整；只估算一条空闲链路，不模拟 replay、FEC 纠错或 credit 停顿。
def estimate_link(p: SerialLinkParams, payload_bytes: int) -> LinkEstimate:
    count("payload_bytes", payload_bytes, 0)
    full, tail = divmod(payload_bytes, p.max_payload_bytes)
    packets = full + bool(tail)
    codewords = full * ceil_div((p.max_payload_bytes + p.packet_overhead_bytes) * 8, p.coding_data_bits)
    if tail:
        codewords += ceil_div((tail + p.packet_overhead_bytes) * 8, p.coding_data_bits)
    bits = ceil_div(codewords * p.coding_wire_bits, p.lane_count) * p.lane_count
    rate = positive("wire_rate_bps", p.lane_count * p.lane_rate_bps)
    seconds = positive("completion_time_s", p.fixed_latency_s + bits / rate) if packets else 0.0
    return LinkEstimate(packets, packets * p.packet_overhead_bytes, bits, seconds)

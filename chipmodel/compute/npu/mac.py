"""稠密 GEMM 工作量和 MAC 阵列理想服务；不隐含 systolic 数据流或存储重用。"""

from dataclasses import dataclass

from chipmodel.common import ClockDomain, PipelineEstimate, PipelineParams, ceil_div, count, estimate_pipeline


# GEMM 的逻辑语义：A[M,K]×B[K,N]→C[M,N]，一次 MAC 按一个逻辑操作计。
@dataclass(frozen=True, slots=True, kw_only=True)
class GemmWorkload:
    m: int  # 输出行数 M [element]。
    n: int  # 输出列数 N [element]。
    k: int  # 归约维 K [element]。
    operand_bits: int  # A/B 每个元素的逻辑位宽 [bit/element]。
    output_bits: int  # C 每个元素的存储位宽 [bit/element]。

    # 允许空张量；位宽必须为正，未声明稀疏跳过或格式转换。
    def __post_init__(self) -> None:
        for name in ("m", "n", "k"):
            count(name, getattr(self, name), 0)
        count("operand_bits", self.operand_bits)
        count("output_bits", self.output_bits)

    # 稠密逻辑工作量 MAC=M*N*K；若按 FLOP 报告，调用方另声明 2 FLOP/MAC。
    @property
    def mac_count(self) -> int:
        return self.m * self.n * self.k

    # 输入逻辑存储量：每个张量分别做 bit→byte 向上取整，不代表实际访问流量。
    @property
    def input_bytes(self) -> int:
        return ceil_div(self.m * self.k * self.operand_bits, 8) + ceil_div(
            self.k * self.n * self.operand_bits, 8)

    # 输出逻辑存储量 ceil(M*N*output_bits/8) [B]。
    @property
    def output_bytes(self) -> int:
        return ceil_div(self.m * self.n * self.output_bits, 8)


# MAC engine 使用通用 P/L/II；每 lane 每次发起一个 MAC，供数和依赖由外部保证。
@dataclass(frozen=True, slots=True, kw_only=True)
class MacArray:
    params: PipelineParams  # P 个 MAC lane 及其 L/II [lane, cycle]。
    clock: ClockDomain  # 固定计算时钟域。

    # 估算指定的实际 MAC 次数；包含 padding/重算的量须由映射方显式传入。
    def estimate(self, executed_macs: int) -> PipelineEstimate:
        return estimate_pipeline(self.params, self.clock, executed_macs)

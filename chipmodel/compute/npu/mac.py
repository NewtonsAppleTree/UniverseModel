"""稠密 GEMM 工作量和 MAC 阵列理想服务；不隐含 systolic 数据流或存储重用。"""

from dataclasses import dataclass
from typing import Literal

from chipmodel.common import ClockDomain, PipelineEstimate, PipelineParams, ceil_div, count, estimate_pipeline, identifier


# 操作和数值格式组成完整服务签名；同位宽格式及融合/非融合运算不互换。
@dataclass(frozen=True, slots=True, kw_only=True)
class MacArithmetic:
    operation: Literal["integer_mac", "float_mul_add", "float_fma"]  # 一乘一加的整数、两次舍入浮点或融合浮点语义。
    operand_format: Literal["int8", "int16", "int32", "int64", "float16", "bfloat16", "float32", "float64"]  # A/B相同的显式格式。
    accumulator_format: Literal["int32", "int64", "float32", "float64"]  # 部分和保存格式；不隐含无限精度。
    output_format: Literal["int32", "int64", "float32", "float64"]  # 本服务不含输出转换，必须与累加格式相同。

    # 只支持同数值家族且无隐式输出转换；服务估算不执行舍入、限幅或溢出验证。
    def __post_init__(self) -> None:
        integers = ("int8", "int16", "int32", "int64")
        floats = ("float16", "bfloat16", "float32", "float64")
        if self.operation not in ("integer_mac", "float_mul_add", "float_fma"):
            raise ValueError("unsupported MAC operation")
        operands = integers if self.operation == "integer_mac" else floats
        accumulators = ("int32", "int64") if self.operation == "integer_mac" else ("float32", "float64")
        if self.operand_format not in operands or self.accumulator_format not in accumulators:
            raise ValueError("unsupported MAC operand/accumulator format family")
        if self.output_format != self.accumulator_format:
            raise ValueError("MAC output conversion requires a separate explicit model")


# 本包稠密任务的逻辑/实际工作分离；padding和重算由映射方提供，不能静默少算。
@dataclass(frozen=True, slots=True, kw_only=True)
class MacWork:
    arithmetic: MacArithmetic  # 请求的操作/操作数/累加/输出格式签名。
    logical_macs: int  # 所需有效逻辑工作 [MAC]，可为0。
    executed_macs: int  # 实际包含padding/重算的工作 [MAC]，至少logical_macs。

    # 不推导稀疏跳过，非零工作按所选服务签名计量。
    def __post_init__(self) -> None:
        if not isinstance(self.arithmetic, MacArithmetic):
            raise TypeError("arithmetic must be MacArithmetic")
        count("logical_macs", self.logical_macs, 0)
        count("executed_macs", self.executed_macs, self.logical_macs)


# 数量、尾批和显式服务边界；实际执行时间/能耗与数值质量不由峰值推导。
@dataclass(frozen=True, slots=True)
class MacAnalysis:
    arithmetic: MacArithmetic  # 已匹配的请求/能力签名。
    logical_macs: int  # 本次逻辑工作 [MAC]。
    executed_macs: int  # 本次实际工作 [MAC]。
    extra_macs: int  # executed-logical [MAC]，映射额外工作。
    issued_lane_slots: int  # ceil(executed/P)*P [MAC slot]。
    unused_tail_slots: int  # issued_lane_slots-executed [MAC slot]。
    packing_efficiency: float | None  # executed/issued_lane_slots [1]；无工作时None。
    useful_work_fraction: float | None  # logical/executed [1]；不等于动态执行利用率。
    service: PipelineEstimate  # 足够独立MAC、供数及在途容量下的孤立服务结果。
    execution_time_s: None  # 实际任务时间 [s]；依赖、供数、流水槽/反馈未建模。
    energy_j: None  # 服务能量 [J]，没有特征化输入。
    unknown_reason: str  # 未知时间/物理成本与功能边界。
    profile_source: str  # 签名对应的P/L/II和时钟参数来源。


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
    arithmetic: MacArithmetic | None = None  # 此档位唯一支持的签名；None仅可调用历史无格式estimate。
    profile_source: str = "unrecorded"  # 操作/格式对应的服务来源，不能由NPU/tensor名称推断。

    # 一个profile只绑定一组签名和P/L/II；改变精度不自动放大lane数或缩短延迟。
    def __post_init__(self) -> None:
        if not isinstance(self.params, PipelineParams) or not isinstance(self.clock, ClockDomain):
            raise TypeError("MacArray requires PipelineParams and ClockDomain")
        if self.arithmetic is not None and not isinstance(self.arithmetic, MacArithmetic):
            raise TypeError("arithmetic must be MacArithmetic or None")
        identifier("profile_source", self.profile_source)

    # 估算指定的实际 MAC 次数；包含 padding/重算的量须由映射方显式传入。
    def estimate(self, executed_macs: int) -> PipelineEstimate:
        return estimate_pipeline(self.params, self.clock, executed_macs)

    # 完整签名匹配后统计尾批和额外工作；复用同一P/L/II公式，不收取第二份计算成本。
    def analyze(self, work: MacWork) -> MacAnalysis:
        if not isinstance(work, MacWork):
            raise TypeError("work must be MacWork")
        if self.arithmetic is None or self.arithmetic != work.arithmetic:
            raise ValueError("MAC operation/format unsupported by selected capability")
        service = self.estimate(work.executed_macs)
        slots = service.issue_groups * self.params.lane_count
        return MacAnalysis(work.arithmetic, work.logical_macs, work.executed_macs,
                           work.executed_macs - work.logical_macs, slots, slots - work.executed_macs,
                           work.executed_macs / slots if slots else None,
                           work.logical_macs / work.executed_macs if work.executed_macs else None,
                           service, None, None,
                           "No dependency/supply/feedback scheduling, numerical validation or calibrated energy; ready independent MAC service only",
                           self.profile_source)

"""CPU 各阶段能力的上界；不执行 ISA，也不模拟乱序或缓存。"""

from dataclasses import dataclass

from chipmodel.common import ClockDomain, count, positive


# 描述独立、同类 μop 的供给/发射/执行/提交能力，最窄阶段限制稳态吞吐。
@dataclass(frozen=True, slots=True, kw_only=True)
class CpuCoreParams:
    fetch_uops_per_cycle: int  # 已按指令展开比例归一的取指供给 [μop/cycle]。
    decode_uops_per_cycle: int  # 解码带宽 [μop/cycle]。
    issue_uops_per_cycle: int  # 最大总发射宽度 [μop/cycle]。
    retire_uops_per_cycle: int  # 提交宽度 [μop/cycle]；不等同于 ISA IPC。
    execution_lanes: int  # 可执行所选 μop 类型的等价端口数 [lane]。
    execution_ii_cycles: int  # 每执行 lane 的发起间隔 II [cycle]。

    # 所有能力为正整数；此模型只涵盖调用方选定的一类 μop。
    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            count(name, getattr(self, name))


# CPU 峰值计算只表达 min(stage capacities)，不输出无依据的程序运行时间。
@dataclass(frozen=True, slots=True, kw_only=True)
class CpuCore:
    params: CpuCoreParams  # 冻结的阶段能力参数。
    clock: ClockDomain  # Core 固定时钟域。

    # 各阶段速率的最小值 r=min(fetch,decode,issue,retire,lanes/II) [μop/cycle]。
    @property
    def peak_uops_per_cycle(self) -> float:
        p = self.params
        return min(p.fetch_uops_per_cycle, p.decode_uops_per_cycle,
                   p.issue_uops_per_cycle, p.retire_uops_per_cycle,
                   p.execution_lanes / p.execution_ii_cycles)

    # r*f [μop/s]；依赖、分支、端口混合与供数均可能进一步降低实测速率。
    @property
    def peak_uops_per_s(self) -> float:
        return positive("peak_uops_per_s", self.peak_uops_per_cycle * self.clock.frequency_hz)

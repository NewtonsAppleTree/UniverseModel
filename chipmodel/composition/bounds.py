"""由因果依赖与资源供给包络推导时间下界，不求真实调度完成时间。"""

from dataclasses import dataclass
from math import fsum

from chipmodel.common import identifier, positive, real


# 资源供给包络 W(T)≤initial_credit+rate*T；首批/流水线突发能力必须显式给出。
@dataclass(frozen=True, slots=True, kw_only=True)
class ResourceBudget:
    resource_id: str  # 唯一资源身份，与 demand 引用一致。
    work_unit: str  # 资源工作单位，如 MAC、B、conversion。
    rate_per_s: float  # 可证明的供给速率上界 r [work_unit/s]。
    initial_credit: float  # 时间零可用的额外供给上界 b [work_unit]；流体模型可取 0。

    # 包络参数有限且非负，r>0；不把任意实测平均速率当作供给上界。
    def __post_init__(self) -> None:
        identifier("resource_id", self.resource_id)
        identifier("work_unit", self.work_unit)
        positive("rate_per_s", self.rate_per_s)
        real("initial_credit", self.initial_credit, minimum=0)


# 一次操作实际消耗的资源工作量；不同单位的 demand 禁止直接累加。
@dataclass(frozen=True, slots=True, kw_only=True)
class ResourceDemand:
    resource_id: str  # 承担此工作量的资源身份。
    work_unit: str  # 与 budget 一致的工作单位。
    amount: float  # 实际工作量 W [work_unit]；包含映射造成的额外工作。

    # 负工作量没有物理意义；单位和资源身份必须显式。
    def __post_init__(self) -> None:
        identifier("resource_id", self.resource_id)
        identifier("work_unit", self.work_unit)
        real("amount", self.amount, minimum=0)


# 操作以完成后依赖表示；latency 是该操作的最小延迟，不是峰值倒数。
@dataclass(frozen=True, slots=True, kw_only=True)
class ActionEstimate:
    action_id: str  # 当前任务内唯一的操作身份。
    latency_s: float  # 满足输入条件后的最小完成延迟 [s]。
    dependencies: tuple[str, ...]  # 必须先完成的操作 ID；不表示全部硬件连接。
    demands: tuple[ResourceDemand, ...]  # 此操作声明的资源工作量。

    # 冻结依赖与工作量；同一操作不能重复列出同一个依赖。
    def __post_init__(self) -> None:
        identifier("action_id", self.action_id)
        real("latency_s", self.latency_s, minimum=0)
        object.__setattr__(self, "dependencies", tuple(self.dependencies))
        object.__setattr__(self, "demands", tuple(self.demands))
        if len(set(self.dependencies)) != len(self.dependencies):
            raise ValueError("duplicate action dependency")


# 只对已声明的任务/资源给出必要时间界；缺失资源仍可能进一步限制系统。
@dataclass(frozen=True, slots=True)
class TimeBounds:
    critical_path_s: float  # 操作 DAG 上延迟和的最大值 [s]。
    resource_bound_s: float  # max_r(max(0,(ΣW_r−b_r)/r_r)) [s]。
    lower_bound_s: float  # max(critical_path_s,resource_bound_s) [s]。
    serial_latency_sum_s: float  # 所有操作最小延迟之和 [s]；不是已验证的系统上界。


# 在依赖 DAG 上动态规划；按唯一资源累加工作，再应用各自的供给包络。
def estimate_time_bounds(actions: tuple[ActionEstimate, ...],
                         budgets: tuple[ResourceBudget, ...]) -> TimeBounds:
    action_map = {a.action_id: a for a in actions}
    resource_map = {b.resource_id: b for b in budgets}
    if len(action_map) != len(actions) or len(resource_map) != len(budgets):
        raise ValueError("duplicate action_id or resource_id")
    successors = {key: [] for key in action_map}
    indegrees = {a.action_id: len(a.dependencies) for a in actions}
    work = {key: [] for key in resource_map}
    for action in actions:
        for dependency in action.dependencies:
            if dependency not in action_map:
                raise ValueError("unknown action dependency")
            successors[dependency].append(action.action_id)
        for demand in action.demands:
            if demand.resource_id not in resource_map:
                raise ValueError("resource demand has no budget")
            if demand.work_unit != resource_map[demand.resource_id].work_unit:
                raise ValueError("resource demand/budget units differ")
            work[demand.resource_id].append(demand.amount)
    ready = [key for key, degree in indegrees.items() if degree == 0]
    finish = {}
    for key in ready:
        action = action_map[key]
        finish[key] = real("critical_path_s", action.latency_s
                           + max((finish[dep] for dep in action.dependencies), default=0))
        for child in successors[key]:
            indegrees[child] -= 1
            if indegrees[child] == 0:
                ready.append(child)
    if len(finish) != len(actions):
        raise ValueError("action dependencies contain a cycle")
    resource_bound = max((max(0.0, (fsum(work[key]) - b.initial_credit) / b.rate_per_s)
                          for key, b in resource_map.items()), default=0.0)
    critical = max(finish.values(), default=0.0)
    return TimeBounds(critical, real("resource_bound_s", resource_bound, minimum=0),
                      max(critical, resource_bound), real("serial_latency_sum_s", fsum(a.latency_s for a in actions)))

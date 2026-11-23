"""小型、精确工作点的成本表及来源再现/留出误差检查。"""

from dataclasses import dataclass
from typing import Literal

from costmodel.interfaces.costs import CostEstimate, CostKey, CostPoint, CostSource, frozen_items, nonnegative, text_id


# 表的唯一键绑定结构/PVT/动作，顺序不决定模型优先级。
@dataclass(frozen=True, slots=True, kw_only=True)
class CostTable:
    table_id: str  # 特征化表及版本身份。
    points: tuple[CostPoint, ...]  # 有来源的条件点；可以为空以明确全部未知。

    # 冻结点集并拒绝模糊重复键，缺点交给查询返回未知。
    def __post_init__(self) -> None:
        text_id("table_id", self.table_id)
        object.__setattr__(self, "points", frozen_items("points", self.points, CostPoint))
        if len({p.key for p in self.points}) != len(self.points):
            raise ValueError("duplicate cost key")


# 精确查表，不插值/外推；源类别与误差未知状态随匹配点返回。
def query_cost(table: CostTable, key: CostKey) -> CostEstimate:
    if not isinstance(table, CostTable) or not isinstance(key, CostKey):
        raise TypeError("query requires CostTable and CostKey")
    point = next((p for p in table.points if p.key == key), None)
    return CostEstimate(key, point, None if point else "No exact structure/PVT/metric/action/unit point; no interpolation or extrapolation")


# 差值仅说明所给参考上的误差；来源点再现不是器件有效性验证。
@dataclass(frozen=True, slots=True)
class ReferenceError:
    role: str  # source_reproduction或holdout；本身不证明参考独立性。
    absolute_error: float  # |预测−参考|，单位与成本项相同。
    relative_error: float | None  # |预测−参考|/|参考|；参考为0时未定义。
    reference_source: CostSource  # 参考工件/方法，保留来源类别与限制。


# 留出比较必须来自不同工件且非假设参考；仍由研究者证明方法独立和代表性。
def check_reference(estimate: CostEstimate, reference_value: float, reference_source: CostSource,
                    *, role: Literal["source_reproduction", "holdout"]) -> ReferenceError:
    if not isinstance(estimate, CostEstimate) or estimate.point is None or not isinstance(reference_source, CostSource):
        raise ValueError("reference check needs a known estimate and reference source")
    reference = nonnegative("reference_value", reference_value)
    if role not in ("source_reproduction", "holdout"):
        raise ValueError("unknown reference role")
    source = estimate.point.source
    if role == "holdout" and (reference_source.kind == "assumption" or source.source_id == reference_source.source_id
            or source.artifact_sha256 == reference_source.artifact_sha256):
        raise ValueError("holdout must use a distinct non-assumption reference artifact")
    error = abs(estimate.value - reference)
    relative = None if reference == 0 else nonnegative("relative_error", error / reference)
    return ReferenceError(role, error, relative, reference_source)

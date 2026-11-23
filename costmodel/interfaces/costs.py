"""条件成本的专业值接口；不依赖硬件，不执行插值或隐式工艺缩放。"""

from dataclasses import dataclass
from math import isfinite
from typing import Literal


# 非空身份描述结构、来源与适用边界，不解释可执行表达式。
def text_id(name: str, value: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


# 校验非负有限物理量；排除bool及溢出，不把未知变成零。
def nonnegative(name: str, value: float) -> float:
    if type(value) not in (int, float):
        raise TypeError(f"{name} must be numeric")
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name} exceeds binary64") from exc
    if not isfinite(result) or result < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return result


# 只接受有限序列并冻结成员，防止把字符串或惰性迭代器当模型列表。
def frozen_items(name: str, values: object, kind: type) -> tuple:
    if not isinstance(values, (tuple, list)) or any(not isinstance(v, kind) for v in values):
        raise TypeError(f"{name} must contain {kind.__name__} values")
    return tuple(values)


# 一个来源绑定具体工件/版本；记录误差缺口，不把公开表当实测。
@dataclass(frozen=True, slots=True, kw_only=True)
class CostSource:
    source_id: str  # 来源身份，用于追溯与比较。
    kind: Literal["characterization", "measurement", "analytical", "assumption"]  # 证据类别；assumption仅为显式假设。
    reference: str  # 文献、URL或本地实验方法引用，不在查询时访问网络。
    revision: str  # 来源版本/工具版本/实验版本。
    artifact_sha256: str | None  # 原始来源工件SHA256；纯假设可为None。
    extraction: str  # 字段提取、单位换算或观测方法。
    limitations: tuple[str, ...]  # 未覆盖成本、误差/校准缺口与适用边界。

    # 非假设来源必须有可核对工件哈希；来源文字不自动证明校准有效。
    def __post_init__(self) -> None:
        for name in ("source_id", "reference", "revision", "extraction"):
            text_id(name, getattr(self, name))
        if self.kind not in ("characterization", "measurement", "analytical", "assumption"):
            raise ValueError("unsupported evidence kind")
        digest = self.artifact_sha256
        if digest is not None and (type(digest) is not str or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)):
            raise ValueError("artifact_sha256 must be a lowercase SHA256")
        if self.kind != "assumption" and digest is None:
            raise ValueError("non-assumption evidence requires an artifact hash")
        object.__setattr__(self, "limitations", frozen_items("limitations", self.limitations, str))
        if not self.limitations:
            raise ValueError("evidence must declare its limitations")
        for item in self.limitations:
            text_id("limitation", item)


# 精确工作点：process包含库/工艺角，温度使用绝对温度；没有全域缩放规律。
@dataclass(frozen=True, slots=True, kw_only=True)
class OperatingPoint:
    process: str  # 工艺/库/角身份，不仅是nm标签。
    voltage_v: float  # VDD [V]，严格为正。
    temperature_k: float  # 条件温度 [K]，严格为正。

    # 归一数值以匹配同一个精确工作点；不自动外推或容差近邻匹配。
    def __post_init__(self) -> None:
        text_id("process", self.process)
        for name in ("voltage_v", "temperature_k"):
            value = nonnegative(name, getattr(self, name))
            if value == 0:
                raise ValueError(f"{name} must be positive")
            object.__setattr__(self, name, value)


# 查询键包含完整结构身份与动作粒度；area/leakage按instance，dynamic按明确动作单位。
@dataclass(frozen=True, slots=True, kw_only=True)
class CostKey:
    structure_id: str  # 完整结构版本或参数哈希，不能只用MAC/SRAM通用名称复用器件值。
    operating_point: OperatingPoint  # 要求精确匹配的PVT条件。
    metric: Literal["area", "leakage", "dynamic"]  # 输出分别为mm²、W、J/动作单位。
    action: str = "instance"  # dynamic必须说明动作语义；area/leakage固定instance。
    work_unit: str = "instance"  # 计数粒度，如MAC、word、bit；不得把byte等同word。

    # 成本项和动作单位不能混用，工作点必须已通过专业校验。
    def __post_init__(self) -> None:
        for name in ("structure_id", "action", "work_unit"):
            text_id(name, getattr(self, name))
        if not isinstance(self.operating_point, OperatingPoint):
            raise TypeError("operating_point must be OperatingPoint")
        if self.metric not in ("area", "leakage", "dynamic"):
            raise ValueError("unknown cost metric")
        if self.metric != "dynamic" and (self.action, self.work_unit) != ("instance", "instance"):
            raise ValueError("area/leakage are per physical instance")
        if self.metric == "dynamic" and (self.action == "instance" or self.work_unit == "instance"):
            raise ValueError("dynamic energy requires explicit action and work unit")


# 表中一个已知条件点；dynamic仅含动作能量，排除另计的背景/漏电。
@dataclass(frozen=True, slots=True, kw_only=True)
class CostPoint:
    key: CostKey  # 结构/PVT/成本项/动作粒度键。
    value: float  # area [mm²]、leakage [W]或dynamic [J/动作单位]。
    source: CostSource  # 字段来源与限制。
    coverage: str  # 所含实体/动作边界；动态项须排除背景功率。
    relative_uncertainty: float | None = None  # 相对情景误差幅度；None为未知，不是0或置信区间。

    # 已知零与未知区分；拒绝非有限或负成本/不确定性。
    def __post_init__(self) -> None:
        if not isinstance(self.key, CostKey) or not isinstance(self.source, CostSource):
            raise TypeError("CostPoint requires key and source")
        object.__setattr__(self, "value", nonnegative("value", self.value))
        text_id("coverage", self.coverage)
        if self.relative_uncertainty is not None:
            object.__setattr__(self, "relative_uncertainty", nonnegative("relative_uncertainty", self.relative_uncertainty))


# 缺点/越域的查询结果明确保留None；不偷偷选择最近器件或PVT。
@dataclass(frozen=True, slots=True)
class CostEstimate:
    key: CostKey  # 原始查询键。
    point: CostPoint | None  # 精确匹配点，未知时None。
    unknown_reason: str | None  # 无来源或越域原因；已知时None。

    # 点与原请求必须完全一致；已知/未知状态互斥。
    def __post_init__(self) -> None:
        if not isinstance(self.key, CostKey):
            raise TypeError("key must be CostKey")
        if self.point is None:
            text_id("unknown_reason", self.unknown_reason)
        elif not isinstance(self.point, CostPoint) or self.point.key != self.key or self.unknown_reason is not None:
            raise ValueError("estimate point must match its request")

    # 未知点返回None而非零；值的单位由key.metric规定。
    @property
    def value(self) -> float | None:
        return None if self.point is None else self.point.value

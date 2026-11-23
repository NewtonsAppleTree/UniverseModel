"""CIM 同输入对照：功能质量、资源下界、显式策略时间和未知成本分别留档。"""

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from artifacts.storage.local import read_run, write_run
from chipmodel.common import count, identifier, positive, typed_tuple
from chipmodel.composition.tile.cim import CimTile, analyze_cim
from chipmodel.compute.cim.matvec import CimInput
from contracts.results.experiment import ExperimentSpec, Metric, RunRecord
from contracts.versions.json_codec import canonical_json, content_hash, parse_json
from evaluation.experiments.runner.single import run_experiment
from workloads.reference.integer_matvec import reference_integer_matvec


# 有限且可审阅的单因素改动；没有可执行公式或任意配置路径。
@dataclass(frozen=True, slots=True, kw_only=True)
class CimCandidate:
    name: str  # 当前study唯一的候选身份。
    category: Literal["baseline", "mapping", "resource_ablation", "precision_ablation", "boundary"]  # 明确比较口径。
    subtract_before_adc: bool | None = None  # 模拟/数字差分位置；None沿用基线。
    adc_lane_count: int | None = None  # ADC通道数 [lane]，改变属于资源消融。
    adc_frequency_hz: float | None = None  # ADC时钟 [Hz]，不自动更改物理校准来源。
    adc_resolution_bits: int | None = None  # 名义ADC精度 [bit]，改变不自动推断速度/能耗收益。
    hold_slot_count: int | None = None  # 外部标量保持槽数 [sample]。
    hold_valid_duration_s: float | None = None  # 外部保持有效期 [s]。

    # baseline不可包含改动；mapping只改变差分位置，其他预算须保持相同。
    def __post_init__(self) -> None:
        identifier("name", self.name)
        if self.category not in ("baseline", "mapping", "resource_ablation", "precision_ablation", "boundary"):
            raise ValueError("unsupported CIM comparison category")
        if self.subtract_before_adc is not None and type(self.subtract_before_adc) is not bool:
            raise TypeError("subtract_before_adc must be bool or None")
        for name in ("adc_lane_count", "adc_resolution_bits", "hold_slot_count"):
            if getattr(self, name) is not None:
                count(name, getattr(self, name))
        for name in ("adc_frequency_hz", "hold_valid_duration_s"):
            if getattr(self, name) is not None:
                positive(name, getattr(self, name))
        overrides = [name for name in self.__dataclass_fields__ if name not in ("name", "category") and getattr(self, name) is not None]
        if self.category == "baseline" and overrides:
            raise ValueError("baseline cannot override its hardware")
        if self.category == "mapping" and set(overrides) != {"subtract_before_adc"}:
            raise ValueError("mapping comparison only changes differential subtraction location")
        allowed = {"resource_ablation": {"adc_lane_count", "adc_frequency_hz", "hold_slot_count", "hold_valid_duration_s"},
                   "precision_ablation": {"adc_resolution_bits"}}
        if self.category in allowed and (len(overrides) != 1 or not set(overrides) <= allowed[self.category]):
            raise ValueError("ablation category requires exactly one matching parameter change")
        if self.category != "baseline" and not overrides:
            raise ValueError("non-baseline candidate needs an explicit change")


# 同一组实际向量/矩阵在相同基线及有标签的消融下比较，失败和质量损失都保留。
@dataclass(frozen=True, slots=True, kw_only=True)
class CimStudy:
    tile: CimTile  # 所有候选共有的基线硬件及profile来源。
    inputs: CimInput  # 同一份已驻留整数输入/权重。
    candidates: tuple[CimCandidate, ...]  # 完整有限候选名单；首项是唯一baseline。
    max_cell_evaluations: int = 1_000_000  # 宿主工作/轨迹展开上限 [cell evaluation]，非硬件预算。
    max_abs_error: int = 0  # 输出整数允许的绝对误差 [integer]；默认精确匹配。
    schema_version: Literal["cim-study/v1"] = "cim-study/v1"  # 研究配置版本。

    # 验证共同输入和名单；候选的硬件可行性在被记录的回调中检查。
    def __post_init__(self) -> None:
        if not isinstance(self.tile, CimTile) or not isinstance(self.inputs, CimInput):
            raise TypeError("CimStudy requires CimTile and CimInput")
        object.__setattr__(self, "candidates", typed_tuple("candidates", self.candidates, CimCandidate))
        count("max_cell_evaluations", self.max_cell_evaluations)
        count("max_abs_error", self.max_abs_error, 0)
        if self.schema_version != "cim-study/v1" or not self.candidates or self.candidates[0].category != "baseline":
            raise ValueError("CIM study requires v1 schema and a first baseline candidate")
        if sum(c.category == "baseline" for c in self.candidates) != 1 or len({c.name for c in self.candidates}) != len(self.candidates):
            raise ValueError("CIM study requires unique candidates and one baseline")


# 显式替换生产者字段；依赖校验与范围由原始模型负责，不创建另一份参数公式。
def apply_candidate(tile: CimTile, candidate: CimCandidate) -> CimTile:
    if not isinstance(tile, CimTile) or not isinstance(candidate, CimCandidate):
        raise TypeError("apply_candidate requires CimTile and CimCandidate")
    adc_changes = {field: getattr(candidate, name) for name, field in
                   (("adc_lane_count", "lane_count"), ("adc_resolution_bits", "resolution_bits"))
                   if getattr(candidate, name) is not None}
    encoding = tile.numeric.encoding if candidate.subtract_before_adc is None else replace(
        tile.numeric.encoding, subtract_before_adc=candidate.subtract_before_adc)
    numeric = replace(tile.numeric, encoding=encoding, adc=replace(tile.numeric.adc, **adc_changes))
    hold_changes = {field: getattr(candidate, name) for name, field in
                    (("hold_slot_count", "slot_count"), ("hold_valid_duration_s", "valid_duration_s"))
                    if getattr(candidate, name) is not None}
    clock = tile.adc_clock if candidate.adc_frequency_hz is None else replace(tile.adc_clock, frequency_hz=candidate.adc_frequency_hz)
    return replace(tile, numeric=numeric, adc_clock=clock, hold=replace(tile.hold, **hold_changes))


# 独立整数参考再应用最终输出格式；量化误差、输出溢出、ADC限幅分别观察。
def evaluate_cim_experiment(tile: CimTile, inputs: CimInput, *, max_cell_evaluations: int = 1_000_000,
                            max_abs_error: int = 0) -> tuple[object, tuple[Metric, ...]]:
    count("max_abs_error", max_abs_error, 0)
    analysis = analyze_cim(tile, inputs, max_cell_evaluations=max_cell_evaluations)
    exact = reference_integer_matvec(inputs.input_codes, inputs.weights, max_macs=max_cell_evaluations)
    bits, policy = tile.numeric.output_bits, tile.numeric.overflow
    lo, hi = -(2 ** (bits - 1)), 2 ** (bits - 1) - 1
    if policy == "saturate":
        reference = tuple(max(lo, min(hi, value)) for value in exact)
    elif policy == "wrap":
        unsigned = tuple(value % (2 ** bits) for value in exact)
        reference = tuple(value if value < 2 ** (bits - 1) else value - 2 ** bits for value in unsigned)
    else:
        reference = exact
    error = max(abs(actual - expected) for actual, expected in zip(analysis.numeric.output, reference))
    validation = {"passed": error <= max_abs_error, "max_abs_error": error, "allowed_abs_error": max_abs_error,
                  "exact_output": exact, "reference_output": reference,
                  "reference_overflowed": tuple(not lo <= value <= hi for value in exact),
                  "reference": "python-integer-dot/v1; final format applied independently"}
    return {"analysis": analysis, "validation": validation, "effective_tile": tile}, (
        Metric(name="logical_macs", value=analysis.counts.logical_macs, unit="MAC", kind="counter"),
        Metric(name="cell_evaluations", value=analysis.counts.cell_evaluations, unit="cell_evaluation", kind="counter"),
        Metric(name="adc_conversions", value=analysis.counts.adc_conversions, unit="conversion", kind="counter"),
        Metric(name="digital_operations", value=analysis.counts.digital_operations, unit="operation", kind="counter"),
        Metric(name="resource_lower_bound", value=analysis.resource_lower_bound_s, unit="second", kind="lower_bound"),
        Metric(name="serial_policy_time", value=analysis.serial_policy_time_s, unit="second", kind="estimated"),
        Metric(name="read_energy", value=None, unit="joule", kind="estimated", unknown_reason=analysis.unknown_reasons[1]),
        Metric(name="programming_time", value=None, unit="second", kind="estimated", unknown_reason=analysis.unknown_reasons[0]),
        Metric(name="programming_energy", value=None, unit="joule", kind="estimated", unknown_reason=analysis.unknown_reasons[0]),
    )


# 构造候选发生在记录内部，使保持/在途/输出容量或格式失败仍留下可追溯记录。
def _evaluate(configuration: dict, inputs: CimInput) -> tuple[object, tuple[Metric, ...]]:
    candidate = next(c for c in configuration["candidates"] if c.name == configuration["selected_candidate"])
    return evaluate_cim_experiment(apply_candidate(configuration["tile"], candidate), inputs,
                                   max_cell_evaluations=configuration["max_cell_evaluations"], max_abs_error=configuration["max_abs_error"])


# 每个候选共享真实数据与完整名单；质量失败和执行失败保持不同状态。
def run_study(study: CimStudy, *, source_revision: str = "unrecorded") -> tuple[RunRecord, ...]:
    if not isinstance(study, CimStudy):
        raise TypeError("study must be CimStudy")
    records = []
    for candidate in study.candidates:
        spec = ExperimentSpec(experiment_id=candidate.name, implementation_id="cim-local-bench/v1", mode="analytical",
                              source_revision=source_revision, assumptions=(
            "Full dense unsigned-input MatVec with signed magnitude weight slices; no zero skipping",
            "Weights and input codes preloaded; programming and external movement remain unknown",
            "Ideal linear conductance, DAC broadcast and stable currents through each TIA scan",
            "ADC bin-midpoint reconstruction and ties-to-even requantization; final-only signed overflow",
            "Serial phases with full stage barriers; sample/hold released on ADC admission into finite internal slots",
            "Digital items: one reconstruction/code, one post-ADC difference/column when selected, one fused requantize/shift-add/column",
            "Fixed service assumptions, no event/device timing, task-level AI quality or calibrated physical energy claim",
        ))
        configuration = {"tile": study.tile, "candidates": study.candidates, "selected_candidate": candidate.name,
                         "max_cell_evaluations": study.max_cell_evaluations, "max_abs_error": study.max_abs_error,
                         "schema_version": study.schema_version}
        records.append(run_experiment(spec, configuration, study.inputs, _evaluate))
    return tuple(records)


# 由记录重建完整对照；拒绝混用来源/输入/预算、遗漏失败候选或重复运行身份。
def summarize_records(records: tuple[RunRecord, ...]) -> tuple[dict[str, object], ...]:
    records = typed_tuple("records", records, RunRecord)
    if not records:
        raise ValueError("no CIM records")
    rows, names, run_ids, shared = [], set(), set(), None
    for record in records:
        if record.spec.implementation_id != "cim-local-bench/v1" or record.spec.mode != "analytical":
            raise ValueError("expected CIM analytical records")
        config = parse_json(record.configuration_json)
        if not isinstance(config, dict) or set(config) != {"tile", "candidates", "selected_candidate", "max_cell_evaluations", "max_abs_error", "schema_version"}:
            raise ValueError("invalid CIM study snapshot")
        if config["schema_version"] != "cim-study/v1" or not isinstance(config["candidates"], list) or not config["candidates"]:
            raise ValueError("invalid CIM schema or roster")
        candidates = tuple(CimCandidate(**item) for item in config["candidates"])
        roster = {c.name for c in candidates}
        if len(roster) != len(candidates) or candidates[0].category != "baseline" or sum(c.category == "baseline" for c in candidates) != 1:
            raise ValueError("invalid CIM candidate roster")
        selected = config.pop("selected_candidate")
        identity = content_hash({"config": config, "inputs": parse_json(record.inputs_json),
                                 "source": record.spec.source_revision, "assumptions": record.spec.assumptions})
        if shared is not None and identity != shared:
            raise ValueError("mixed CIM budgets, inputs or source versions")
        shared = identity
        if selected != record.spec.experiment_id or selected not in roster or selected in names or record.run_id in run_ids:
            raise ValueError("invalid or duplicate CIM candidate/run identity")
        names.add(selected)
        run_ids.add(record.run_id)
        payload = parse_json(record.output_json) if record.status == "succeeded" else None
        a = payload["analysis"] if payload else None
        rows.append({"candidate": selected, "category": next(c.category for c in candidates if c.name == selected),
                     "status": record.status, "validation_passed": payload["validation"]["passed"] if payload else None,
                     "max_abs_error": payload["validation"]["max_abs_error"] if payload else None,
                     "output": a["numeric"]["output"] if a else None, "counts": a["counts"] if a else None,
                     "clipped_samples": a["numeric"]["clipped_samples"] if a else None,
                     "resource_lower_bound_s": a["resource_lower_bound_s"] if a else None,
                     "serial_policy_time_s": a["serial_policy_time_s"] if a else None,
                     "bottlenecks": a["bottlenecks"] if a else None,
                     "max_hold_age_s": max(s["hold_age_s"] for s in a["samples"]) if a else None,
                     "diagnostic": record.diagnostic, "identity_hash": record.identity_hash})
    if names != roster:
        raise ValueError("incomplete CIM candidate roster")
    return tuple(sorted(rows, key=lambda row: row["candidate"]))


# 先写全部不可变bundle，最后提交索引；目录存在时拒绝覆盖。
def write_study(records: tuple[RunRecord, ...], directory: str | Path) -> Path:
    summarize_records(records)
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=False)
    entries = []
    for index, record in enumerate(sorted(records, key=lambda r: r.spec.experiment_id)):
        name = f"run-{index:04d}"
        write_run(record, target / name)
        entries.append({"directory": name, "run_id": record.run_id, "identity_hash": record.identity_hash})
    with (target / "index.json").open("x", encoding="utf-8") as handle:
        handle.write(canonical_json({"schema_version": "cim-study-index/v1", "runs": entries}) + "\n")
    return target


# 只回读哈希验证的记录，不重新编程/计算；索引不能指向任意路径或漏掉失败样本。
def read_study(directory: str | Path) -> tuple[RunRecord, ...]:
    target = Path(directory)
    index = parse_json((target / "index.json").read_text(encoding="utf-8"))
    if not isinstance(index, dict) or set(index) != {"schema_version", "runs"} or index["schema_version"] != "cim-study-index/v1":
        raise ValueError("invalid CIM study index")
    if not isinstance(index["runs"], list) or not index["runs"]:
        raise ValueError("CIM index requires a complete run roster")
    records = []
    for position, entry in enumerate(index["runs"]):
        if not isinstance(entry, dict) or set(entry) != {"directory", "run_id", "identity_hash"} or entry["directory"] != f"run-{position:04d}":
            raise ValueError("invalid CIM bundle path/order")
        record = RunRecord.from_dict(read_run(target / entry["directory"]))
        if record.run_id != entry["run_id"] or record.identity_hash != entry["identity_hash"]:
            raise ValueError("CIM index and run identity disagree")
        records.append(record)
    summarize_records(tuple(records))
    return tuple(records)

"""物理条件实验：来源点、PVT/几何/窗口/热敏感性与未知成本分开解释。"""

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from artifacts.storage.local import read_run, write_run
from chipmodel.common import identifier, typed_tuple
from chipmodel.packaging.evidence import PhysicalModel, PhysicalWork, analyze_physical
from chipmodel.packaging.thermal.trace import ThermalTrace, analyze_thermal_trace
from configuration.resolution.dataclass_config import resolve_dataclass
from contracts.results.experiment import ExperimentSpec, Metric, RunRecord
from contracts.versions.json_codec import canonical_json, content_hash, parse_json
from costmodel.providers.tabulated.lookup import CostTable
from evaluation.experiments.runner.single import run_experiment


# 一个固定来源表下的物理情景；输入工作与模型/功率条件分别保存。
@dataclass(frozen=True, slots=True, kw_only=True)
class PhysicalCase:
    name: str  # 全研究唯一案例名。
    group: str  # 一个基线及其敏感性/反例集合。
    role: Literal["baseline", "geometry", "observation", "thermal", "pvt", "activity", "boundary"]  # 明确允许变化因素。
    model: PhysicalModel  # 唯一资源、结构/PVT、面积计量和几何约束。
    work: PhysicalWork  # 动作账本、覆盖缺口及外部观测窗口。
    table: CostTable  # 明确来源/单位/条件与误差未知状态。
    thermal: ThermalTrace | None = None  # 可选外部总功率驱动的单节点轨迹。

    # 冻结专业输入，几何不合法等运行反例由执行阶段保留失败记录。
    def __post_init__(self) -> None:
        identifier("name", self.name)
        identifier("group", self.group)
        if self.role not in ("baseline", "geometry", "observation", "thermal", "pvt", "activity", "boundary"):
            raise ValueError("invalid physical comparison role")
        if not isinstance(self.model, PhysicalModel) or not isinstance(self.work, PhysicalWork) or not isinstance(self.table, CostTable):
            raise TypeError("physical case needs model/work/table")
        if self.thermal is not None and not isinstance(self.thermal, ThermalTrace):
            raise TypeError("thermal must be ThermalTrace")


# 查找参数树叶子差异，热敏感性只允许单数值变化，不解释字符串公式。
def _differences(a: object, b: object) -> list[tuple[object, object]]:
    if isinstance(a, dict) and isinstance(b, dict) and a.keys() == b.keys():
        return [pair for key in a for pair in _differences(a[key], b[key])]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [pair for x, y in zip(a, b) for pair in _differences(x, y)]
    return [] if a == b and type(a) is type(b) else [(a, b)]


# 每组一基线；查询表与来源固定，避免把换成本数据误作方案收益。
@dataclass(frozen=True, slots=True, kw_only=True)
class PhysicalStudy:
    cases: tuple[PhysicalCase, ...]  # 完整研究名单，含未知结果与失败反例。
    schema_version: Literal["physical-evidence-study/v1"] = "physical-evidence-study/v1"  # 配置/比较语义版本。

    # 按声明因素检查其他输入不变；不同因素的案例不汇成统一能效排名。
    def __post_init__(self) -> None:
        object.__setattr__(self, "cases", typed_tuple("cases", self.cases, PhysicalCase))
        if self.schema_version != "physical-evidence-study/v1" or not self.cases or len({c.name for c in self.cases}) != len(self.cases):
            raise ValueError("invalid physical schema or roster")
        for group in {c.group for c in self.cases}:
            cases = [c for c in self.cases if c.group == group]
            baselines = [c for c in cases if c.role == "baseline"]
            if len(baselines) != 1:
                raise ValueError("each physical group needs one baseline")
            base = baselines[0]
            for case in cases:
                if case.role in ("baseline", "boundary"):
                    continue
                model, work, thermal = case.model, case.work, case.thermal
                if case.role == "geometry":
                    model = replace(model, boundary=base.model.boundary, placements=base.model.placements)
                elif case.role == "observation":
                    work = replace(work, observation=base.work.observation)
                elif case.role == "activity":
                    work = replace(work, activities=base.work.activities, activity_source=base.work.activity_source)
                elif case.role == "pvt":
                    if [(s.resource_id, s.structure_id) for s in model.structures] != [(s.resource_id, s.structure_id) for s in base.model.structures]:
                        raise ValueError("PVT comparison cannot change structures")
                    model = replace(model, structures=base.model.structures)
                elif case.role == "thermal":
                    diff = _differences(parse_json(canonical_json(thermal)), parse_json(canonical_json(base.thermal)))
                    if len(diff) != 1 or any(type(v) not in (int, float) for v in diff[0]):
                        raise ValueError("thermal comparison requires one numeric change")
                    thermal = base.thermal
                if (model, work, thermal, case.table) != (base.model, base.work, base.thermal, base.table):
                    raise ValueError("comparison changed a factor outside its declared role")
                if (case.model, case.work, case.thermal) == (base.model, base.work, base.thermal):
                    raise ValueError("comparison must change its declared factor")


# 数值只来自专业模型；热功率是外部输入，不能与动态/漏电账本再次相加。
def _evaluate(configuration: dict, work: PhysicalWork) -> tuple[object, tuple[Metric, ...]]:
    case = next(c for c in configuration["study"].cases if c.name == configuration["selected"])
    analysis = analyze_physical(case.model, work, case.table)
    thermal = None
    if case.thermal is not None:
        if case.thermal.resource_id != case.model.scope_id:
            raise ValueError("thermal trace must describe this physical scope")
        thermal = analyze_thermal_trace(case.thermal)
    metrics = []
    for name, value, unit in (("characterized_area", analysis.characterized_area_mm2, "square_millimeter"),
            ("leakage_power", analysis.leakage_power_w, "watt"), ("dynamic_energy", analysis.dynamic_energy_j, "joule"),
            ("leakage_energy", analysis.leakage_energy_j, "joule"), ("modeled_energy", analysis.modeled_energy_j, "joule")):
        metrics.append(Metric(name=name, value=value, unit=unit, kind="estimated",
            unknown_reason="Missing exact cost point, activity coverage or observation duration; see physical ledger" if value is None else None))
    if thermal is not None:
        metrics.append(Metric(name="lumped_peak_temperature", value=thermal.peak_temperature_k, unit="kelvin", kind="estimated"))
    return {"physical": analysis, "thermal": thermal}, tuple(metrics)


# 来源/PVT/完整名单和工作进入身份，失败分析不丢弃。
def run_study(study: PhysicalStudy, *, source_revision: str = "unrecorded") -> tuple[RunRecord, ...]:
    if not isinstance(study, PhysicalStudy):
        raise TypeError("study must be PhysicalStudy")
    records = []
    for case in study.cases:
        spec = ExperimentSpec(experiment_id=case.name, implementation_id="physical-evidence/v1", mode="analytical",
            source_revision=source_revision, assumptions=(
                "Exact structure/PVT/action/unit lookup only; missing data and uncertainty remain unknown",
                "Static area/background use one complete resource cover; dynamic terms exclude background power",
                "Explicit observed or assumed duration only; no integration over service lower bounds or host wall time",
                "Floorplan area checks are necessary constraints; no routing, timing closure or physical feasibility proof",
                "Single-node thermal response uses externally supplied total power; no hotspots, inter-die coupling or PVT feedback",
                "Source reproduction is not independent device calibration; synthetic assumptions are not measured results",
            ))
        records.append(run_experiment(spec, {"study": study, "selected": case.name}, case.work, _evaluate))
    return tuple(records)


# 完整同源名单和实际输入校验，保留全部来源、失败与未知值。
def summarize_records(records: tuple[RunRecord, ...]) -> tuple[dict[str, object], ...]:
    records = typed_tuple("records", records, RunRecord)
    rows, names, ids, identity = [], set(), set(), None
    if not records:
        raise ValueError("empty physical records")
    for record in records:
        if (record.spec.implementation_id, record.spec.mode) != ("physical-evidence/v1", "analytical"):
            raise ValueError("expected physical analytical records")
        config = parse_json(record.configuration_json)
        if not isinstance(config, dict) or set(config) != {"study", "selected"}:
            raise ValueError("invalid physical snapshot")
        study = resolve_dataclass(PhysicalStudy, config["study"])
        current = content_hash({"study": config["study"], "source": record.spec.source_revision, "assumptions": record.spec.assumptions})
        if identity is not None and identity != current:
            raise ValueError("mixed physical studies or source versions")
        identity = current
        case = next((c for c in study.cases if c.name == config["selected"]), None)
        if case is None or case.name != record.spec.experiment_id or case.name in names or record.run_id in ids:
            raise ValueError("invalid or duplicate physical case/run identity")
        if canonical_json(case.work) != record.inputs_json:
            raise ValueError("physical inputs differ from declared work")
        names.add(case.name)
        ids.add(record.run_id)
        rows.append({"case": case.name, "group": case.group, "role": case.role, "status": record.status,
            "result": parse_json(record.output_json) if record.output_json is not None else None,
            "metrics": parse_json(canonical_json(record.metrics)), "diagnostic": record.diagnostic, "identity_hash": record.identity_hash})
    if names != {c.name for c in study.cases}:
        raise ValueError("incomplete physical case roster")
    return tuple(sorted(rows, key=lambda row: row["case"]))


# 先写哈希bundle，再写固定相对路径索引；不覆盖已有实验目录。
def write_study(records: tuple[RunRecord, ...], directory: str | Path) -> Path:
    summarize_records(records)
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=False)
    entries = []
    for position, record in enumerate(sorted(records, key=lambda r: r.spec.experiment_id)):
        name = f"run-{position:04d}"
        write_run(record, target / name)
        entries.append({"directory": name, "run_id": record.run_id, "identity_hash": record.identity_hash})
    with (target / "index.json").open("x", encoding="utf-8") as handle:
        handle.write(canonical_json({"schema_version": "physical-evidence-index/v1", "runs": entries}) + "\n")
    return target


# 回读只核对工件/输入身份和完整协议，不运行物理模型。
def read_study(directory: str | Path) -> tuple[RunRecord, ...]:
    target = Path(directory)
    index = parse_json((target / "index.json").read_text(encoding="utf-8"))
    if not isinstance(index, dict) or set(index) != {"schema_version", "runs"} or index["schema_version"] != "physical-evidence-index/v1":
        raise ValueError("invalid physical index")
    if not isinstance(index["runs"], list) or not index["runs"]:
        raise ValueError("physical index needs complete runs")
    records = []
    for position, entry in enumerate(index["runs"]):
        if not isinstance(entry, dict) or set(entry) != {"directory", "run_id", "identity_hash"} or entry["directory"] != f"run-{position:04d}":
            raise ValueError("invalid physical bundle path/order")
        record = RunRecord.from_dict(read_run(target / entry["directory"]))
        if (record.run_id, record.identity_hash) != (entry["run_id"], entry["identity_hash"]):
            raise ValueError("physical index/record identity mismatch")
        records.append(record)
    summarize_records(tuple(records))
    return tuple(records)

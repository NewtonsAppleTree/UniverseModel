"""按CPU/GPU/NPU各自语义保存能力对照；不同家族的指标不作统一性能排名。"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from artifacts.storage.local import read_run, write_run
from chipmodel.common import identifier, typed_tuple
from chipmodel.compute.cpu.core import CpuCore, CpuWork, analyze_cpu
from chipmodel.compute.gpu.occupancy import GpuSmParams, GpuBlock, derive_occupancy
from chipmodel.compute.npu.mac import MacArray, MacWork
from configuration.resolution.dataclass_config import resolve_dataclass
from contracts.results.experiment import ExperimentSpec, Metric, RunRecord
from contracts.versions.json_codec import canonical_json, content_hash, parse_json
from evaluation.experiments.runner.single import run_experiment


# 封闭的三类独立调用；family只选择已有入口，不接受可执行字符串。
@dataclass(frozen=True, slots=True, kw_only=True)
class ComputeCase:
    name: str  # 全研究唯一的案例身份。
    group: str  # 同一家族的一组基线与单因素比较，不进行跨架构性能排名。
    family: Literal["cpu", "gpu", "npu"]  # 所选能力分析入口。
    role: Literal["baseline", "resource_ablation", "workload_ablation", "boundary"]  # 资源、工作变化与边界反例分开。
    model: CpuCore | GpuSmParams | MacArray  # 显式能力、服务/分配规则及profile来源。
    work: CpuWork | GpuBlock | MacWork  # 该模型对应的独立任务需求。

    # 检查模型/工作家族，语义不匹配或启动不可行留给分析入口记录。
    def __post_init__(self) -> None:
        identifier("name", self.name)
        identifier("group", self.group)
        kinds = {"cpu": (CpuCore, CpuWork), "gpu": (GpuSmParams, GpuBlock), "npu": (MacArray, MacWork)}
        if self.family not in kinds or self.role not in ("baseline", "resource_ablation", "workload_ablation", "boundary"):
            raise ValueError("invalid compute family/role")
        model, work = kinds[self.family]
        if not isinstance(self.model, model) or not isinstance(self.work, work):
            raise TypeError("compute model/work do not match family")


# 基线与消融都保存完整参数；每组一个基线，资源消融固定工作且仅改单个数值参数。
@dataclass(frozen=True, slots=True, kw_only=True)
class ComputeStudy:
    cases: tuple[ComputeCase, ...]  # 完整有限名单，包含不可行或不支持的边界案例。
    schema_version: Literal["compute-capacity-study/v1"] = "compute-capacity-study/v1"  # 配置语义版本。

    # 自动审查单因素与预算口径；未知物理成本不通过比较标签变成已知。
    def __post_init__(self) -> None:
        object.__setattr__(self, "cases", typed_tuple("cases", self.cases, ComputeCase))
        if self.schema_version != "compute-capacity-study/v1" or not self.cases or len({c.name for c in self.cases}) != len(self.cases):
            raise ValueError("invalid compute schema or duplicate/empty roster")
        for group in {case.group for case in self.cases}:
            cases = [case for case in self.cases if case.group == group]
            baseline = [case for case in cases if case.role == "baseline"]
            if len(baseline) != 1 or len({case.family for case in cases}) != 1:
                raise ValueError("each compute group requires one baseline and one family")
            base = baseline[0]
            for case in cases:
                if case.role not in ("resource_ablation", "workload_ablation"):
                    continue
                changed, fixed = ("model", "work") if case.role == "resource_ablation" else ("work", "model")
                if getattr(case, fixed) != getattr(base, fixed):
                    raise ValueError("ablation must preserve its fixed model/work")
                differences = _differences(parse_json(canonical_json(getattr(base, changed))),
                                           parse_json(canonical_json(getattr(case, changed))))
                if len(differences) != 1 or any(type(value) not in (int, float) for value in differences[0]):
                    raise ValueError("ablation requires exactly one numeric parameter change; use boundary for semantic changes")


# 比较规范参数树的叶子；只用于审查单因素，不解释任意公式或修改模型。
def _differences(a: object, b: object) -> list[tuple[object, object]]:
    if isinstance(a, dict) and isinstance(b, dict) and a.keys() == b.keys():
        return [pair for key in a for pair in _differences(a[key], b[key])]
    return [] if a == b and type(a) is type(b) else [(a, b)]


# 原生产模型负责全部公式；这里只投影指标并保留未知执行时间。
def _evaluate(configuration: dict, work: CpuWork | GpuBlock | MacWork) -> tuple[object, tuple[Metric, ...]]:
    case = next(c for c in configuration["study"].cases if c.name == configuration["selected"])
    if case.family == "cpu":
        analysis = analyze_cpu(case.model, work)
        metrics = (Metric(name="uop_issue_span_lower_bound", value=analysis.issue_span_lower_bound_s, unit="second", kind="lower_bound"),)
    elif case.family == "gpu":
        analysis = derive_occupancy(case.model, work)
        metrics = (Metric(name="occupancy", value=analysis.occupancy_fraction, unit="one", kind="estimated"),
                   Metric(name="resident_blocks", value=analysis.resident_blocks, unit="one", kind="counter"))
    else:
        analysis = case.model.analyze(work)
        metrics = (Metric(name="executed_macs", value=analysis.executed_macs, unit="MAC", kind="counter"),
                   Metric(name="ideal_mac_service", value=analysis.service.completion_time_s, unit="second", kind="estimated"))
    return analysis, (*metrics, Metric(name="execution_time", value=None, unit="second", kind="estimated",
                                      unknown_reason="Capacity/residency/isolated service only; no program or kernel execution model"))


# 每条记录保存完整研究名单、实际输入和源码身份；错误签名在记录内部失败。
def run_study(study: ComputeStudy, *, source_revision: str = "unrecorded") -> tuple[RunRecord, ...]:
    if not isinstance(study, ComputeStudy):
        raise TypeError("study must be ComputeStudy")
    records = []
    for case in study.cases:
        spec = ExperimentSpec(experiment_id=case.name, implementation_id="compute-capacity/v1", mode="analytical",
                              source_revision=source_revision, assumptions=(
            "Separate CPU homogeneous uop capacity, GPU block residency and NPU independent MAC service scopes",
            "Single numeric parameter ablations preserve the complementary work/model; boundary cases may change semantics",
            "CPU cycle-zero stage credits, no stage latency/dependency; GPU padded-warp block-quantum allocation",
            "NPU explicit arithmetic signature with ready operands, sufficient independent MACs and inflight slots",
            "No execution-time, AI quality, device calibration or physical cost claim from successful analysis",
        ))
        records.append(run_experiment(spec, {"study": study, "selected": case.name}, case.work, _evaluate))
    return tuple(records)


# 验证完整名单/同源研究并展示各专业输出；不以succeeded代替物理可行性或数值质量。
def summarize_records(records: tuple[RunRecord, ...]) -> tuple[dict[str, object], ...]:
    records = typed_tuple("records", records, RunRecord)
    rows, names, ids, identity = [], set(), set(), None
    if not records:
        raise ValueError("empty compute records")
    for record in records:
        if (record.spec.implementation_id, record.spec.mode) != ("compute-capacity/v1", "analytical"):
            raise ValueError("expected compute capacity analytical records")
        config = parse_json(record.configuration_json)
        if not isinstance(config, dict) or set(config) != {"study", "selected"}:
            raise ValueError("invalid compute snapshot")
        study = resolve_dataclass(ComputeStudy, config["study"])
        current = content_hash({"study": config["study"], "source": record.spec.source_revision, "assumptions": record.spec.assumptions})
        if identity is not None and identity != current:
            raise ValueError("mixed compute studies or source versions")
        identity = current
        case = next((c for c in study.cases if c.name == config["selected"]), None)
        if case is None or case.name != record.spec.experiment_id or case.name in names or record.run_id in ids:
            raise ValueError("invalid or duplicate compute case/run identity")
        if canonical_json(case.work) != record.inputs_json:
            raise ValueError("compute work differs from the declared comparison")
        names.add(case.name)
        ids.add(record.run_id)
        rows.append({"case": case.name, "group": case.group, "family": case.family, "role": case.role,
                     "status": record.status, "analysis": parse_json(record.output_json) if record.output_json is not None else None,
                     "diagnostic": record.diagnostic, "identity_hash": record.identity_hash})
    if names != {c.name for c in study.cases}:
        raise ValueError("incomplete compute case roster")
    return tuple(sorted(rows, key=lambda row: row["case"]))


# 各run先写哈希校验bundle，最后提交索引；目标目录不覆盖已有实验。
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
        handle.write(canonical_json({"schema_version": "compute-study-index/v1", "runs": entries}) + "\n")
    return target


# 只读保存结果，不重新分析；路径、身份、完整名单与单因素协议均复核。
def read_study(directory: str | Path) -> tuple[RunRecord, ...]:
    target = Path(directory)
    index = parse_json((target / "index.json").read_text(encoding="utf-8"))
    if not isinstance(index, dict) or set(index) != {"schema_version", "runs"} or index["schema_version"] != "compute-study-index/v1":
        raise ValueError("invalid compute index")
    if not isinstance(index["runs"], list) or not index["runs"]:
        raise ValueError("compute index needs complete runs")
    records = []
    for position, entry in enumerate(index["runs"]):
        if not isinstance(entry, dict) or set(entry) != {"directory", "run_id", "identity_hash"} or entry["directory"] != f"run-{position:04d}":
            raise ValueError("invalid compute bundle path/order")
        record = RunRecord.from_dict(read_run(target / entry["directory"]))
        if (record.run_id, record.identity_hash) != (entry["run_id"], entry["identity_hash"]):
            raise ValueError("compute index/record identity mismatch")
        records.append(record)
    summarize_records(tuple(records))
    return tuple(records)

"""固定工作、位置/资源/顺序消融的局部Die/Package实验；不声明可行执行或物理校准。"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from artifacts.storage.local import read_run, write_run
from chipmodel.common import identifier, typed_tuple
from chipmodel.composition.die.topology import die_owners
from chipmodel.composition.package.assembly import AssemblyJob, ChipAssembly, analyze_assembly, project_scopes
from configuration.resolution.dataclass_config import resolve_dataclass
from contracts.results.experiment import ExperimentSpec, Metric, RunRecord
from contracts.versions.json_codec import canonical_json, content_hash, parse_json
from evaluation.experiments.runner.single import run_experiment


# 专业组合与完整job输入直接进入记录；role约束允许变化的研究因素。
@dataclass(frozen=True, slots=True, kw_only=True)
class AssemblyCase:
    name: str  # 全研究唯一案例身份。
    group: str  # 固定基线的一组位置/资源/顺序比较。
    role: Literal["baseline", "placement", "resource_ablation", "ordering_ablation", "boundary"]  # 区分调度位置、额外资源与边界反例。
    assembly: ChipAssembly  # 唯一资源/时钟/Die/domain清单及profile来源。
    jobs: tuple[AssemblyJob, ...]  # 实际任务、MAC/访问/搬运、地址预留与依赖。

    # 构造时固定类型与身份；可运行性、容量及job依赖在模型中验证并记录失败。
    def __post_init__(self) -> None:
        identifier("name", self.name)
        identifier("group", self.group)
        if self.role not in ("baseline", "placement", "resource_ablation", "ordering_ablation", "boundary"):
            raise ValueError("invalid assembly comparison role")
        if not isinstance(self.assembly, ChipAssembly):
            raise TypeError("assembly must be ChipAssembly")
        object.__setattr__(self, "jobs", typed_tuple("jobs", self.jobs, AssemblyJob))


# 每组一基线；位置变化保留实际工作，资源消融只改一个数值参数，顺序消融只改依赖。
@dataclass(frozen=True, slots=True, kw_only=True)
class AssemblyStudy:
    cases: tuple[AssemblyCase, ...]  # 全部有限比较名单，包括失败反例。
    schema_version: Literal["chip-assembly-study/v1"] = "chip-assembly-study/v1"  # 配置与比较协议版本。

    # 比较协议自动审查；同一逻辑工作不能靠删除访存或重定义profile获取虚假收益。
    def __post_init__(self) -> None:
        object.__setattr__(self, "cases", typed_tuple("cases", self.cases, AssemblyCase))
        if self.schema_version != "chip-assembly-study/v1" or not self.cases or len({c.name for c in self.cases}) != len(self.cases):
            raise ValueError("invalid assembly schema or duplicate/empty roster")
        for group in {c.group for c in self.cases}:
            cases = [c for c in self.cases if c.group == group]
            baselines = [c for c in cases if c.role == "baseline"]
            if len(baselines) != 1:
                raise ValueError("each assembly group requires exactly one baseline")
            base = baselines[0]
            for case in cases:
                if case.role == "resource_ablation":
                    if case.jobs != base.jobs:
                        raise ValueError("resource ablation must preserve actual jobs")
                    diff = _differences(parse_json(canonical_json(base.assembly)), parse_json(canonical_json(case.assembly)))
                    if len(diff) != 1 or any(type(v) not in (int, float) for v in diff[0]):
                        raise ValueError("resource ablation requires one numeric parameter change")
                elif case.role in ("placement", "ordering_ablation"):
                    if case.assembly != base.assembly:
                        raise ValueError("placement/ordering comparison must preserve all hardware")
                    a, b = {j.job_id: j for j in base.jobs}, {j.job_id: j for j in case.jobs}
                    if len(a) != len(base.jobs) or len(b) != len(case.jobs) or a.keys() != b.keys():
                        raise ValueError("comparison must preserve unique complete job roster")
                    for key in a:
                        if a[key].work != b[key].work:
                            raise ValueError("comparison must preserve every actual TileWork")
                        if case.role == "placement" and a[key].dependencies != b[key].dependencies:
                            raise ValueError("placement cannot change job ordering")
                        if case.role == "ordering_ablation" and a[key].tile_id != b[key].tile_id:
                            raise ValueError("ordering cannot change job placement")
                    if a == b:
                        raise ValueError("comparison must change its declared factor")


# 只审查规范参数树的叶子差异，不解释表达式或动态导入模型。
def _differences(a: object, b: object) -> list[tuple[object, object]]:
    if isinstance(a, dict) and isinstance(b, dict) and a.keys() == b.keys():
        return [pair for key in a for pair in _differences(a[key], b[key])]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [pair for x, y in zip(a, b) for pair in _differences(x, y)]
    return [] if a == b and type(a) is type(b) else [(a, b)]


# 生产模型负责全部公式；摘要使用同一结果，执行时间和能量保持未知。
def _evaluate(configuration: dict, jobs: tuple[AssemblyJob, ...]) -> tuple[object, tuple[Metric, ...]]:
    case = next(c for c in configuration["study"].cases if c.name == configuration["selected"])
    analysis = analyze_assembly(case.assembly, jobs)
    owners = die_owners(case.assembly.resources.nodes, case.assembly.scope_id, case.assembly.die_ids)
    physical = tuple(r.resource_id for r in (*case.assembly.resources.memories, *case.assembly.resources.channels,
                                            *case.assembly.resources.links)) + tuple(t.mac_resource_id for t in case.assembly.tiles)
    scopes = (*case.assembly.die_ids, *(key for key in physical if owners[key] is None))
    payload = {"analysis": analysis, "scope_reports": project_scopes(analysis, scopes),
               "whole_report": project_scopes(analysis, (case.assembly.scope_id,))}
    metrics = (Metric(name="necessary_service_bound", value=analysis.lower_bound_s, unit="second", kind="lower_bound"),
               Metric(name="declared_memory_capacity", value=sum(size for _, size in analysis.memory_capacities), unit="byte", kind="counter"),
               Metric(name="executed_macs", value=sum(j.work.executed_macs for j in jobs), unit="MAC", kind="counter"),
               Metric(name="boundary_payload", value=sum(t.payload_bytes for t in analysis.boundary_traffic), unit="byte", kind="counter"),
               Metric(name="boundary_wire", value=sum(t.wire_bits for t in analysis.boundary_traffic), unit="bit", kind="counter"),
               Metric(name="execution_time", value=None, unit="second", kind="estimated", unknown_reason="No feasible execution/visibility/CDC scheduler"),
               Metric(name="energy", value=None, unit="joule", kind="estimated", unknown_reason="No calibrated dynamic/static physical costs"))
    return payload, metrics


# 完整清单、配置、实际工作与来源参与身份；运行异常保存failed记录，不删去反例。
def run_study(study: AssemblyStudy, *, source_revision: str = "unrecorded") -> tuple[RunRecord, ...]:
    if not isinstance(study, AssemblyStudy):
        raise TypeError("study must be AssemblyStudy")
    records = []
    for case in study.cases:
        spec = ExperimentSpec(experiment_id=case.name, implementation_id="chip-assembly/v1", mode="analytical",
            source_revision=source_revision, assumptions=(
                "Single physical resource inventory; shared capacity, work and initial service credits counted once",
                "Each TileWork is an explicit ready-work trace; complete-job dependencies only, no implicit local data ordering",
                "Potentially concurrent scratch reservations cannot overlap; ordered whole jobs may reuse a region",
                "NoC remains within one die; serial boundary links have explicit endpoint placement and independent direction IDs",
                "Scope summaries project the same resource-envelope metric; never sum subtree bounds into execution time",
                "No numerical task execution, calibrated physical costs, queues, CDC synchronization or feasible schedule claim",
            ))
        records.append(run_experiment(spec, {"study": study, "selected": case.name}, case.jobs, _evaluate))
    return tuple(records)


# 回读检查完整同源名单和真实工作；保留专业分析、全部失败与未知指标。
def summarize_records(records: tuple[RunRecord, ...]) -> tuple[dict[str, object], ...]:
    records = typed_tuple("records", records, RunRecord)
    rows, names, ids, identity = [], set(), set(), None
    if not records:
        raise ValueError("empty assembly records")
    for record in records:
        if (record.spec.implementation_id, record.spec.mode) != ("chip-assembly/v1", "analytical"):
            raise ValueError("expected chip assembly analytical records")
        config = parse_json(record.configuration_json)
        if not isinstance(config, dict) or set(config) != {"study", "selected"}:
            raise ValueError("invalid assembly snapshot")
        study = resolve_dataclass(AssemblyStudy, config["study"])
        current = content_hash({"study": config["study"], "source": record.spec.source_revision, "assumptions": record.spec.assumptions})
        if identity is not None and identity != current:
            raise ValueError("mixed assembly studies or source versions")
        identity = current
        case = next((c for c in study.cases if c.name == config["selected"]), None)
        if case is None or case.name != record.spec.experiment_id or case.name in names or record.run_id in ids:
            raise ValueError("invalid or duplicate assembly case/run identity")
        if canonical_json(case.jobs) != record.inputs_json:
            raise ValueError("assembly inputs differ from declared jobs")
        names.add(case.name)
        ids.add(record.run_id)
        rows.append({"case": case.name, "group": case.group, "role": case.role, "status": record.status,
                     "result": parse_json(record.output_json) if record.output_json is not None else None,
                     "metrics": parse_json(canonical_json(record.metrics)), "diagnostic": record.diagnostic, "identity_hash": record.identity_hash})
    if names != {c.name for c in study.cases}:
        raise ValueError("incomplete assembly case roster")
    return tuple(sorted(rows, key=lambda row: row["case"]))


# 哈希bundle先落盘，固定相对路径索引最后写；禁止覆盖已存在的研究目录。
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
        handle.write(canonical_json({"schema_version": "chip-assembly-index/v1", "runs": entries}) + "\n")
    return target


# 回读不执行模型；索引路径、run身份和完整研究协议必须一致。
def read_study(directory: str | Path) -> tuple[RunRecord, ...]:
    target = Path(directory)
    index = parse_json((target / "index.json").read_text(encoding="utf-8"))
    if not isinstance(index, dict) or set(index) != {"schema_version", "runs"} or index["schema_version"] != "chip-assembly-index/v1":
        raise ValueError("invalid assembly index")
    if not isinstance(index["runs"], list) or not index["runs"]:
        raise ValueError("assembly index needs complete runs")
    records = []
    for position, entry in enumerate(index["runs"]):
        if not isinstance(entry, dict) or set(entry) != {"directory", "run_id", "identity_hash"} or entry["directory"] != f"run-{position:04d}":
            raise ValueError("invalid assembly bundle path/order")
        record = RunRecord.from_dict(read_run(target / entry["directory"]))
        if (record.run_id, record.identity_hash) != (entry["run_id"], entry["identity_hash"]):
            raise ValueError("assembly index/record identity mismatch")
        records.append(record)
    summarize_records(tuple(records))
    return tuple(records)

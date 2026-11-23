"""外存/缓存的有限对照实验；保存实际访问、完整profile、冷初态及未知成本。"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from artifacts.storage.local import read_run, write_run
from chipmodel.common import identifier, typed_tuple
from chipmodel.composition.memory import analyze_cached_dram
from chipmodel.memory.access import MemoryAccess
from chipmodel.memory.cache import CacheParams
from chipmodel.memory.controllers.dram_read import DramReadProfile, estimate_dram_access, estimate_dram_span
from chipmodel.memory.flash.nand import NandReadProfile, NandReadRequest, analyze_nand_reads
from configuration.resolution.dataclass_config import resolve_dataclass
from contracts.results.experiment import ExperimentSpec, Metric, RunRecord
from contracts.versions.json_codec import canonical_json, content_hash, parse_json
from evaluation.experiments.runner.single import run_experiment


# 访问与策略边界；DRAM行状态条件不是由缓存命中推导。
@dataclass(frozen=True, slots=True, kw_only=True)
class MemoryWork:
    accesses: tuple[MemoryAccess, ...] = ()  # DRAM单请求或cache有序byte访问。
    nand_requests: tuple[NandReadRequest, ...] = ()  # NAND有序page/data/OOB列请求。
    row_state: Literal["hit", "closed", "conflict"] | None = None  # DRAM每行片段的隔离起点条件。
    single_row: bool = False  # DRAM单行API；True时越行必须失败。
    flush: bool = False  # Cache窗口末显式写回dirty行；默认保留dirty状态。

    # 冻结输入并验证策略开关；容量与操作支持在实际模型入口检查。
    def __post_init__(self) -> None:
        object.__setattr__(self, "accesses", typed_tuple("accesses", self.accesses, MemoryAccess))
        object.__setattr__(self, "nand_requests", typed_tuple("nand_requests", self.nand_requests, NandReadRequest))
        if self.row_state not in (None, "hit", "closed", "conflict"):
            raise ValueError("invalid memory work row_state")
        if type(self.single_row) is not bool or type(self.flush) is not bool:
            raise TypeError("single_row and flush must be bool")


# family选择已有专业入口；资源profile可独立替换，配置没有可执行字符串。
@dataclass(frozen=True, slots=True, kw_only=True)
class MemoryCase:
    name: str  # 完整研究内唯一案例身份。
    group: str  # 一组共享研究问题的基线/消融/边界案例。
    family: Literal["dram", "cached_dram", "nand"]  # 已实现的三个调用边界。
    role: Literal["baseline", "resource_ablation", "access_comparison", "boundary"]  # 单参数资源变化与访问/边界变化分开。
    profile: DramReadProfile | NandReadProfile  # 外存资源来源、几何、时钟/接口和成本。
    work: MemoryWork  # 真实访问及显式策略，研究固定冷cache/NAND buffer初态。
    cache: CacheParams | None = None  # cached_dram必需；其他家族不得附加未使用缓存。

    # 模型与工作必须匹配；错误地址和不支持读写留给运行记录保存诊断。
    def __post_init__(self) -> None:
        identifier("name", self.name)
        identifier("group", self.group)
        if self.family not in ("dram", "cached_dram", "nand") or self.role not in (
                "baseline", "resource_ablation", "access_comparison", "boundary"):
            raise ValueError("invalid memory family/role")
        if not isinstance(self.work, MemoryWork):
            raise TypeError("work must be MemoryWork")
        if self.family == "nand":
            if not isinstance(self.profile, NandReadProfile) or self.cache is not None or self.work.accesses or (
                    self.work.row_state is not None or self.work.single_row or self.work.flush):
                raise ValueError("NAND case has incompatible profile/work")
        elif not isinstance(self.profile, DramReadProfile) or self.work.nand_requests or self.work.row_state is None:
            raise ValueError("DRAM case requires profile, byte accesses and explicit row_state")
        elif self.family == "dram":
            if len(self.work.accesses) != 1 or self.cache is not None or self.work.flush:
                raise ValueError("DRAM study case requires exactly one access and no cache policy")
        elif not isinstance(self.cache, CacheParams) or self.work.single_row:
            raise ValueError("cached DRAM requires cache params and span service")


# 一组一个基线；资源消融仅改一个数值，访问对照固定全部资源。
@dataclass(frozen=True, slots=True, kw_only=True)
class MemoryStudy:
    cases: tuple[MemoryCase, ...]  # 完整有限案例名单，含失败/未知结果。
    schema_version: Literal["memory-access-study/v1"] = "memory-access-study/v1"  # 参数与比较语义版本。

    # 自动审查固定条件；不同预算资源消融不冒充同预算布局收益。
    def __post_init__(self) -> None:
        object.__setattr__(self, "cases", typed_tuple("cases", self.cases, MemoryCase))
        if self.schema_version != "memory-access-study/v1" or not self.cases or len({c.name for c in self.cases}) != len(self.cases):
            raise ValueError("invalid memory schema or duplicate/empty roster")
        for group in {c.group for c in self.cases}:
            cases = [c for c in self.cases if c.group == group]
            bases = [c for c in cases if c.role == "baseline"]
            if len(bases) != 1 or len({c.family for c in cases}) != 1:
                raise ValueError("memory group requires one baseline and one family")
            base = bases[0]
            for case in cases:
                if case.role == "access_comparison" and (case.profile, case.cache) != (base.profile, base.cache):
                    raise ValueError("access comparison must preserve all resource parameters")
                if case.role == "resource_ablation":
                    if case.work != base.work:
                        raise ValueError("resource ablation must preserve actual accesses and policy")
                    diff = _differences(parse_json(canonical_json((base.profile, base.cache))),
                                        parse_json(canonical_json((case.profile, case.cache))))
                    if len(diff) != 1 or any(type(v) not in (int, float) for v in diff[0]):
                        raise ValueError("resource ablation requires exactly one numeric parameter change")


# 比较规范JSON树的叶子；不解析任意表达式，不将布尔/策略变化伪装成数值消融。
def _differences(a: object, b: object) -> list[tuple[object, object]]:
    if isinstance(a, dict) and isinstance(b, dict) and a.keys() == b.keys():
        return [pair for k in a for pair in _differences(a[k], b[k])]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [pair for x, y in zip(a, b) for pair in _differences(x, y)]
    return [] if a == b and type(a) is type(b) else [(a, b)]


# 调用生产公式与状态机，指标只做投影；没有host time到目标性能的转换。
def _evaluate(configuration: dict, work: MemoryWork) -> tuple[object, tuple[Metric, ...]]:
    case = next(c for c in configuration["study"].cases if c.name == configuration["selected"])
    if case.family == "dram":
        function = estimate_dram_access if work.single_row else estimate_dram_span
        analysis = function(case.profile, work.accesses[0], row_state=work.row_state)
        bound = analysis.completion_time_s if work.single_row else analysis.lower_bound_s
        metrics = (Metric(name="read_conditional_bound", value=bound, unit="second", kind="lower_bound"),
                   Metric(name="capacity", value=case.profile.organization.capacity_bytes, unit="byte", kind="counter"),
                   Metric(name="peak_payload_bandwidth", value=case.profile.organization.peak_bandwidth_bytes_per_s, unit="byte_per_second", kind="estimated"))
    elif case.family == "cached_dram":
        analysis = analyze_cached_dram(case.cache, case.profile, work.accesses, row_state=work.row_state, flush=work.flush)
        metrics = (Metric(name="line_hits", value=analysis.cache.line_hits, unit="one", kind="counter"),
                   Metric(name="line_misses", value=analysis.cache.line_misses, unit="one", kind="counter"),
                   Metric(name="fill_bytes", value=analysis.cache.fill_bytes, unit="byte", kind="counter"),
                   Metric(name="writeback_bytes", value=analysis.cache.writeback_bytes, unit="byte", kind="counter"),
                   Metric(name="read_conditional_bound", value=analysis.read_lower_bound_s, unit="second", kind="lower_bound"))
    else:
        analysis = analyze_nand_reads(case.profile, work.nand_requests)
        metrics = (Metric(name="array_read_pages", value=analysis.array_read_pages, unit="one", kind="counter"),
                   Metric(name="known_serial_service", value=analysis.known_service_s, unit="second", kind="lower_bound"),
                   Metric(name="modeled_serial_time", value=analysis.modeled_time_s, unit="second", kind="estimated",
                          unknown_reason="; ".join(analysis.unknown_costs) if analysis.modeled_time_s is None else None))
    return analysis, (*metrics, Metric(name="execution_time", value=None, unit="second", kind="estimated",
        unknown_reason="Metadata and conditional analytical service only; no controller/device execution or physical calibration"))


# 每次运行保留完整名单、输入、初态、条件和版本；模型异常转换为failed记录。
def run_study(study: MemoryStudy, *, source_revision: str = "unrecorded") -> tuple[RunRecord, ...]:
    if not isinstance(study, MemoryStudy):
        raise TypeError("study must be MemoryStudy")
    records = []
    for case in study.cases:
        spec = ExperimentSpec(experiment_id=case.name, implementation_id="memory-access/v1", mode="analytical",
                              source_revision=source_revision, assumptions=(
            "DRAM each row fragment has explicit conditional state with legal PRE/ACT at origin; no schedule or refresh",
            "Full burst coverage; ranks share each channel bus; independent channel rates counted once",
            "Cache starts empty, exact LRU write-back/write-allocate; all misses read a complete line; flush is explicit",
            "NAND starts with empty one-page buffer on one die; serial array read, command and external data/OOB output",
            "Resource ablations preserve accesses and change one numeric parameter; access comparisons preserve all resources",
            "No AI task quality, target execution-time, physical-cost or device-calibration claim from successful analysis",
        ))
        records.append(run_experiment(spec, {"study": study, "selected": case.name}, case.work, _evaluate))
    return tuple(records)


# 回读检查同一研究/版本、真实输入和完整名单；保留失败与所有未知成本。
def summarize_records(records: tuple[RunRecord, ...]) -> tuple[dict[str, object], ...]:
    records = typed_tuple("records", records, RunRecord)
    rows, names, ids, identity = [], set(), set(), None
    if not records:
        raise ValueError("empty memory records")
    for record in records:
        if (record.spec.implementation_id, record.spec.mode) != ("memory-access/v1", "analytical"):
            raise ValueError("expected memory analytical records")
        config = parse_json(record.configuration_json)
        if not isinstance(config, dict) or set(config) != {"study", "selected"}:
            raise ValueError("invalid memory snapshot")
        study = resolve_dataclass(MemoryStudy, config["study"])
        current = content_hash({"study": config["study"], "source": record.spec.source_revision, "assumptions": record.spec.assumptions})
        if identity is not None and identity != current:
            raise ValueError("mixed memory studies or source versions")
        identity = current
        case = next((c for c in study.cases if c.name == config["selected"]), None)
        if case is None or case.name != record.spec.experiment_id or case.name in names or record.run_id in ids:
            raise ValueError("invalid or duplicate memory case/run identity")
        if canonical_json(case.work) != record.inputs_json:
            raise ValueError("memory inputs differ from declared comparison")
        names.add(case.name)
        ids.add(record.run_id)
        rows.append({"case": case.name, "group": case.group, "family": case.family, "role": case.role, "status": record.status,
                     "analysis": parse_json(record.output_json) if record.output_json is not None else None,
                     "metrics": parse_json(canonical_json(record.metrics)), "diagnostic": record.diagnostic, "identity_hash": record.identity_hash})
    if names != {c.name for c in study.cases}:
        raise ValueError("incomplete memory case roster")
    return tuple(sorted(rows, key=lambda row: row["case"]))


# 先写哈希校验bundle，再写固定相对路径索引；已有目录不覆盖。
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
        handle.write(canonical_json({"schema_version": "memory-study-index/v1", "runs": entries}) + "\n")
    return target


# 回读不运行模型；路径、索引、输入身份与完整比较协议必须一致。
def read_study(directory: str | Path) -> tuple[RunRecord, ...]:
    target = Path(directory)
    index = parse_json((target / "index.json").read_text(encoding="utf-8"))
    if not isinstance(index, dict) or set(index) != {"schema_version", "runs"} or index["schema_version"] != "memory-study-index/v1":
        raise ValueError("invalid memory index")
    if not isinstance(index["runs"], list) or not index["runs"]:
        raise ValueError("memory index needs complete runs")
    records = []
    for position, entry in enumerate(index["runs"]):
        if not isinstance(entry, dict) or set(entry) != {"directory", "run_id", "identity_hash"} or entry["directory"] != f"run-{position:04d}":
            raise ValueError("invalid memory bundle path/order")
        record = RunRecord.from_dict(read_run(target / entry["directory"]))
        if (record.run_id, record.identity_hash) != (entry["run_id"], entry["identity_hash"]):
            raise ValueError("memory index/record identity mismatch")
        records.append(record)
    summarize_records(tuple(records))
    return tuple(records)

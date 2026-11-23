"""Compare small linear mappings through existing independent MAC/DMA models and run records."""

from dataclasses import dataclass
from math import isfinite
from typing import Literal

from chipmodel.common import ClockDomain, PipelineParams
from chipmodel.compute.npu.mac import MacArray
from chipmodel.control.data_movement import DmaParams, estimate_dma
from chipmodel.composition.tile.digital import analyze_tile
from compiler.src.interpret.linear import execute_plan
from compiler.src.memplan.linear import count_traffic, plan_memory
from compiler.src.tiling.linear import build_plan
from contracts.plan.linear import TileShape
from contracts.results.experiment import ExperimentSpec, Metric, RunRecord
from contracts.versions.json_codec import content_hash, parse_json
from contracts.workload.linear import LinearInputs, LinearSpec, input_identity, positive_int
from evaluation.experiments.runner.single import run_experiment
from evaluation.experiments.runner.tile_mapping import LinearTileBackend, map_linear_tile
from workloads.kernels.linear import describe_work, generate_inputs
from workloads.reference.linear import compare_output, reference_linear


# Explicit single scratch/MAC/DMA capability assumption; throughput is valid only for the declared dtype.
@dataclass(frozen=True, slots=True, kw_only=True)
class LinearHardware:
    operand_dtype: Literal["int8", "float64"]  # Supported operand format; matching 64-bit accumulation/output assumed.
    scratch_capacity_bytes: int  # Shared A/B/C scratch capacity [B]; >0.
    compute_clock: ClockDomain  # MAC clock f_compute [Hz]; distinct from transfer clock.
    mac: PipelineParams  # MAC lanes P and service L/II [lane, cycle]; supplied assumptions, not calibration.
    dma_clock: ClockDomain  # Single DMA channel clock f_dma [Hz].
    dma: DmaParams  # Row-request DMA service parameters; external DRAM/NoC are not added implicitly.
    tile_backend: LinearTileBackend | None = None  # 可选逐地址 SRAM/路径分析；None 保留原 MAC/DMA 摘要边界。

    # Reject unsupported formats, invalid capacity and objects without declared hardware semantics.
    def __post_init__(self) -> None:
        if self.operand_dtype not in ("int8", "float64"):
            raise ValueError("unsupported hardware operand format")
        positive_int("scratch_capacity_bytes", self.scratch_capacity_bytes)
        for name, kind in (("compute_clock", ClockDomain), ("mac", PipelineParams),
                           ("dma_clock", ClockDomain), ("dma", DmaParams)):
            if not isinstance(getattr(self, name), kind):
                raise TypeError(f"{name} must be {kind.__name__}")
        if self.tile_backend is not None:
            if not isinstance(self.tile_backend, LinearTileBackend):
                raise TypeError("tile_backend must be LinearTileBackend")
            tile = self.tile_backend.tile
            memory = next(m for m in tile.resources.memories if m.resource_id == tile.scratch_id)
            channel = next(c for c in tile.resources.channels if c.resource_id == self.tile_backend.channel_id)
            if (tile.mac, tile.compute_clock, memory.capacity_bytes, channel.params, channel.clock) != (
                    self.mac, self.compute_clock, self.scratch_capacity_bytes, self.dma, self.dma_clock):
                raise ValueError("linear and tile hardware budgets must match")


# One candidate is explicit; unsuccessful capacity checks remain part of the comparison.
@dataclass(frozen=True, slots=True, kw_only=True)
class MappingCandidate:
    name: str  # Human-readable unique candidate identity, never a path or executable string.
    tile: TileShape  # Requested maximum tile extents [element].
    strategy: Literal["output_stationary", "reload_partials"]  # C residency/partial traffic policy.

    # Reject missing names and unknown policies; capacity feasibility is evaluated inside the recorded run.
    def __post_init__(self) -> None:
        if type(self.name) is not str or not self.name.strip():
            raise ValueError("candidate name must be nonempty")
        if not isinstance(self.tile, TileShape) or self.strategy not in ("output_stationary", "reload_partials"):
            raise ValueError("invalid tile/strategy")


# Functional work limit and quality thresholds are declared, not hidden hardware parameters.
@dataclass(frozen=True, slots=True, kw_only=True)
class LinearExperiment:
    workload: LinearSpec  # Unmapped dense task semantics and operand format.
    hardware: LinearHardware  # Single resource capability/budget and service assumptions.
    candidate: MappingCandidate  # One explicit mapping to validate and execute.
    max_macs: int = 1_000_000  # Host functional/reference work limit [MAC]; not target capacity.
    atol: float = 1e-12  # Absolute binary64 acceptance tolerance [output value]; integers compare exactly.
    rtol: float = 1e-12  # Relative binary64 acceptance tolerance [1]; integers compare exactly.

    # Check producer types and finite quality thresholds; mismatch/feasibility failures occur in the run.
    def __post_init__(self) -> None:
        for name, kind in (("workload", LinearSpec), ("hardware", LinearHardware), ("candidate", MappingCandidate)):
            if not isinstance(getattr(self, name), kind):
                raise TypeError(f"{name} must be {kind.__name__}")
        positive_int("max_macs", self.max_macs)
        for name in ("atol", "rtol"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")


# Study-level generation and finite candidate enumeration; direct evaluate_mapping accepts explicit data.
@dataclass(frozen=True, slots=True, kw_only=True)
class LinearStudy:
    workload: LinearSpec  # Shared task; all candidates compare the same actual operands.
    hardware: LinearHardware  # Shared resource budget and service rates.
    candidates: tuple[MappingCandidate, ...]  # Finite candidate list, including infeasible cases.
    seed: int = 0  # SHA256-index-v1 generation seed [1]; unsigned 64-bit.
    max_macs: int = 1_000_000  # Host execution/reference bound [MAC].
    atol: float = 1e-12  # Absolute output quality tolerance [output value].
    rtol: float = 1e-12  # Relative output quality tolerance [1].
    schema_version: Literal["linear-study/v1"] = "linear-study/v1"  # JSON study schema version.

    # Freeze unique candidate identities; validate common configuration before launching any run.
    def __post_init__(self) -> None:
        if self.schema_version != "linear-study/v1" or type(self.seed) is not int or not 0 <= self.seed < 1 << 64:
            raise ValueError("unsupported study schema or seed")
        if not isinstance(self.candidates, (list, tuple)) or not self.candidates:
            raise ValueError("study needs a nonempty candidate list")
        object.__setattr__(self, "candidates", tuple(self.candidates))
        for candidate in self.candidates:
            LinearExperiment(workload=self.workload, hardware=self.hardware, candidate=candidate,
                             max_macs=self.max_macs, atol=self.atol, rtol=self.rtol)
        if len({candidate.name for candidate in self.candidates}) != len(self.candidates):
            raise ValueError("duplicate candidate name")


# Validate numerics, count actual row payloads, and query isolated resource service; this is not event simulation.
def evaluate_mapping(params: LinearExperiment, inputs: LinearInputs) -> tuple[object, tuple[Metric, ...]]:
    spec, hardware, candidate = params.workload, params.hardware, params.candidate
    identity = input_identity(spec, inputs)
    if spec.dtype != hardware.operand_dtype:
        raise ValueError("workload dtype is unsupported by the declared MAC capability")
    if spec.m * spec.n * spec.k > params.max_macs:
        raise ValueError("experiment work exceeds max_macs")
    plan = build_plan(spec, candidate.tile, candidate.strategy)
    memory = plan_memory(spec, plan, hardware.scratch_capacity_bytes)
    traffic = count_traffic(spec, plan)
    actual = execute_plan(spec, inputs, plan, hardware.scratch_capacity_bytes, max_macs=params.max_macs)
    reference = reference_linear(spec, inputs, max_macs=params.max_macs)
    validation = compare_output(spec, actual, reference, atol=params.atol, rtol=params.rtol)
    compute = MacArray(params=hardware.mac, clock=hardware.compute_clock).estimate(traffic.executed_macs)
    dma_cycles = sum(estimate_dma(hardware.dma, hardware.dma_clock, request.payload_bytes).completion_cycles
                     for request in traffic.transfers)
    dma_time = hardware.dma_clock.seconds(dma_cycles)
    bound = max(compute.completion_time_s, dma_time)
    tile_work, tile_analysis = None, None
    if hardware.tile_backend is not None:
        tile_work = map_linear_tile(hardware.tile_backend, spec, plan, memory, traffic)
        tile_analysis = analyze_tile(hardware.tile_backend.tile, tile_work)
        bound = tile_analysis.lower_bound_s
    metrics = (
        Metric(name="executed_macs", value=traffic.executed_macs, unit="MAC", kind="counter"),
        Metric(name="external_payload", value=traffic.external_bytes, unit="byte", kind="counter"),
        Metric(name="scratch_allocation", value=memory.allocation_bytes, unit="byte", kind="counter"),
        Metric(name="ideal_compute_service", value=compute.completion_time_s, unit="second", kind="estimated"),
        Metric(name="serial_dma_service", value=dma_time, unit="second", kind="estimated"),
        Metric(name="resource_time_lower_bound", value=bound, unit="second", kind="lower_bound"),
        Metric(name="total_energy", value=None, unit="joule", kind="estimated",
               unknown_reason="No calibrated compute, memory, transfer or leakage energy profile supplied"),
    )
    return {"input_identity": identity, "plan_identity": content_hash(plan), "plan": plan,
            "logical_work": describe_work(spec), "memory": memory, "traffic": traffic,
            "output": actual, "reference": reference, "validation": validation,
            "ideal_compute": compute, "serial_dma_cycles": dma_cycles,
            "tile_work": tile_work, "tile_analysis": tile_analysis}, metrics


# The runner receives structured generation provenance alongside the mapping; it does not execute strings.
def _evaluate_generated(configuration: dict[str, object], inputs: LinearInputs) -> tuple[object, tuple[Metric, ...]]:
    return evaluate_mapping(configuration["mapping"], inputs)


# Execute a finite comparison with identical data/budget; callback failures are retained as failed RunRecords.
def run_study(study: LinearStudy, *, source_revision: str = "unrecorded") -> tuple[RunRecord, ...]:
    inputs = generate_inputs(study.workload, study.seed)
    records = []
    for candidate in study.candidates:
        params = LinearExperiment(workload=study.workload, hardware=study.hardware, candidate=candidate,
                                  max_macs=study.max_macs, atol=study.atol, rtol=study.rtol)
        tile_backend = study.hardware.tile_backend
        spec = ExperimentSpec(experiment_id=candidate.name, implementation_id=("linear-tile-analysis/v1" if tile_backend
                                                                                 else "linear-mapping-analysis/v1"),
                              mode="analytical", source_revision=source_revision, assumptions=(
                                  "Dense row-major positive extents; INT8/INT64 or binary64 without FMA",
                                  "Three byte-packed disjoint scratch arenas; A/B reloaded per update",
                                  "One serial DMA channel; one request per external tensor row; no alignment penalty",
                                  "MAC capability and service parameters are assumptions, not measured calibration",
                                  "Resource lower bound permits ideal overlap and omits undeclared dependency stalls",
                                  "No event execution, full-system timing or physical energy claim",
                              ) + (("Explicit scalar A/B reads per MAC; C register residency only within each K slice",
                                    "SRAM word transactions include DMA and compute; no implicit request coalescing",
                                    "Tile paths are explicit; external memory service may remain unknown",
                                    f"Service profile source: {tile_backend.profile_source}") if tile_backend else
                                   ("External memory and NoC service are omitted",)))
        configuration = {"mapping": params, "input_generator": {"version": "sha256-index-v1", "seed": study.seed}}
        records.append(run_experiment(spec, configuration, inputs, _evaluate_generated))
    return tuple(records)


# Rebuild comparison rows solely from immutable records; execution success and numerical quality stay separate.
def summarize_records(records: tuple[RunRecord, ...]) -> tuple[dict[str, object], ...]:
    rows = []
    for record in records:
        row = {"candidate": record.spec.experiment_id, "run_id": record.run_id, "status": record.status,
               "validation_passed": None, "external_bytes": None, "scratch_bytes": None,
               "resource_lower_bound_s": None, "diagnostic": record.diagnostic}
        if record.status == "succeeded":
            payload = parse_json(record.output_json)
            row.update(validation_passed=payload["validation"]["passed"],
                       external_bytes=payload["traffic"]["a_read_bytes"] + payload["traffic"]["b_read_bytes"]
                       + payload["traffic"]["partial_read_bytes"] + payload["traffic"]["partial_write_bytes"]
                       + payload["traffic"]["output_write_bytes"], scratch_bytes=payload["memory"]["allocation_bytes"],
                       resource_lower_bound_s=next(metric.value for metric in record.metrics
                                                  if metric.name == "resource_time_lower_bound"))
            if payload.get("tile_analysis") is not None:
                tile = payload["tile_analysis"]
                row.update(bottlenecks=tile["bottlenecks"], bank_reads=tile["scratch_service"]["bank_reads"],
                           bank_writes=tile["scratch_service"]["bank_writes"],
                           unknown_costs=tile["transfer"]["unknown_costs"])
        rows.append(row)
    return tuple(rows)

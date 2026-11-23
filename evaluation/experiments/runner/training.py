"""Finite training mapping comparison with complete semantic work and explicitly partial hardware evidence."""

from dataclasses import dataclass
from math import isfinite
import sys
from typing import Literal

from chipmodel.compute.npu.mac import MacArray
from chipmodel.control.data_movement import estimate_dma
from compiler.src.interpret.training import execute_training
from contracts.results.experiment import ExperimentSpec, Metric, RunRecord
from contracts.versions.json_codec import content_hash, parse_json
from contracts.workload.linear import positive_int
from contracts.workload.training import TrainingInputs, TrainingSpec, TrainingState, validate_learning_rate
from evaluation.experiments.runner.linear import LinearHardware, MappingCandidate
from evaluation.experiments.runner.single import run_experiment
from workloads.graphs.training import describe_training, generate_training
from workloads.reference.training import compare_training, reference_training


# One mapping has two distinct storage budgets and explicit numerical/reference settings.
@dataclass(frozen=True, slots=True, kw_only=True)
class TrainingExperiment:
    workload: TrainingSpec  # Chain dimensions and activation semantics.
    hardware: LinearHardware  # GEMM-only MAC/DMA assumptions and scratch capacity.
    candidate: MappingCandidate  # Same maximum tile/policy applied to each actual contraction shape.
    backing_capacity_bytes: int  # Packed named tensors' separate backing-store budget [B].
    learning_rate: float = 0.125  # Plain SGD learning rate; finite >=0.
    max_macs: int = 1_000_000  # Full-step GEMM host work limit [MAC], not per-layer capacity.
    atol: float = 1e-12  # Absolute output/gradient/update acceptance tolerance [value].
    rtol: float = 1e-12  # Relative acceptance tolerance [1].
    reference_backend: Literal["exact", "pytorch"] = "exact"  # Explicit optional reference, never dynamic import text.

    # Validate structured inputs before running; format and storage feasibility remain recorded runtime failures.
    def __post_init__(self) -> None:
        if not isinstance(self.workload, TrainingSpec) or not isinstance(self.hardware, LinearHardware) or not isinstance(self.candidate, MappingCandidate):
            raise TypeError("expected TrainingSpec, LinearHardware and MappingCandidate")
        positive_int("backing_capacity_bytes", self.backing_capacity_bytes)
        positive_int("max_macs", self.max_macs)
        validate_learning_rate(self.learning_rate)
        for value in (self.atol, self.rtol):
            if type(value) not in (int, float) or not isfinite(value) or value < 0:
                raise ValueError("training tolerances must be finite and nonnegative")
        if self.reference_backend not in ("exact", "pytorch"):
            raise ValueError("unsupported training reference backend")


# A finite study resets every candidate to identical old weights/data; this is not sequential SGD across candidates.
@dataclass(frozen=True, slots=True, kw_only=True)
class TrainingStudy:
    workload: TrainingSpec  # Shared semantics and loss definition.
    hardware: LinearHardware  # Shared declared resource capability and scratch.
    candidates: tuple[MappingCandidate, ...]  # Explicit finite mapping list, including infeasible points.
    backing_capacity_bytes: int  # Shared named-tensor memory budget [B].
    learning_rate: float = 0.125  # Shared plain SGD rate.
    seed: int = 7  # Training SHA256-index-v1 seed [uint64].
    max_macs: int = 1_000_000  # Full-step host functional/reference work bound [MAC].
    atol: float = 1e-12  # Absolute numerical tolerance [value].
    rtol: float = 1e-12  # Relative numerical tolerance [1].
    schema_version: Literal["training-study/v1"] = "training-study/v1"  # Study configuration version.

    # Freeze candidates and validate shared producer settings without executing a target operation.
    def __post_init__(self) -> None:
        if self.schema_version != "training-study/v1" or type(self.seed) is not int or not 0 <= self.seed < 1 << 64:
            raise ValueError("unsupported training study schema/seed")
        if not isinstance(self.candidates, (tuple, list)) or not self.candidates:
            raise ValueError("training study needs candidates")
        object.__setattr__(self, "candidates", tuple(self.candidates))
        for candidate in self.candidates:
            TrainingExperiment(workload=self.workload, hardware=self.hardware, candidate=candidate,
                               backing_capacity_bytes=self.backing_capacity_bytes, learning_rate=self.learning_rate,
                               max_macs=self.max_macs, atol=self.atol, rtol=self.rtol)
        if len({candidate.name for candidate in self.candidates}) != len(self.candidates):
            raise ValueError("duplicate training candidate name")


# Compare the whole step; only the GEMM subset has target service estimates, while full-step time remains unknown.
def evaluate_training(params: TrainingExperiment, inputs: tuple[TrainingState, TrainingInputs]) -> tuple[object, tuple[Metric, ...]]:
    state, data = inputs
    if params.hardware.tile_backend is not None:
        raise ValueError("training Tile address mapping is not implemented; use the declared MAC/DMA-only backend")
    if params.hardware.operand_dtype != "float64":
        raise ValueError("training requires explicit float64 hardware capability")
    result, plan = execute_training(params.workload, state, data, params.learning_rate, params.candidate.tile,
                                    params.candidate.strategy, scratch_capacity_bytes=params.hardware.scratch_capacity_bytes,
                                    backing_capacity_bytes=params.backing_capacity_bytes, max_macs=params.max_macs)
    if params.reference_backend == "exact":
        reference = reference_training(params.workload, state, data, params.learning_rate, max_macs=params.max_macs)
    else:
        from evaluation.calibration.pytorch_training import pytorch_training
        reference = pytorch_training(params.workload, state, data, params.learning_rate)
    validation = compare_training(result, reference, atol=params.atol, rtol=params.rtol)
    gemms = tuple(operation for operation in plan.operations if operation.kind == "gemm")
    macs = sum(operation.traffic.executed_macs for operation in gemms)
    gemm_bytes = sum(operation.traffic.external_bytes for operation in gemms)
    sizes = {tensor.name: tensor.size_bytes for tensor in plan.tensors}
    auxiliary_bytes = sum(sum(sizes[name] for name in operation.reads + operation.writes)
                          for operation in plan.operations if operation.kind != "gemm")
    compute = MacArray(params=params.hardware.mac, clock=params.hardware.compute_clock).estimate(macs)
    dma_cycles = sum(estimate_dma(params.hardware.dma, params.hardware.dma_clock, transfer.payload_bytes).completion_cycles
                     for operation in gemms for transfer in operation.traffic.transfers)
    bound = max(compute.completion_time_s, params.hardware.dma_clock.seconds(dma_cycles))
    metrics = (
        Metric(name="gemm_macs", value=macs, unit="MAC", kind="counter"),
        Metric(name="gemm_payload", value=gemm_bytes, unit="byte", kind="counter"),
        Metric(name="auxiliary_logical_payload", value=auxiliary_bytes, unit="byte", kind="counter"),
        Metric(name="backing_peak", value=plan.memory.peak_bytes, unit="byte", kind="counter"),
        Metric(name="gemm_scratch_peak", value=max(operation.scratch.allocation_bytes for operation in gemms), unit="byte", kind="counter"),
        Metric(name="gemm_resource_lower_bound", value=bound, unit="second", kind="lower_bound"),
        Metric(name="step_time", value=None, unit="second", kind="estimated",
               unknown_reason="No complete service/schedule model for loss, activation, transpose and SGD; GEMM bound is partial"),
        Metric(name="step_energy", value=None, unit="joule", kind="estimated", unknown_reason="No calibrated full-step compute/memory energy profile"),
    )
    return {"input_identity": content_hash({"workload": params.workload, "state": state, "data": data}),
            "plan_identity": content_hash(plan), "plan": plan, "logical_work": describe_training(params.workload),
            "result": result, "reference": reference, "validation": validation,
            "validation_passed": all(item.passed for item in validation.values()), "gemm_dma_cycles": dma_cycles}, metrics


# Keep generation and external version provenance in effective configuration while passing typed parameters to execution.
def _evaluate_config(configuration: dict[str, object], inputs: tuple[TrainingState, TrainingInputs]) -> tuple[object, tuple[Metric, ...]]:
    return evaluate_training(configuration["experiment"], inputs)


# Freeze the actual reference environment in run identity and preserve failed candidates as independent attempts.
def run_training_study(study: TrainingStudy, *, source_revision: str = "unrecorded", reference_backend: str = "exact") -> tuple[RunRecord, ...]:
    if reference_backend == "pytorch":
        from evaluation.calibration.pytorch_training import pytorch_environment
        environment = pytorch_environment()
    elif reference_backend == "exact":
        environment = {"backend": "fractions-reverse-mode/v1", "python": sys.version}
    else:
        raise ValueError("unsupported training reference backend")
    inputs = generate_training(study.workload, study.seed)
    records = []
    for candidate in study.candidates:
        params = TrainingExperiment(workload=study.workload, hardware=study.hardware, candidate=candidate,
                                    backing_capacity_bytes=study.backing_capacity_bytes, learning_rate=study.learning_rate,
                                    max_macs=study.max_macs, atol=study.atol, rtol=study.rtol, reference_backend=reference_backend)
        spec = ExperimentSpec(experiment_id=candidate.name, implementation_id="linear-training-analysis/v1", mode="analytical",
                              source_revision=source_revision, assumptions=(
                                  "Bias-free float64 Linear chain; optional hidden ReLU, derivative at zero=0; mean MSE and plain SGD",
                                  "One old parameter snapshot per candidate; all backward operations precede all updates",
                                  "Explicit materialized transposes; serial backing allocation lifetimes; separate GEMM scratch",
                                  "Auxiliary payload counts one read of each input and one write of each output per operation",
                                  "GEMM subset lower bound only; auxiliary register/storage service and total step timing unmodeled",
                                  "Reference is functional evidence only; no GPU, event timing, training convergence or energy claim",
                              ))
        configuration = {"experiment": params, "reference_environment": environment,
                         "input_generator": {"version": "training-sha256-index-v1", "seed": study.seed}}
        records.append(run_experiment(spec, configuration, inputs, _evaluate_config))
    return tuple(records)


# Reconstruct comparison rows from verified run records without rerunning training or importing an external framework.
def summarize_training(records: tuple[RunRecord, ...]) -> tuple[dict[str, object], ...]:
    rows = []
    for record in records:
        row = {"candidate": record.spec.experiment_id, "run_id": record.run_id, "status": record.status,
               "validation_passed": None, "loss": None, "next_version": None, "diagnostic": record.diagnostic}
        if record.status == "succeeded":
            output = parse_json(record.output_json)
            row.update(validation_passed=output["validation_passed"], loss=output["result"]["loss"],
                       next_version=output["result"]["next_state"]["version"])
            row.update({metric.name: metric.value for metric in record.metrics})
        rows.append(row)
    return tuple(rows)

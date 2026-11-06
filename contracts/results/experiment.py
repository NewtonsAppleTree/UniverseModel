"""Small experiment boundary; hardware payloads retain their own schemas and semantics."""

from dataclasses import dataclass
from math import isfinite
from typing import Literal

from contracts.versions.json_codec import canonical_json, content_hash, parse_json
from contracts.units.metrics import validate_metric_unit


# An identity is an explicit nonempty string, never an inferred device capability.
def _identity(name: str, value: str) -> None:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")


# The experiment declares purpose, execution semantics, implementation revision and omitted mechanisms.
@dataclass(frozen=True, slots=True, kw_only=True)
class ExperimentSpec:
    experiment_id: str  # Experiment identity; no physical unit.
    implementation_id: str  # Explicit adapter/model version; never a dynamic import path.
    mode: Literal["functional", "analytical", "static_schedule", "event"]  # Target result semantics.
    source_revision: str  # Code revision/source reference; 'unrecorded' means incomplete provenance.
    assumptions: tuple[str, ...]  # Applicability and coverage statements; immutable text.
    schema_version: Literal["universal-experiment/v1"] = "universal-experiment/v1"  # Public schema ID.

    # Freeze assumptions and reject unsupported schema/mode; no hardware behavior is inferred.
    def __post_init__(self) -> None:
        for name in ("experiment_id", "implementation_id", "source_revision"):
            _identity(name, getattr(self, name))
        if self.schema_version != "universal-experiment/v1":
            raise ValueError("unsupported experiment schema_version")
        if self.mode not in ("functional", "analytical", "static_schedule", "event"):
            raise ValueError("unsupported experiment mode")
        if isinstance(self.assumptions, str):
            raise TypeError("assumptions must be a sequence of statements")
        object.__setattr__(self, "assumptions", tuple(self.assumptions))
        for statement in self.assumptions:
            _identity("assumption", statement)


# A metric carries one unit and evidence kind; unknown physical cost is value=None with a reason.
@dataclass(frozen=True, slots=True, kw_only=True)
class Metric:
    name: str  # Metric identity within one run; unique, e.g. completion_time.
    value: int | float | None  # Numeric observation/estimate; None denotes unknown, never zero.
    unit: str  # Canonical unit token, e.g. second, byte, MAC, conversion; no implicit conversion.
    kind: Literal["counter", "estimated", "lower_bound", "simulated"]  # Evidence/measurement basis.
    clock_domain: str | None = None  # Required for unit='cycle'; unrelated clocks cannot be summed.
    unknown_reason: str | None = None  # Mandatory iff value=None; omitted cost is not a complete total.

    # Reject bool/nonfinite values and unbound cycles; unit conversion belongs to the producer.
    def __post_init__(self) -> None:
        _identity("name", self.name)
        validate_metric_unit(self.unit)
        if self.kind not in ("counter", "estimated", "lower_bound", "simulated"):
            raise ValueError("unsupported metric kind")
        if self.value is not None:
            if type(self.value) not in (int, float):
                raise TypeError("metric value must be int, float or None")
            if type(self.value) is float and not isfinite(self.value):
                raise ValueError("metric value must be finite")
            if self.unknown_reason is not None:
                raise ValueError("known metric cannot have unknown_reason")
        else:
            _identity("unknown_reason", self.unknown_reason)
        if self.unit == "cycle" and self.clock_domain is None:
            raise ValueError("cycle metric requires clock_domain")
        if self.clock_domain is not None:
            _identity("clock_domain", self.clock_domain)


# Immutable snapshots distinguish run success, target metrics and host wall time; identity excludes observations.
@dataclass(frozen=True, slots=True, kw_only=True)
class RunRecord:
    run_id: str  # Unique attempt identity; identical inputs may have different run_id.
    spec: ExperimentSpec  # Frozen purpose, implementation revision, assumptions and mode.
    configuration_json: str  # Canonical effective configuration snapshot; units remain in producer fields.
    inputs_json: str  # Canonical input snapshot; this small boundary stores inline data.
    output_json: str | None  # Canonical producer output; None for a failed execution.
    metrics: tuple[Metric, ...]  # Immutable observations with independent units and evidence kinds.
    status: Literal["succeeded", "failed"]  # Execution status; does not assert functional validation.
    host_elapsed_s: float  # Host callback elapsed time [s]; never a simulated target metric.
    diagnostic: str | None = None  # Failure type/message; successful execution has no diagnostic.
    schema_version: Literal["universal-run/v1"] = "universal-run/v1"  # Public record schema ID.

    # Check snapshots, unique metrics and terminal consistency; failed attempts have no fabricated result.
    def __post_init__(self) -> None:
        _identity("run_id", self.run_id)
        if not isinstance(self.spec, ExperimentSpec):
            raise TypeError("spec must be ExperimentSpec")
        if self.schema_version != "universal-run/v1":
            raise ValueError("unsupported run schema_version")
        if self.status not in ("succeeded", "failed"):
            raise ValueError("unsupported run status")
        if type(self.host_elapsed_s) not in (int, float) or not isfinite(self.host_elapsed_s) or self.host_elapsed_s < 0:
            raise ValueError("host_elapsed_s must be finite and nonnegative")
        for name in ("configuration_json", "inputs_json", "output_json"):
            snapshot = getattr(self, name)
            if snapshot is None and name == "output_json":
                continue
            if type(snapshot) is not str or canonical_json(parse_json(snapshot)) != snapshot:
                raise ValueError(f"{name} must be canonical JSON")
        object.__setattr__(self, "metrics", tuple(self.metrics))
        if any(not isinstance(metric, Metric) for metric in self.metrics):
            raise TypeError("metrics must contain Metric objects")
        if len({metric.name for metric in self.metrics}) != len(self.metrics):
            raise ValueError("duplicate metric name")
        if self.spec.mode != "event" and any(metric.kind == "simulated" for metric in self.metrics):
            raise ValueError("simulated metric requires an event experiment")
        if self.status == "succeeded":
            if self.output_json is None or self.diagnostic is not None:
                raise ValueError("succeeded run requires output and no diagnostic")
        else:
            _identity("diagnostic", self.diagnostic)
            if self.output_json is not None or self.metrics:
                raise ValueError("failed run cannot claim output or complete metrics")

    # Experiment identity H(spec, effective configuration, inputs); seed/initial state must be explicit inputs.
    @property
    def identity_hash(self) -> str:
        return content_hash({"spec": self.spec, "configuration": parse_json(self.configuration_json),
                             "inputs": parse_json(self.inputs_json)})

    # Return a fresh JSON-owned view; editing it cannot mutate the immutable record snapshots.
    def to_dict(self) -> dict[str, object]:
        return {"schema_version": self.schema_version, "run_id": self.run_id,
                "identity_hash": self.identity_hash, "spec": parse_json(canonical_json(self.spec)),
                "configuration": parse_json(self.configuration_json), "inputs": parse_json(self.inputs_json),
                "output": parse_json(self.output_json) if self.output_json is not None else None,
                "metrics": parse_json(canonical_json(self.metrics)), "status": self.status,
                "host_elapsed_s": self.host_elapsed_s, "diagnostic": self.diagnostic}

    # Decode this exact version and rerun semantic checks; byte integrity alone is not schema validation.
    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "RunRecord":
        expected = {"schema_version", "run_id", "identity_hash", "spec", "configuration", "inputs",
                    "output", "metrics", "status", "host_elapsed_s", "diagnostic"}
        if not isinstance(value, dict) or set(value) != expected:
            raise ValueError("run record has missing or unsupported fields")
        if not isinstance(value["spec"], dict) or not isinstance(value["metrics"], list):
            raise TypeError("run spec/metrics must be a JSON object/array")
        if any(not isinstance(metric, dict) for metric in value["metrics"]):
            raise TypeError("metric must be a JSON object")
        if value["status"] == "failed" and value["output"] is not None:
            raise ValueError("failed run cannot contain output")
        result = cls(run_id=value["run_id"], spec=ExperimentSpec(**value["spec"]),
                     configuration_json=canonical_json(value["configuration"]), inputs_json=canonical_json(value["inputs"]),
                     output_json=canonical_json(value["output"]) if value["status"] == "succeeded" else None,
                     metrics=tuple(Metric(**metric) for metric in value["metrics"]), status=value["status"],
                     host_elapsed_s=value["host_elapsed_s"], diagnostic=value["diagnostic"],
                     schema_version=value["schema_version"])
        if result.identity_hash != value["identity_hash"]:
            raise ValueError("experiment identity hash mismatch")
        return result

"""One injected callable per experiment; this runner does not simulate hardware time."""

from collections.abc import Callable
from copy import deepcopy
from time import perf_counter
from typing import TypeVar
from uuid import uuid4

from contracts.results.experiment import ExperimentSpec, Metric, RunRecord
from contracts.versions.json_codec import canonical_json


P = TypeVar("P")  # Producer parameter type; no shared hardware base class.
I = TypeVar("I")  # Explicit input type; no mandatory global workload schema.
R = TypeVar("R")  # Producer output type; projected only at the persistence boundary.


# Snapshot explicit inputs, invoke a fresh copied boundary, and record success/failure without hidden stages.
def run_experiment(spec: ExperimentSpec, configuration: P, inputs: I,
                   execute: Callable[[P, I], tuple[R, tuple[Metric, ...]]]) -> RunRecord:
    """execute(config, inputs) -> (producer payload, metrics); callback closure state is caller-owned.

    Host wall time is bookkeeping. Target cycles/time are only those explicitly returned by the producer.
    Structural snapshot errors propagate before invocation; callback/result errors become failed records.
    """
    if not isinstance(spec, ExperimentSpec):
        raise TypeError("spec must be ExperimentSpec")
    configuration_json, inputs_json = canonical_json(configuration), canonical_json(inputs)
    local_configuration, local_inputs = deepcopy(configuration), deepcopy(inputs)
    start = perf_counter()
    try:
        payload, metrics = execute(local_configuration, local_inputs)
        return RunRecord(run_id=uuid4().hex, spec=spec, configuration_json=configuration_json,
                         inputs_json=inputs_json, output_json=canonical_json(payload), metrics=tuple(metrics),
                         status="succeeded", host_elapsed_s=perf_counter() - start)
    except Exception as exc:
        return RunRecord(run_id=uuid4().hex, spec=spec, configuration_json=configuration_json,
                         inputs_json=inputs_json, output_json=None, metrics=(), status="failed",
                         host_elapsed_s=perf_counter() - start, diagnostic=f"{type(exc).__name__}: {exc}")

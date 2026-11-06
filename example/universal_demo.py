"""python -m example.universal_demo --case adc|dma: independently configured local queries."""

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Literal

from artifacts.storage.local import write_run
from chipmodel.common import ClockDomain
from chipmodel.compute.cim.periphery.adc import AdcParams, IdealAdc
from chipmodel.control.data_movement import DmaParams, estimate_dma
from configuration.resolution.dataclass_config import load_config
from contracts.results.experiment import ExperimentSpec, Metric
from contracts.versions.json_codec import parse_json
from evaluation.experiments.runner.single import run_experiment


# ADC query parameters; latency/II are supplied software assumptions, not measured circuit data.
@dataclass(frozen=True, slots=True, kw_only=True)
class AdcConfiguration:
    clock: ClockDomain  # Fixed conversion clock; f [Hz], Tclk=1/f [s].
    adc: AdcParams  # ADC resolution, range [V], P lanes and L/II [cycle].


# Explicit sampled inputs; batch time is measured from all samples being ready.
@dataclass(frozen=True, slots=True, kw_only=True)
class AdcInputs:
    voltages_v: tuple[float, ...]  # Sampled voltages [V]; order is preserved in ADC codes.


# One standalone ADC case; JSON fields resolve to the same model parameters as direct Python calls.
@dataclass(frozen=True, slots=True, kw_only=True)
class AdcCase:
    configuration: AdcConfiguration  # Producer-owned parameter schema, independent of full chip topology.
    inputs: AdcInputs  # Explicit finite sample vector [V].
    schema_version: Literal["universal-adc-example/v1"] = "universal-adc-example/v1"  # Example schema ID.


# DMA query parameters; no implicit SRAM, link or destination service is added.
@dataclass(frozen=True, slots=True, kw_only=True)
class DmaConfiguration:
    clock: ClockDomain  # Fixed DMA clock f [Hz]; local cycles convert via C/f.
    dma: DmaParams  # DMA bus width [B/cycle], burst size [B], startup/control [cycle].


# One explicit copy payload; transfer granularity remains the DMA model's responsibility.
@dataclass(frozen=True, slots=True, kw_only=True)
class DmaInputs:
    payload_bytes: int  # Logical bytes to copy [B]; count>=0, no implicit weight traffic.


# One standalone DMA case; input and configuration have separate immutable identities.
@dataclass(frozen=True, slots=True, kw_only=True)
class DmaCase:
    configuration: DmaConfiguration  # Producer-owned parameter schema.
    inputs: DmaInputs  # Copy request data, independent of hardware configuration.
    schema_version: Literal["universal-dma-example/v1"] = "universal-dma-example/v1"  # Example schema ID.


# Quantize explicit voltages and estimate C=L+(ceil(S/P)-1)II; clipping remains visible in the output.
def evaluate_adc(configuration: AdcConfiguration, inputs: AdcInputs) -> tuple[object, tuple[Metric, ...]]:
    adc = IdealAdc(params=configuration.adc, frequency_hz=configuration.clock.frequency_hz)
    samples = adc.convert_many(inputs.voltages_v)
    estimate = adc.estimate_batch(len(samples))
    return {"samples": samples, "batch": estimate}, (
        Metric(name="adc_conversions", value=len(samples), unit="conversion", kind="counter"),
        Metric(name="completion_cycles", value=estimate.completion_cycles, unit="cycle", kind="estimated",
               clock_domain=configuration.clock.domain_id),
        Metric(name="completion_time", value=estimate.completion_time_s, unit="second", kind="estimated"),
        Metric(name="energy", value=None, unit="joule", kind="estimated",
               unknown_reason="No circuit characterization supplied"),
    )


# Estimate C=startup+bursts*overhead+ceil(payload/width); empty requests consume zero target cycles.
def evaluate_dma(configuration: DmaConfiguration, inputs: DmaInputs) -> tuple[object, tuple[Metric, ...]]:
    estimate = estimate_dma(configuration.dma, configuration.clock, inputs.payload_bytes)
    return estimate, (
        Metric(name="payload", value=inputs.payload_bytes, unit="byte", kind="counter"),
        Metric(name="completion_cycles", value=estimate.completion_cycles, unit="cycle", kind="estimated",
               clock_domain=configuration.clock.domain_id),
        Metric(name="completion_time", value=estimate.completion_time_s, unit="second", kind="estimated"),
    )


# Choose an explicit adapter, resolve JSON/overrides, run once, and optionally commit a new local bundle.
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=("adc", "dma"), default="adc")
    parser.add_argument("--config", type=Path, help="JSON case; defaults to config/experiments/universal_<case>.json")
    parser.add_argument("--set", action="append", default=[], metavar="FIELD=JSON", help="explicit dotted override")
    parser.add_argument("--output", type=Path, help="new output directory; existing runs are never overwritten")
    parser.add_argument("--source-revision", default="unrecorded", help="explicit code revision; include dirty-state reference")
    args = parser.parse_args()
    try:
        overrides = {}
        for item in args.set:
            key, separator, value = item.partition("=")
            if not separator or key in overrides:
                raise ValueError("each --set must have a unique FIELD=JSON path")
            overrides[key] = parse_json(value)
        path = args.config or Path(__file__).resolve().parents[1] / "config" / "experiments" / f"universal_{args.case}.json"
        case_type, execute = (AdcCase, evaluate_adc) if args.case == "adc" else (DmaCase, evaluate_dma)
        case = load_config(case_type, path, overrides=overrides)
        spec = ExperimentSpec(experiment_id=f"standalone-{args.case}", implementation_id=f"universal-{args.case}-demo/v1",
                              mode="analytical", source_revision=args.source_revision,
                              assumptions=("Isolated service; all input ready; no contention or backpressure",
                                           "Clock and L/II are software assumptions; no silicon performance claim"))
        record = run_experiment(spec, case.configuration, case.inputs, execute)
        if args.output is not None:
            write_run(record, args.output)
        print(json.dumps(record.to_dict(), ensure_ascii=False, indent=2, allow_nan=False))
        return int(record.status != "succeeded")
    except (OSError, TypeError, ValueError) as exc:
        parser.exit(2, f"configuration/artifact error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())

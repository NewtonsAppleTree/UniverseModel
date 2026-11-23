"""Deterministic dense training-chain fixtures and full semantic work accounting."""

from dataclasses import dataclass
from hashlib import sha256

from contracts.workload.linear import positive_int
from contracts.workload.training import TrainingInputs, TrainingSpec, TrainingState


# Keep dense contractions, auxiliary arithmetic, comparisons and data rearrangements in distinct counters.
@dataclass(frozen=True, slots=True, kw_only=True)
class TrainingWork:
    gemm_macs: int  # 3*B*sum(d_l*d_(l+1)) [MAC]; includes every input and weight gradient.
    scalar_arithmetic_operations: int  # Mean-MSE 4*B*d_L+2 plus SGD 2*P [scalar operation].
    comparisons: int  # Forward/backward ReLU 2*B*sum(hidden_widths) [comparison]; zero for identity.
    selections: int  # Forward/backward ReLU 2*B*sum(hidden_widths) [selection]; no floating multiply implied.
    transpose_elements: int  # sum(B*d_l + d_l*d_(l+1)) [element]; explicit backward input/weight transposes.
    parameter_bytes: int  # 8*P [B]; excludes activations, gradients, next state and scratch.


# Derive logical actions independently of the compiler schedule; do not approximate training with only 3x forward.
def describe_training(spec: TrainingSpec) -> TrainingWork:
    p, b = spec.parameter_elements, spec.batch_size
    hidden = b * sum(spec.widths[1:-1]) if spec.hidden_activation == "relu" else 0
    return TrainingWork(gemm_macs=3 * b * p, scalar_arithmetic_operations=4 * b * spec.widths[-1] + 2 + 2 * p,
                        comparisons=2 * hidden, selections=2 * hidden,
                        transpose_elements=b * sum(spec.widths[:-1]) + p, parameter_bytes=8 * p)


# SHA256-index-v1 uses distinct tensor labels, immutable dyadic float data and a materialization bound.
def generate_training(spec: TrainingSpec, seed: int, *, max_elements: int = 1_000_000) -> tuple[TrainingState, TrainingInputs]:
    if type(seed) is not int or not 0 <= seed < 1 << 64:
        raise ValueError("seed must be an unsigned 64-bit integer")
    positive_int("max_elements", max_elements)
    count = spec.parameter_elements + spec.batch_size * (spec.widths[0] + spec.widths[-1])
    if count > max_elements:
        raise ValueError("training input materialization exceeds max_elements")
    sizes = {"x": spec.batch_size * spec.widths[0], "target": spec.batch_size * spec.widths[-1]}
    sizes.update({f"w{i}": a * b for i, (a, b) in enumerate(zip(spec.widths, spec.widths[1:]))})
    buffers = {label: tuple((sha256(f"training-input/v1:{seed}:{label}:{index}".encode("ascii")).digest()[0] % 17 - 8) / 16.0
                            for index in range(size)) for label, size in sizes.items()}
    state = TrainingState(version=0, weights=tuple(buffers[f"w{i}"] for i in range(len(spec.widths) - 1)))
    return state, TrainingInputs(x=buffers["x"], target=buffers["target"])

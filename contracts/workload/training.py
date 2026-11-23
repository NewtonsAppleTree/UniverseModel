"""Small immutable float64 training boundary; no framework, compiler or hardware dependency."""

from dataclasses import dataclass
from math import isfinite
from typing import Literal

from contracts.versions.json_codec import content_hash
from contracts.workload.linear import positive_int


# Snapshot an explicitly binary64 flat buffer; no coercion of bool, integer or nonfinite values.
def float_buffer(values: tuple[float, ...]) -> tuple[float, ...]:
    if not isinstance(values, (list, tuple)) or not values:
        raise ValueError("expected a nonempty float64 list/tuple")
    result = tuple(values)
    if any(type(value) is not float or not isfinite(value) for value in result):
        raise ValueError("training buffers require finite Python floats")
    return result


# Validate SGD learning rate; zero is useful for a gradient-only observation with a new step version.
def validate_learning_rate(value: float) -> None:
    if type(value) not in (int, float) or not isfinite(value) or value < 0:
        raise ValueError("learning_rate must be finite and nonnegative")


# Bias-free dense chain; hidden ReLU has derivative zero at zero and MSE averages all output elements.
@dataclass(frozen=True, slots=True, kw_only=True)
class TrainingSpec:
    batch_size: int  # Batch B [sample]; positive.
    widths: tuple[int, ...]  # Input, optional hidden, output widths [element]; at least two positive widths.
    hidden_activation: Literal["identity", "relu"] = "relu"  # Applied between Linear layers only.
    dtype: Literal["float64"] = "float64"  # All inputs, weights, activations, gradients and updates use binary64.
    schema_version: Literal["linear-training/v1"] = "linear-training/v1"  # Fixed mean-MSE/plain-SGD semantics.

    # Freeze dimensions and reject unsupported formats before allocating parameters or activations.
    def __post_init__(self) -> None:
        positive_int("batch_size", self.batch_size)
        if not isinstance(self.widths, (tuple, list)) or not 2 <= len(self.widths) <= 17:
            raise ValueError("widths must describe 1 to 16 Linear layers")
        object.__setattr__(self, "widths", tuple(self.widths))
        for width in self.widths:
            positive_int("width", width)
        if self.hidden_activation not in ("identity", "relu") or self.dtype != "float64" or self.schema_version != "linear-training/v1":
            raise ValueError("unsupported training semantics")

    # All dense parameter elements P=sum(d_l*d_(l+1)); bias and optimizer states are absent.
    @property
    def parameter_elements(self) -> int:
        return sum(a * b for a, b in zip(self.widths, self.widths[1:]))

    # Full forward, all dW and all dX execute 3*B*P MAC, excluding separate scalar actions.
    @property
    def gemm_macs(self) -> int:
        return 3 * self.batch_size * self.parameter_elements


# A step consumes an immutable parameter snapshot; matrix W_l is row-major [in_width,out_width].
@dataclass(frozen=True, slots=True, kw_only=True)
class TrainingState:
    version: int  # Logical update version [step]; >=0, incremented even for learning_rate=0.
    weights: tuple[tuple[float, ...], ...]  # Owned immutable parameter buffers; no optimizer momentum state.

    # Freeze nested buffers; dimensions are checked against a TrainingSpec at the consumer boundary.
    def __post_init__(self) -> None:
        if type(self.version) is not int or self.version < 0:
            raise ValueError("state version must be a nonnegative integer")
        if not isinstance(self.weights, (tuple, list)) or not self.weights:
            raise ValueError("weights must be a nonempty sequence")
        object.__setattr__(self, "weights", tuple(float_buffer(buffer) for buffer in self.weights))

    # Bind both parameter contents and logical version, preventing same-version foreign-gradient reuse.
    @property
    def identity_hash(self) -> str:
        return content_hash(self)


# Actual training data is part of every saved experiment, not inferred from shape or seed alone.
@dataclass(frozen=True, slots=True, kw_only=True)
class TrainingInputs:
    x: tuple[float, ...]  # Row-major input [B,d_0].
    target: tuple[float, ...]  # Row-major regression target [B,d_L].

    # Own immutable finite binary64 snapshots.
    def __post_init__(self) -> None:
        object.__setattr__(self, "x", float_buffer(self.x))
        object.__setattr__(self, "target", float_buffer(self.target))


# Gradients identify the exact parameter snapshot used during differentiation.
@dataclass(frozen=True, slots=True, kw_only=True)
class TrainingGradients:
    state_identity: str  # SHA256 of source TrainingState; distinct from a workload or run identity.
    state_version: int  # Source parameter version [step]; must match before applying SGD.
    weights: tuple[tuple[float, ...], ...]  # dLoss/dW_l in the same layout as each weight.
    x: tuple[float, ...]  # dLoss/dX [B,d_0]; all input gradients are computed.

    # Freeze results and require a valid source identity; semantic shapes are validated separately.
    def __post_init__(self) -> None:
        if type(self.state_identity) is not str or len(self.state_identity) != 64 or any(c not in "0123456789abcdef" for c in self.state_identity):
            raise ValueError("gradient source identity must be lowercase SHA256")
        frozen = TrainingState(version=self.state_version, weights=self.weights)
        object.__setattr__(self, "weights", frozen.weights)
        object.__setattr__(self, "x", float_buffer(self.x))


# Numeric result separates pre-update prediction/loss/gradients from the next immutable state.
@dataclass(frozen=True, slots=True, kw_only=True)
class TrainingResult:
    loss: float  # Mean squared error sum((prediction-target)^2)/(B*d_L) [value squared].
    prediction: tuple[float, ...]  # Pre-update output [B,d_L].
    gradients: TrainingGradients  # Derivatives with respect to the old state and input.
    next_state: TrainingState  # Updated weights, version=old.version+1; original state remains unchanged.

    # Reject nonfinite loss/prediction and objects lacking the declared result types.
    def __post_init__(self) -> None:
        if type(self.loss) is not float or not isfinite(self.loss) or self.loss < 0:
            raise ValueError("loss must be finite nonnegative float64")
        object.__setattr__(self, "prediction", float_buffer(self.prediction))
        if not isinstance(self.gradients, TrainingGradients) or not isinstance(self.next_state, TrainingState):
            raise TypeError("expected TrainingGradients and TrainingState")


# Validate parameter and data shapes without referring to any mapped plan or target resource.
def validate_training(spec: TrainingSpec, state: TrainingState, inputs: TrainingInputs) -> None:
    if not isinstance(spec, TrainingSpec) or not isinstance(state, TrainingState) or not isinstance(inputs, TrainingInputs):
        raise TypeError("expected training spec, state and inputs")
    sizes = tuple(a * b for a, b in zip(spec.widths, spec.widths[1:]))
    if tuple(map(len, state.weights)) != sizes:
        raise ValueError("weight shapes do not match training widths")
    if len(inputs.x) != spec.batch_size * spec.widths[0] or len(inputs.target) != spec.batch_size * spec.widths[-1]:
        raise ValueError("training input/target shape mismatch")

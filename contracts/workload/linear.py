"""Versioned dense linear semantics shared by workloads, compiler and evaluation."""

from dataclasses import dataclass
from math import isfinite
from typing import Literal

from contracts.versions.json_codec import content_hash


# Require a positive discrete extent/capacity; bool is never an integer parameter.
def positive_int(name: str, value: int) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be an int")
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


# A[M,K] @ B[K,N] -> C[M,N]; dense row-major, alpha=1, beta=0, no bias/transpose/FMA.
@dataclass(frozen=True, slots=True, kw_only=True)
class LinearSpec:
    m: int  # Output rows M [element]; >0.
    n: int  # Output columns N [element]; >0, N=1 also represents MatVec.
    k: int  # Reduction extent K [element]; >0.
    dtype: Literal["int8", "float64"] = "int8"  # Operand format; signed INT8 or finite IEEE binary64.
    schema_version: Literal["dense-linear/v1"] = "dense-linear/v1"  # Semantics version, not a hardware identity.

    # Guarantee any INT8 product reduction fits INT64, including intermediate partial sums.
    def __post_init__(self) -> None:
        for name in ("m", "n", "k"):
            positive_int(name, getattr(self, name))
        if self.dtype not in ("int8", "float64") or self.schema_version != "dense-linear/v1":
            raise ValueError("unsupported dense linear dtype/schema")
        if self.dtype == "int8" and self.k * 128 * 128 > (1 << 63) - 1:
            raise ValueError("worst-case INT8 reduction exceeds INT64")

    # Byte-addressable operand storage: INT8=1 B, binary64=8 B per element.
    @property
    def operand_bytes(self) -> int:
        return 1 if self.dtype == "int8" else 8

    # Accumulators and outputs use INT64 or binary64, both 8 B per element.
    @property
    def result_bytes(self) -> int:
        return 8

    # Explicit accumulation/output format; output is never implicitly requantized to INT8.
    @property
    def result_dtype(self) -> str:
        return "int64" if self.dtype == "int8" else "float64"

    # Bind mappings and input identities to complete versioned semantics.
    @property
    def identity_hash(self) -> str:
        return content_hash(self)


# Inline immutable row-major operands; shape and format are validated against a LinearSpec.
@dataclass(frozen=True, slots=True, kw_only=True)
class LinearInputs:
    a: tuple[int | float, ...]  # Flattened A, offset i*K+p [element value].
    b: tuple[int | float, ...]  # Flattened B, offset p*N+j [element value].

    # Take ownership of immutable scalar sequences; reject bool, nonfinite values and nested buffers.
    def __post_init__(self) -> None:
        for name in ("a", "b"):
            raw = getattr(self, name)
            if not isinstance(raw, (list, tuple)):
                raise TypeError(f"{name} must be a list/tuple of scalars")
            values = tuple(raw)
            for value in values:
                if type(value) not in (int, float):
                    raise TypeError(f"{name} elements must be int/float, not bool or nested values")
                if type(value) is float and not isfinite(value):
                    raise ValueError(f"{name} elements must be finite")
            object.__setattr__(self, name, values)


# Check lengths and actual scalar representation before any consumer accesses an operand.
def validate_inputs(spec: LinearSpec, inputs: LinearInputs) -> None:
    if not isinstance(spec, LinearSpec) or not isinstance(inputs, LinearInputs):
        raise TypeError("expected LinearSpec and LinearInputs")
    if len(inputs.a) != spec.m * spec.k or len(inputs.b) != spec.k * spec.n:
        raise ValueError("operand lengths do not match A[M,K], B[K,N]")
    for values in (inputs.a, inputs.b):
        if spec.dtype == "int8":
            if any(type(value) is not int or not -128 <= value <= 127 for value in values):
                raise ValueError("INT8 operands require integer values in [-128,127]")
        elif any(type(value) is not float for value in values):
            raise TypeError("float64 operands require explicit Python floats")


# Content identity includes shape/format semantics as well as both actual operand buffers.
def input_identity(spec: LinearSpec, inputs: LinearInputs) -> str:
    validate_inputs(spec, inputs)
    return content_hash({"workload": spec, "inputs": inputs})

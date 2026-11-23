"""Exact integer/rational reference; does not import compiler or hardware implementations."""

from dataclasses import dataclass
from fractions import Fraction
from math import isfinite

from contracts.workload.linear import LinearInputs, LinearSpec, positive_int, validate_inputs


# Scalar dot products use exact arithmetic; binary64 reference rounds only the final exact sum.
def reference_linear(spec: LinearSpec, inputs: LinearInputs, *, max_macs: int = 1_000_000) -> tuple[int | float, ...]:
    validate_inputs(spec, inputs)
    positive_int("max_macs", max_macs)
    if spec.m * spec.n * spec.k > max_macs:
        raise ValueError("reference work exceeds max_macs")
    values = []
    for row in range(spec.m):
        for column in range(spec.n):
            if spec.dtype == "int8":
                result = sum(inputs.a[row * spec.k + p] * inputs.b[p * spec.n + column] for p in range(spec.k))
            else:
                exact = sum((Fraction(inputs.a[row * spec.k + p]) * Fraction(inputs.b[p * spec.n + column])
                             for p in range(spec.k)), Fraction(0))
                result = float(exact)
                if not isfinite(result):
                    raise ValueError("reference result is not finite binary64")
            values.append(result)
    return tuple(values)


# Output quality is an explicit result, separate from execution success and performance claims.
@dataclass(frozen=True, slots=True, kw_only=True)
class LinearValidation:
    passed: bool  # True iff all values satisfy the declared comparison rule.
    mismatched_indices: tuple[int, ...]  # Flat C indices failing equality/tolerance [element index].
    max_absolute_error: int | float  # max(abs(actual-reference)) [output value].


# INT64 requires exact values/types; floats require |actual-reference| <= atol+rtol*|reference|.
def compare_output(spec: LinearSpec, actual: tuple[int | float, ...], reference: tuple[int | float, ...], *,
                   atol: float = 1e-12, rtol: float = 1e-12) -> LinearValidation:
    for name, value in (("atol", atol), ("rtol", rtol)):
        if type(value) not in (int, float) or not isfinite(value) or value < 0:
            raise ValueError(f"{name} must be finite and nonnegative")
    if len(actual) != spec.m * spec.n or len(reference) != spec.m * spec.n:
        raise ValueError("output/reference length does not match C[M,N]")
    errors, failed = [], []
    expected_type = int if spec.dtype == "int8" else float
    for index, (value, expected) in enumerate(zip(actual, reference)):
        if type(value) is not expected_type or type(expected) is not expected_type:
            raise TypeError("output/reference scalar type does not match result_dtype")
        if expected_type is float and (not isfinite(value) or not isfinite(expected)):
            raise ValueError("output/reference must be finite")
        error = abs(value - expected)
        threshold = 0 if expected_type is int else atol + rtol * abs(expected)
        if expected_type is float and (not isfinite(error) or not isfinite(threshold)):
            raise ValueError("comparison arithmetic exceeds binary64 range")
        errors.append(error)
        if error > threshold:
            failed.append(index)
    return LinearValidation(passed=not failed, mismatched_indices=tuple(failed), max_absolute_error=max(errors))

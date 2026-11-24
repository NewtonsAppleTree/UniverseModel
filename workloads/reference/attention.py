"""Exact input dot products and Decimal softmax reference; numerical evidence, not target execution."""

from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
from math import isfinite

from contracts.workload.attention import AttentionInputs, AttentionSpec, attention_buffer, attention_identity, validate_attention
from contracts.workload.linear import positive_int


# Local precision is a host reference setting; explicit context prevents ambient Decimal state changing results.
def _context(precision_digits: int) -> Context:
    if type(precision_digits) is not int or not 32 <= precision_digits <= 256:
        raise ValueError('reference precision_digits must be an integer in [32,256]')
    return Context(prec=precision_digits, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999)


# Shift exact rational logits before Decimal conversion, preserving small differences under a huge common offset.
def _probabilities(scores: tuple[Fraction, ...]) -> tuple[Decimal, ...]:
    largest = max(scores)
    shifted = tuple(score - largest for score in scores)
    exps = tuple((Decimal(value.numerator) / Decimal(value.denominator)).exp() for value in shifted)
    denominator = sum(exps, Decimal(0))
    return tuple(value / denominator for value in exps)


# Observations round to binary64; overflow is rejected, tiny probabilities/results follow binary64 underflow to zero.
def _observed(value: Decimal) -> float:
    result = float(value)
    if not isfinite(result):
        raise ValueError('Attention reference output exceeds finite binary64')
    return result


# Standalone stable softmax over one nonempty finite row; no implicit mask, temperature or target SFU precision.
def reference_softmax(logits: tuple[float, ...], *, precision_digits: int = 80) -> tuple[float, ...]:
    values = attention_buffer('logits', logits)
    if not values:
        raise ValueError('softmax requires a nonempty row')
    with localcontext(_context(precision_digits)):
        return tuple(_observed(p) for p in _probabilities(tuple(map(Fraction, values))))


# Retain reference intermediates and source identity; successful evaluation is not an AI task-quality verdict.
@dataclass(frozen=True, slots=True)
class AttentionReference:
    input_identity: str  # SHA256 of complete Attention spec and actual Q/K/V.
    output: tuple[float, ...]  # Row-major [B,Hq,Sq,Dv], rounded reference output.
    probabilities: tuple[float, ...]  # [B,Hq,Sq,Skv], exact zero for masked positions; rounded observations.
    precision_digits: int  # Decimal significant digits used for exp/normalization/weighted sums [digit].


# Numerical agreement is separate from execution success and downstream classification quality.
@dataclass(frozen=True, slots=True)
class AttentionValidation:
    passed: bool  # Every output satisfies abs(actual-reference)<=atol+rtol*abs(reference).
    max_absolute_error: float  # Largest absolute output difference [output value].
    mismatched_indices: tuple[int, ...]  # Flat output indices outside tolerance.


# Bind the numerical oracle to the exact task/data and validate all observed outputs with explicit tolerances.
def compare_attention(spec: AttentionSpec, inputs: AttentionInputs, actual: tuple[float, ...], reference: AttentionReference, *,
                      atol: float = 1e-12, rtol: float = 1e-12) -> AttentionValidation:
    if not isinstance(reference, AttentionReference) or reference.input_identity != attention_identity(spec, inputs):
        raise ValueError('Attention reference input identity mismatch')
    actual = attention_buffer('actual', actual)
    expected = attention_buffer('reference', reference.output)
    if len(actual) != spec.batch_size*spec.query_heads*spec.query_length*spec.value_dim or len(actual) != len(expected):
        raise ValueError('Attention comparison output shape mismatch')
    for name, value in (('atol', atol), ('rtol', rtol)):
        if type(value) not in (float, int) or not isfinite(value) or value < 0:
            raise ValueError(f'{name} must be finite and nonnegative')
    errors, mismatches = [], []
    for i, (value, target) in enumerate(zip(actual, expected)):
        error, tolerance = abs(value-target), atol+rtol*abs(target)
        if not isfinite(error) or not isfinite(tolerance):
            raise ValueError('Attention comparison exceeds binary64 range')
        errors.append(error)
        if error > tolerance:
            mismatches.append(i)
    return AttentionValidation(not mismatches, max(errors), tuple(mismatches))


# Reference uses valid pairs only, exact rational QK/scale and Decimal exp/AV; full probability storage is host-bounded.
def reference_attention(spec: AttentionSpec, inputs: AttentionInputs, *, precision_digits: int = 80,
                        max_score_pairs: int = 100_000, max_macs: int = 1_000_000) -> AttentionReference:
    validate_attention(spec, inputs)
    context = _context(precision_digits)
    positive_int('max_score_pairs', max_score_pairs)
    positive_int('max_macs', max_macs)
    if spec.score_pairs > max_score_pairs or spec.visible_pairs * (spec.key_dim + spec.value_dim) > max_macs:
        raise ValueError('Attention reference exceeds max_score_pairs/max_macs')
    output, probabilities = [], []
    d, dv, sq, sk = spec.key_dim, spec.value_dim, spec.query_length, spec.kv_length
    group_size = spec.query_heads // spec.kv_heads
    with localcontext(context):
        for batch in range(spec.batch_size):
            for head in range(spec.query_heads):
                kv_group = batch * spec.kv_heads + head // group_size
                for row in range(sq):
                    visible = spec.query_start + row + 1 if spec.causal else sk
                    qbase = ((batch * spec.query_heads + head) * sq + row) * d
                    scores = tuple(sum((Fraction(inputs.q[qbase + feature]) * Fraction(inputs.k[(kv_group * sk + key) * d + feature])
                                        for feature in range(d)), Fraction(0)) * Fraction(spec.scale) for key in range(visible))
                    weights = _probabilities(scores)
                    for feature in range(dv):
                        value = sum((weight * Decimal.from_float(inputs.v[(kv_group * sk + key) * dv + feature])
                                     for key, weight in enumerate(weights)), Decimal(0))
                        output.append(_observed(value))
                    probabilities.extend(_observed(p) for p in weights)
                    probabilities.extend(0.0 for _ in range(sk - visible))
    return AttentionReference(attention_identity(spec, inputs), tuple(output), tuple(probabilities), precision_digits)

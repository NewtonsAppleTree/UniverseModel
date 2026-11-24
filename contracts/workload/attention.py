"""Hardware-independent scaled dot-product Attention and immutable logical KV boundaries."""

from dataclasses import dataclass
from math import isfinite
from typing import Literal

from contracts.versions.json_codec import content_hash
from contracts.workload.linear import positive_int


# Logical versions/positions are nonnegative Python integers, excluding bool.
def nonnegative_int(name: str, value: int) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f'{name} must be a nonnegative Python int')
    return value


# Freeze an explicit finite binary64 buffer; empty arrays are useful for an empty KV snapshot.
def attention_buffer(name: str, values: tuple[float, ...]) -> tuple[float, ...]:
    if not isinstance(values, (tuple, list)):
        raise TypeError(f'{name} must be a list/tuple')
    result = tuple(values)
    if any(type(value) is not float or not isfinite(value) for value in result):
        raise ValueError(f'{name} requires finite explicit Python floats')
    return result


# Q[B,Hq,Sq,D], K[B,Hkv,Skv,D], V[B,Hkv,Skv,Dv]; contiguous Hq/Hkv query groups share K/V.
@dataclass(frozen=True, slots=True, kw_only=True)
class AttentionSpec:
    batch_size: int  # B [sample], positive; all samples share logical lengths in this version.
    query_heads: int  # Hq [head], positive multiple of Hkv.
    kv_heads: int  # Hkv [head]; shared logical K/V heads, not physically replicated to Hq.
    query_length: int  # Sq [token position], positive and independent of Skv.
    kv_length: int  # Skv [token position], positive visible-plus-masked key extent.
    key_dim: int  # D [element/head]; Q and K contraction dimensions are equal.
    value_dim: int  # Dv [element/head]; may differ from D.
    scale: float  # Positive logit multiplier [1]; conventionally 1/sqrt(D), always explicit.
    causal: bool = False  # If true, query i can use key j iff j <= query_start+i.
    query_start: int = 0  # Absolute query start within the K sequence [token position]; noncausal requires 0.
    dtype: Literal['float64'] = 'float64'  # Input/output storage semantics; no low-precision or quantized claim.
    schema_version: Literal['attention/v1'] = 'attention/v1'  # No projection, bias, dropout, position encoding or backward.

    # Validate grouping and causal alignment before any tensor allocation; every row has at least one visible key.
    def __post_init__(self) -> None:
        for name in ('batch_size', 'query_heads', 'kv_heads', 'query_length', 'kv_length', 'key_dim', 'value_dim'):
            positive_int(name, getattr(self, name))
        if self.query_heads % self.kv_heads:
            raise ValueError('query_heads must be divisible by kv_heads')
        nonnegative_int('query_start', self.query_start)
        if type(self.causal) is not bool:
            raise TypeError('causal must be bool')
        if (self.causal and self.query_start + self.query_length > self.kv_length) or (not self.causal and self.query_start != 0):
            raise ValueError('query_start/length is incompatible with causal KV extent')
        if type(self.scale) not in (int, float):
            raise TypeError('scale must be a Python int/float')
        try:
            scale = float(self.scale)
        except OverflowError as exc:
            raise ValueError('scale exceeds binary64') from exc
        if not isfinite(scale) or scale <= 0:
            raise ValueError('scale must be finite and positive')
        object.__setattr__(self, 'scale', scale)
        if self.dtype != 'float64' or self.schema_version != 'attention/v1':
            raise ValueError('unsupported Attention dtype/schema')

    # Complete rectangular score extent R=B*Hq*Sq*Skv [pair], independent of mask exploitation.
    @property
    def score_pairs(self) -> int:
        return self.batch_size * self.query_heads * self.query_length * self.kv_length

    # Causal valid pairs sum_i(query_start+i+1); no claim that hardware skips masked pairs.
    @property
    def visible_pairs(self) -> int:
        q = self.query_length
        return self.batch_size * self.query_heads * (q * (self.query_start + 1) + q * (q - 1) // 2) if self.causal else self.score_pairs

    # Unique logical Q/K/V elements; GQA sharing counts K/V by Hkv.
    @property
    def input_elements(self) -> int:
        return self.batch_size * (self.query_heads * self.query_length * self.key_dim
                                  + self.kv_heads * self.kv_length * (self.key_dim + self.value_dim))

    # Bind data, profiles and references to complete semantics, including scale and causal alignment.
    @property
    def identity_hash(self) -> str:
        return content_hash(self)


# Independent immutable logical input buffers; flat order follows the spec's B/head/token/feature axes.
@dataclass(frozen=True, slots=True, kw_only=True)
class AttentionInputs:
    q: tuple[float, ...]  # Query values [B,Hq,Sq,D], not raw model activations before projection.
    k: tuple[float, ...]  # Key values [B,Hkv,Skv,D].
    v: tuple[float, ...]  # Value values [B,Hkv,Skv,Dv].

    # Caller lists cannot mutate a task after its identity or reference has been computed.
    def __post_init__(self) -> None:
        for name in ('q', 'k', 'v'):
            object.__setattr__(self, name, attention_buffer(name, getattr(self, name)))


# Shape validation is independent of the reference algorithm, mapping and target resources.
def validate_attention(spec: AttentionSpec, inputs: AttentionInputs) -> None:
    if not isinstance(spec, AttentionSpec) or not isinstance(inputs, AttentionInputs):
        raise TypeError('expected AttentionSpec and AttentionInputs')
    b, h, s = spec.batch_size, spec.kv_heads, spec.kv_length
    expected = (b * spec.query_heads * spec.query_length * spec.key_dim, b * h * s * spec.key_dim, b * h * s * spec.value_dim)
    if tuple(len(getattr(inputs, name)) for name in ('q', 'k', 'v')) != expected:
        raise ValueError('Q/K/V lengths do not match Attention axes')


# Same shape with different values, head grouping or causal alignment is a different workload input.
def attention_identity(spec: AttentionSpec, inputs: AttentionInputs) -> str:
    validate_attention(spec, inputs)
    return content_hash({'spec': spec, 'inputs': inputs})


# Logical KV capacity/shape; no pages, physical placement, eviction or request scheduler.
@dataclass(frozen=True, slots=True, kw_only=True)
class KvCacheSpec:
    batch_size: int  # B [sample], uniform token count across samples.
    kv_heads: int  # Hkv [head], not query heads.
    key_dim: int  # D [element/head] for K.
    value_dim: int  # Dv [element/head] for V.
    max_tokens: int  # Logical token limit per sample [token], positive.
    schema_version: Literal['logical-kv/v1'] = 'logical-kv/v1'  # Binary64 contiguous logical snapshots only.

    # Capacity bounds logical data; physical page padding/replication require a separate mapping.
    def __post_init__(self) -> None:
        for name in ('batch_size', 'kv_heads', 'key_dim', 'value_dim', 'max_tokens'):
            positive_int(name, getattr(self, name))
        if self.schema_version != 'logical-kv/v1':
            raise ValueError('unsupported logical KV schema')

    # Maximum logical K/V payload B*Hkv*Tmax*(D+Dv)*8 [B], excluding metadata.
    @property
    def capacity_bytes(self) -> int:
        return self.batch_size * self.kv_heads * self.max_tokens * (self.key_dim + self.value_dim) * 8


# Immutable state owned by the caller; explicit identity/version permits branches but does not arbitrate concurrent commits.
@dataclass(frozen=True, slots=True, kw_only=True)
class KvCacheState:
    spec: KvCacheSpec  # Logical batch/head/dimension/capacity contract.
    version: int = 0  # Append generation [update], independent of token count.
    tokens: int = 0  # Resident contiguous positions per sample [token], 0..max_tokens.
    k: tuple[float, ...] = ()  # Current keys [B,Hkv,tokens,D].
    v: tuple[float, ...] = ()  # Current values [B,Hkv,tokens,Dv].

    # Validate complete snapshots, including empty initialization; never infer missing tensor contents.
    def __post_init__(self) -> None:
        if not isinstance(self.spec, KvCacheSpec):
            raise TypeError('spec must be KvCacheSpec')
        nonnegative_int('version', self.version)
        nonnegative_int('tokens', self.tokens)
        if self.tokens > self.spec.max_tokens:
            raise ValueError('KV logical token capacity exceeded')
        groups = self.spec.batch_size * self.spec.kv_heads
        for name, dim in (('k', self.spec.key_dim), ('v', self.spec.value_dim)):
            values = attention_buffer(name, getattr(self, name))
            if len(values) != groups * self.tokens * dim:
                raise ValueError(f'KV {name} length does not match snapshot')
            object.__setattr__(self, name, values)

    # Resident logical K/V payload; immutable host copies are not target transfer events.
    @property
    def resident_bytes(self) -> int:
        return (len(self.k) + len(self.v)) * 8

    # Identity includes dimensions, capacity, contents and logical version; same-version foreign state is distinct.
    @property
    def identity_hash(self) -> str:
        return content_hash(self)

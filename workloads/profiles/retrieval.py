"""Finite real-task protocol: fixed splits, validation-only scale selection and explicit numeric ablations."""

from dataclasses import dataclass
from math import isfinite

from contracts.workload.linear import positive_int
from workloads.datasets.tabular import TabularSource


# Rounding changes stored support coordinates, not input storage dtype or inferred packed hardware capacity.
@dataclass(frozen=True, slots=True, kw_only=True)
class RetrievalVariant:
    name: str  # Unique numeric-policy label.
    key_decimals: int | None = None  # Decimal rounding places [-2,12]; None preserves standardized support values.
    expected_quality: bool = True  # Reviewed quality-gate expectation, separate from execution status.

    # Preserve a deliberately coarse negative control without treating quality failure as an exception.
    def __post_init__(self) -> None:
        if type(self.name) is not str or not self.name.strip() or type(self.expected_quality) is not bool:
            raise ValueError('invalid variant name/expectation')
        if self.key_decimals is not None and (type(self.key_decimals) is not int or not -2<=self.key_decimals<=12):
            raise ValueError('key_decimals must be None or integer in [-2,12]')


# Repeated held-out splits are paired comparisons, not independent population samples or a language-model workload.
@dataclass(frozen=True, slots=True, kw_only=True)
class RetrievalProfile:
    source: TabularSource  # Original real dataset and exact byte/source metadata.
    seeds: tuple[int, ...]  # Complete unique finite split seed roster [uint64].
    train_per_class: int  # Support and normalization samples per class [sample].
    validation_per_class: int  # Scale-selection samples per class [sample]; all remaining rows are test.
    scale_candidates: tuple[float, ...]  # Fixed positive RBF inverse-bandwidth grid [1], selected on validation accuracy.
    variants: tuple[RetrievalVariant, ...]  # Complete numeric ablation roster, exactly one unrounded baseline.
    minimum_accuracy: float = 0.8  # Held-out absolute accuracy requirement [1], fixed before execution.
    maximum_accuracy_drop: float = 0.05  # Allowed degradation from same-split unrounded baseline [1].
    query_tile: int = 8  # Query rows per fused shared-KV mapping block [sample].
    scratch_capacity_bytes: int = 8_000_000  # Explicit analytic scratch reservation budget [B], not a measured device.
    backing_capacity_bytes: int = 8_000_000  # Explicit analytic original/temporary backing budget [B].
    max_samples: int = 10_000  # Local dataset materialization guard [sample].
    max_file_bytes: int = 1_000_000  # Local source byte limit [B].
    max_macs: int = 1_000_000  # Per-Attention reference/interpreter contraction guard [MAC].
    max_score_pairs: int = 100_000  # Per-reference probability storage limit [pair].
    schema_version: str = 'retrieval-quality/v1'  # Standardization, RBF, split, selection and quality-gate protocol.

    # Freeze shared budgets and variants; baseline must use unrounded keys and no candidate changes the test split.
    def __post_init__(self) -> None:
        if not isinstance(self.source,TabularSource) or self.schema_version!='retrieval-quality/v1':
            raise ValueError('invalid retrieval source/schema')
        if not isinstance(self.seeds,(tuple,list)) or not self.seeds or any(type(s) is not int or not 0<=s<1<<64 for s in self.seeds) or len(set(self.seeds))!=len(self.seeds):
            raise ValueError('seeds must be unique uint64 values')
        object.__setattr__(self,'seeds',tuple(self.seeds))
        if not isinstance(self.scale_candidates,(tuple,list)) or not self.scale_candidates:
            raise ValueError('scale_candidates must be nonempty')
        if any(type(v) not in (float,int) or not isfinite(v) or v<=0 for v in self.scale_candidates):
            raise ValueError('scale_candidates must be finite positive numbers')
        scales = tuple(float(v) for v in self.scale_candidates)
        if len(set(scales))!=len(scales):
            raise ValueError('duplicate scale candidate')
        object.__setattr__(self,'scale_candidates',scales)
        if not isinstance(self.variants,(tuple,list)) or not self.variants or any(not isinstance(v,RetrievalVariant) for v in self.variants):
            raise ValueError('variants require RetrievalVariant values')
        object.__setattr__(self,'variants',tuple(self.variants))
        if len({v.name for v in self.variants})!=len(self.variants) or sum(v.key_decimals is None for v in self.variants)!=1:
            raise ValueError('variants need unique names and exactly one unrounded baseline')
        for name in ('train_per_class','validation_per_class','query_tile','scratch_capacity_bytes','backing_capacity_bytes','max_samples','max_file_bytes','max_macs','max_score_pairs'):
            positive_int(name,getattr(self,name))
        for name in ('minimum_accuracy','maximum_accuracy_drop'):
            value = getattr(self,name)
            if type(value) not in (float,int) or not isfinite(value) or not 0<=value<=1:
                raise ValueError('accuracy thresholds must be finite in [0,1]')

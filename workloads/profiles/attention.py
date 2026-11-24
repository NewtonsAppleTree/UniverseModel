"""Finite explicit Attention scenarios, preserving source and host verification budgets."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from contracts.workload.attention import AttentionInputs, AttentionSpec
from contracts.workload.linear import positive_int
from workloads.datasets.attention import AttentionDataset, load_attention_dataset
from workloads.kernels.attention import generate_attention


# One scenario is a task/input choice; differing shapes are not automatically comparable hardware speedups.
@dataclass(frozen=True, slots=True, kw_only=True)
class AttentionCase:
    name: str  # Unique case identifier within the suite.
    spec: AttentionSpec  # Complete mathematical task; names such as decode do not override its semantics.
    purpose: str  # Research/verification question and source assumption for this scenario.
    seed: int | None = 0  # attention-input/v1 uint64 seed; None iff a dataset is selected.
    dataset: AttentionDataset | None = None  # Explicit local data provenance; mutually exclusive with seed generation.
    expected_status: Literal['succeeded', 'failed'] = 'succeeded'  # Reviewed fixture expectation, never the actual outcome.

    # Freeze only valid explicit source choices; malformed data/profile feasibility can still be retained as run failures.
    def __post_init__(self) -> None:
        if not isinstance(self.spec, AttentionSpec):
            raise TypeError('spec must be AttentionSpec')
        for name in ('name', 'purpose'):
            if type(getattr(self, name)) is not str or not getattr(self, name).strip():
                raise ValueError(f'{name} must be a nonempty string')
        if self.dataset is None:
            if type(self.seed) is not int or not 0 <= self.seed < 1 << 64:
                raise ValueError('generated case needs a uint64 seed')
        elif not isinstance(self.dataset, AttentionDataset) or self.seed is not None:
            raise ValueError('dataset case requires AttentionDataset and seed=None')
        if self.expected_status not in ('succeeded', 'failed'):
            raise ValueError('unsupported expected_status')


# Fixed finite roster and budgets; no unrecorded sampling, arrival scheduler or implicit model-zoo presets.
@dataclass(frozen=True, slots=True, kw_only=True)
class AttentionSuite:
    suite_id: str  # Workload-suite/revision identity.
    source_note: str  # Provenance and representativeness boundary for the case selection.
    cases: tuple[AttentionCase, ...]  # Complete ordered case list, including expected failures.
    precision_digits: int = 80  # Host Decimal reference precision [digit], 32..256.
    max_elements: int = 100_000  # Maximum materialized input elements [element], not target memory capacity.
    max_score_pairs: int = 100_000  # Host full probability-matrix limit [pair].
    max_macs: int = 1_000_000  # Host reference visible-pair contraction limit [MAC].
    max_file_bytes: int = 4_194_304  # Maximum local dataset file bytes read/parsed [B].
    schema_version: Literal['attention-suite/v1'] = 'attention-suite/v1'  # Versioned finite-suite semantics.

    # Require a nonempty unique roster and valid host limits; input size failures happen per case and remain visible.
    def __post_init__(self) -> None:
        for name in ('suite_id', 'source_note'):
            if type(getattr(self, name)) is not str or not getattr(self, name).strip():
                raise ValueError(f'{name} must be a nonempty string')
        if not isinstance(self.cases, (tuple, list)) or not self.cases or any(not isinstance(c, AttentionCase) for c in self.cases):
            raise ValueError('cases must be a nonempty AttentionCase list/tuple')
        object.__setattr__(self, 'cases', tuple(self.cases))
        if len({case.name for case in self.cases}) != len(self.cases):
            raise ValueError('duplicate Attention case name')
        for name in ('max_elements', 'max_score_pairs', 'max_macs', 'max_file_bytes'):
            positive_int(name, getattr(self, name))
        if type(self.precision_digits) is not int or not 32 <= self.precision_digits <= 256:
            raise ValueError('precision_digits must be in [32,256]')
        if self.schema_version != 'attention-suite/v1':
            raise ValueError('unsupported Attention suite schema')


# Shared preparation enforces the same shape/materialization bounds for generated and file-backed inputs.
def prepare_attention(case: AttentionCase, suite: AttentionSuite, *, data_root: str | Path) -> AttentionInputs:
    if not isinstance(case, AttentionCase) or not isinstance(suite, AttentionSuite) or case not in suite.cases:
        raise ValueError('case must belong to the declared suite')
    if case.spec.input_elements > suite.max_elements:
        raise ValueError('Attention input materialization exceeds max_elements')
    if case.dataset is not None:
        return load_attention_dataset(case.dataset, data_root, case.spec, max_file_bytes=suite.max_file_bytes)
    return generate_attention(case.spec, case.seed, max_elements=suite.max_elements)

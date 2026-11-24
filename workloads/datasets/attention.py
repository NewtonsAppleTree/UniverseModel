"""Bounded local Attention fixtures with explicit provenance and raw-byte identity."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Literal

from contracts.versions.json_codec import parse_json
from contracts.workload.attention import AttentionInputs, AttentionSpec, validate_attention
from contracts.workload.linear import positive_int


# Dataset metadata is a declared source boundary, not proof of representativeness, licensing or task quality.
@dataclass(frozen=True, slots=True, kw_only=True)
class AttentionDataset:
    dataset_id: str  # Stable dataset/revision label, separate from workload and run identities.
    relative_path: str  # Portable relative POSIX path within the caller-supplied data root.
    sha256: str  # SHA256 of exact JSON bytes, including whitespace/newlines.
    source: str  # Source revision/generation method or external attribution.
    kind: Literal['synthetic', 'external']  # Distinguish a generated fixture from externally supplied data.
    split: Literal['train', 'validation', 'test']  # Declared use; loader does not infer statistical independence.
    usage_terms: str  # Source-provided usage information or explicit unknown status.
    limitations: str  # Coverage and representativeness limits, retained in the experiment configuration.

    # Refuse ambiguous paths and missing source declarations before accessing the filesystem.
    def __post_init__(self) -> None:
        for name in ('dataset_id', 'relative_path', 'source', 'usage_terms', 'limitations'):
            value = getattr(self, name)
            if type(value) is not str or not value.strip():
                raise ValueError(f'{name} must be a nonempty string')
        if type(self.sha256) is not str or len(self.sha256) != 64 or any(c not in '0123456789abcdef' for c in self.sha256):
            raise ValueError('dataset sha256 must be lowercase SHA256')
        path = PurePosixPath(self.relative_path)
        if (path.is_absolute() or '\\' in self.relative_path or ':' in self.relative_path
                or any(part in ('', '.', '..') for part in self.relative_path.split('/'))):
            raise ValueError('dataset path must be a normalized relative POSIX file path')
        if self.kind not in ('synthetic', 'external') or self.split not in ('train', 'validation', 'test'):
            raise ValueError('unsupported dataset kind/split')


# Check containment and byte identity before parsing strict JSON; the file binds data to the complete Attention spec.
def load_attention_dataset(dataset: AttentionDataset, root: str | Path, spec: AttentionSpec, *,
                           max_file_bytes: int = 4_194_304) -> AttentionInputs:
    if not isinstance(dataset, AttentionDataset) or not isinstance(spec, AttentionSpec):
        raise TypeError('expected AttentionDataset and AttentionSpec')
    positive_int('max_file_bytes', max_file_bytes)
    base = Path(root).resolve()
    path = (base / dataset.relative_path).resolve()
    if not path.is_relative_to(base):
        raise ValueError('dataset resolves outside the declared data root')
    with path.open('rb') as handle:
        raw = handle.read(max_file_bytes + 1)
    if len(raw) > max_file_bytes:
        raise ValueError('dataset exceeds max_file_bytes')
    if sha256(raw).hexdigest() != dataset.sha256:
        raise ValueError('dataset raw SHA256 mismatch')
    value = parse_json(raw.decode('utf-8'))
    if (not isinstance(value, dict) or set(value) != {'schema_version', 'spec_identity', 'inputs'}
            or value['schema_version'] != 'attention-input-file/v1' or value['spec_identity'] != spec.identity_hash):
        raise ValueError('dataset schema/spec identity mismatch')
    if not isinstance(value['inputs'], dict) or set(value['inputs']) != {'q', 'k', 'v'}:
        raise ValueError('dataset requires exactly Q/K/V buffers')
    inputs = AttentionInputs(**value['inputs'])
    validate_attention(spec, inputs)
    return inputs

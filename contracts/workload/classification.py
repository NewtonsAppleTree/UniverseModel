"""Immutable tabular classification observations; independent of classifier and target hardware."""

from dataclasses import dataclass

from contracts.versions.json_codec import content_hash
from contracts.workload.attention import attention_buffer


# Original rows and labels retain their source order; partitioning and preprocessing must be explicit downstream.
@dataclass(frozen=True, slots=True, kw_only=True)
class ClassificationData:
    features: tuple[tuple[float, ...], ...]  # [sample,feature] finite measurements; source metadata supplies units.
    labels: tuple[int, ...]  # Zero-based class labels [class index].
    feature_names: tuple[str, ...]  # Ordered unique feature/measurement names, including units where applicable.
    class_names: tuple[str, ...]  # Ordered unique class names; tie breaking uses this order.
    source_sha256: str  # Exact original file byte identity; transformations create distinct data identity.

    # Freeze nested values and reject ambiguous rows, labels and source identities.
    def __post_init__(self) -> None:
        for name in ('feature_names','class_names'):
            values = getattr(self,name)
            if not isinstance(values,(list,tuple)) or not values or any(type(v) is not str or not v.strip() for v in values) or len(set(values)) != len(values):
                raise ValueError(f'{name} requires unique nonempty names')
            object.__setattr__(self,name,tuple(values))
        if len(self.class_names) < 2:
            raise ValueError('classification needs at least two classes')
        if not isinstance(self.features,(list,tuple)) or not self.features:
            raise ValueError('features require nonempty rows')
        rows = tuple(attention_buffer('features',row) for row in self.features)
        if any(len(row)!=len(self.feature_names) for row in rows):
            raise ValueError('feature width mismatch')
        if not isinstance(self.labels,(list,tuple)) or len(self.labels)!=len(rows) or any(type(v) is not int or not 0<=v<len(self.class_names) for v in self.labels):
            raise ValueError('invalid class labels')
        if type(self.source_sha256) is not str or len(self.source_sha256)!=64 or any(c not in '0123456789abcdef' for c in self.source_sha256):
            raise ValueError('source_sha256 must be lowercase SHA256')
        object.__setattr__(self,'features',rows)
        object.__setattr__(self,'labels',tuple(self.labels))

    # Actual observations and declared source/order determine experiment input identity.
    @property
    def identity_hash(self) -> str:
        return content_hash(self)

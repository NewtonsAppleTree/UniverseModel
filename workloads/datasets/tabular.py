"""Bounded local numeric CSV classification sources with explicit original-byte provenance."""

import csv
from dataclasses import dataclass
from hashlib import sha256
from io import StringIO
from pathlib import Path, PurePosixPath

from contracts.workload.classification import ClassificationData
from contracts.workload.linear import positive_int


# Source declarations describe attribution and limitations; they are not dataset representativeness claims.
@dataclass(frozen=True, slots=True, kw_only=True)
class TabularSource:
    dataset_id: str  # Dataset/revision label.
    relative_path: str  # Normalized relative POSIX CSV path within caller data root.
    sha256: str  # SHA256 of original CSV bytes, including original line endings.
    source_url: str  # Original source URL/DOI; loading remains offline.
    attribution: str  # Creator/donor/citation statement.
    usage_terms: str  # Verified terms/source or explicitly unknown usage status.
    limitations: str  # Source defects, scope and representativeness restrictions.
    feature_names: tuple[str, ...]  # Ordered numeric CSV features; names declare measurement units.
    class_names: tuple[str, ...]  # Exact accepted final-column labels, defining class index order.
    has_header: bool = False  # If true, one header row must exactly match feature names plus 'label'.

    # Validate portable source and format declarations without opening files or importing external packages.
    def __post_init__(self) -> None:
        for name in ('dataset_id','relative_path','source_url','attribution','usage_terms','limitations'):
            if type(getattr(self,name)) is not str or not getattr(self,name).strip():
                raise ValueError(f'{name} requires nonempty source text')
        path = PurePosixPath(self.relative_path)
        if path.is_absolute() or '\\' in self.relative_path or ':' in self.relative_path or any(p in ('','.','..') for p in self.relative_path.split('/')):
            raise ValueError('source path must be a normalized relative POSIX path')
        if type(self.sha256) is not str or len(self.sha256)!=64 or any(c not in '0123456789abcdef' for c in self.sha256):
            raise ValueError('source SHA256 must be lowercase hexadecimal')
        for name in ('feature_names','class_names'):
            values = getattr(self,name)
            if not isinstance(values,(list,tuple)) or not values or any(type(v) is not str or not v.strip() for v in values) or len(set(values))!=len(values):
                raise ValueError('source feature/class names must be unique and nonempty')
            object.__setattr__(self,name,tuple(values))
        if type(self.has_header) is not bool or len(self.class_names)<2:
            raise ValueError('invalid CSV header/class declaration')


# Verify containment and bounded raw bytes before parsing numeric rows; no missing-value imputation is inferred.
def load_classification(source: TabularSource, root: str | Path, *, max_file_bytes: int = 1_000_000,
                        max_samples: int = 100_000) -> ClassificationData:
    if not isinstance(source,TabularSource):
        raise TypeError('source must be TabularSource')
    positive_int('max_file_bytes',max_file_bytes)
    positive_int('max_samples',max_samples)
    base = Path(root).resolve()
    path = (base/source.relative_path).resolve()
    if not path.is_relative_to(base):
        raise ValueError('classification source outside data root')
    with path.open('rb') as handle:
        raw = handle.read(max_file_bytes+1)
    if len(raw)>max_file_bytes or sha256(raw).hexdigest()!=source.sha256:
        raise ValueError('classification source size/SHA256 mismatch')
    reader = csv.reader(StringIO(raw.decode('utf-8')),strict=True)
    rows,labels = [],[]
    try:
        if source.has_header and next(reader,None)!=[*source.feature_names,'label']:
            raise ValueError('classification CSV header mismatch')
        for row in reader:
            if not row:
                continue
            if len(row)!=len(source.feature_names)+1 or row[-1] not in source.class_names:
                raise ValueError('classification CSV width/label mismatch')
            if len(rows)>=max_samples:
                raise ValueError('classification dataset exceeds max_samples')
            rows.append(tuple(float(v) for v in row[:-1]))
            labels.append(source.class_names.index(row[-1]))
    except csv.Error as exc:
        raise ValueError('malformed classification CSV') from exc
    return ClassificationData(features=tuple(rows),labels=tuple(labels),feature_names=source.feature_names,
                              class_names=source.class_names,source_sha256=source.sha256)

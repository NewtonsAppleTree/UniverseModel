"""Train-only standardized RBF attention classifier; finite held-out splits and explicit support state."""

from dataclasses import dataclass
from hashlib import sha256
from math import sqrt

from contracts.versions.json_codec import content_hash
from contracts.workload.attention import AttentionInputs, AttentionSpec, attention_buffer
from contracts.workload.classification import ClassificationData
from contracts.workload.linear import positive_int
from workloads.reference.attention import reference_attention
from workloads.reference.classification import classification_metrics


# A split owns disjoint exhaustive source row indices, without altering the original observations.
@dataclass(frozen=True, slots=True, kw_only=True)
class RetrievalSplit:
    data_identity: str  # Full ClassificationData identity.
    seed: int  # uint64 seed for split-sha256/v1 ordering.
    train: tuple[int, ...]  # Support/normalization training row indices.
    validation: tuple[int, ...]  # Hyperparameter-selection row indices.
    test: tuple[int, ...]  # Held-out reporting row indices; never used in fitting/selection.

    # Freeze partitions and reject repeated, negative or noninteger indices before dataset-bound validation.
    def __post_init__(self) -> None:
        if type(self.data_identity) is not str or len(self.data_identity)!=64 or any(c not in '0123456789abcdef' for c in self.data_identity):
            raise ValueError('data_identity must be lowercase SHA256')
        if type(self.seed) is not int or not 0<=self.seed<1<<64:
            raise ValueError('split seed must be uint64')
        all_indices = []
        for name in ('train','validation','test'):
            values = getattr(self,name)
            if not isinstance(values,(tuple,list)) or not values or any(type(v) is not int or v<0 for v in values):
                raise ValueError('split requires nonempty nonnegative integer partitions')
            object.__setattr__(self,name,tuple(values))
            all_indices.extend(values)
        if len(set(all_indices))!=len(all_indices):
            raise ValueError('split partitions overlap')


# Standardized support vectors and labels form a fitted nonparametric model; all fitted statistics use training rows only.
@dataclass(frozen=True, slots=True, kw_only=True)
class RetrievalState:
    data_identity: str  # Exact source observations used to fit this state.
    split: RetrievalSplit  # Explicit training/validation/test partition and generation seed.
    means: tuple[float, ...]  # Training-only per-feature mean [source feature unit].
    scales: tuple[float, ...]  # Training population standard deviations [source feature unit]; zero variance uses 1.
    support: tuple[tuple[float, ...], ...]  # Training vectors after fixed standardization [1].
    labels: tuple[int, ...]  # Training support labels [class index].
    classes: int  # Number of classes, defining one-hot V width [class].

    # Freeze state and check shape/domain so an external caller can supply an independently fitted model.
    def __post_init__(self) -> None:
        if not isinstance(self.split,RetrievalSplit) or self.split.data_identity!=self.data_identity:
            raise ValueError('retrieval state/split identity mismatch')
        means,scales = attention_buffer('means',self.means),attention_buffer('scales',self.scales)
        if not means or len(means)!=len(scales) or any(v<=0 for v in scales):
            raise ValueError('invalid standardization dimensions/scales')
        if not isinstance(self.support,(list,tuple)):
            raise TypeError('support must be list/tuple')
        vectors = tuple(attention_buffer('support',v) for v in self.support)
        positive_int('classes',self.classes)
        if self.classes<2 or len(vectors)!=len(self.split.train) or any(len(v)!=len(means) for v in vectors):
            raise ValueError('retrieval support shape mismatch')
        if not isinstance(self.labels,(list,tuple)) or len(self.labels)!=len(vectors) or any(type(v) is not int or not 0<=v<self.classes for v in self.labels):
            raise ValueError('invalid support labels')
        for name,value in (('means',means),('scales',scales),('support',vectors),('labels',tuple(self.labels))):
            object.__setattr__(self,name,value)

    # Source, split, normalization and support contents all participate in model identity.
    @property
    def identity_hash(self) -> str:
        return content_hash(self)


# Class-stratified hash ordering is stable across Python versions; remaining examples become the test partition.
def stratified_split(data: ClassificationData, *, seed: int, train_per_class: int, validation_per_class: int) -> RetrievalSplit:
    if not isinstance(data,ClassificationData):
        raise TypeError('data must be ClassificationData')
    if type(seed) is not int or not 0<=seed<1<<64:
        raise ValueError('seed must be uint64')
    positive_int('train_per_class',train_per_class)
    positive_int('validation_per_class',validation_per_class)
    train,validation,test = [],[],[]
    for label in range(len(data.class_names)):
        indices = [i for i,y in enumerate(data.labels) if y==label]
        indices.sort(key=lambda i: (sha256(f'split-sha256/v1:{seed}:{label}:{i}'.encode('ascii')).digest(),i))
        boundary = train_per_class+validation_per_class
        if len(indices)<=boundary:
            raise ValueError('each class needs nonempty train/validation/test examples')
        train.extend(indices[:train_per_class])
        validation.extend(indices[train_per_class:boundary])
        test.extend(indices[boundary:])
    return RetrievalSplit(data_identity=data.identity_hash,seed=seed,train=tuple(train),validation=tuple(validation),test=tuple(test))


# Validate complete partition ownership before computing statistics solely from the declared training subset.
def fit_retrieval(data: ClassificationData, split: RetrievalSplit) -> RetrievalState:
    if not isinstance(data,ClassificationData) or not isinstance(split,RetrievalSplit):
        raise TypeError('expected classification data and retrieval split')
    if split.data_identity!=data.identity_hash or set((*split.train,*split.validation,*split.test))!=set(range(len(data.features))):
        raise ValueError('split does not match complete source dataset')
    rows = [data.features[i] for i in split.train]
    means = tuple(sum(row[j] for row in rows)/len(rows) for j in range(len(data.feature_names)))
    scales = tuple(sqrt(sum((row[j]-mean)**2 for row in rows)/len(rows)) or 1.0 for j,mean in enumerate(means))
    support = tuple(tuple((v-mean)/scale for v,mean,scale in zip(row,means,scales)) for row in rows)
    return RetrievalState(data_identity=data.identity_hash,split=split,means=means,scales=scales,
                          support=support,labels=tuple(data.labels[i] for i in split.train),classes=len(data.class_names))


# Normalize query measurements with training statistics; optional decimal rounding affects only stored support keys.
def retrieval_vectors(state: RetrievalState, queries: tuple[tuple[float, ...], ...], key_decimals: int | None = None) -> tuple:
    if not isinstance(state,RetrievalState):
        raise TypeError('state must be RetrievalState')
    if key_decimals is not None and (type(key_decimals) is not int or not -2<=key_decimals<=12):
        raise ValueError('key_decimals must be None or integer in [-2,12]')
    if not isinstance(queries,(tuple,list)) or not queries:
        raise ValueError('queries must be nonempty rows')
    normalized = []
    for row in queries:
        values = attention_buffer('query',row)
        if len(values)!=len(state.means):
            raise ValueError('query feature width mismatch')
        normalized.append(attention_buffer('normalized query',tuple((v-m)/s for v,m,s in zip(values,state.means,state.scales))))
    keys = state.support if key_decimals is None else tuple(tuple(round(v,key_decimals) for v in row) for row in state.support)
    return tuple(normalized),keys


# Q=[2x,-||x||²,1], K=[z,1,-||z||²] gives QK=-||x-z||²; V is the support label's one-hot vector.
def retrieval_attention(state: RetrievalState, queries: tuple[tuple[float, ...], ...], *, scale: float,
                        key_decimals: int | None = None) -> tuple[AttentionSpec, AttentionInputs]:
    q,k = retrieval_vectors(state,queries,key_decimals)
    qbuf = tuple(v for row in q for v in (*[2*x for x in row],-sum(x*x for x in row),1.0))
    kbuf = tuple(v for row in k for v in (*row,1.0,-sum(x*x for x in row)))
    vbuf = tuple(float(label==j) for label in state.labels for j in range(state.classes))
    spec = AttentionSpec(batch_size=1,query_heads=1,kv_heads=1,query_length=len(q),kv_length=len(k),
                         key_dim=len(state.means)+2,value_dim=state.classes,scale=scale)
    return spec,AttentionInputs(q=qbuf,k=kbuf,v=vbuf)


# Select the first maximum-accuracy scale using validation rows only; the full ordered score table remains evidence.
def select_retrieval_scale(state: RetrievalState, data: ClassificationData, scales: tuple[float, ...], *,
                           max_macs: int = 1_000_000, max_score_pairs: int = 100_000) -> tuple:
    if state.data_identity!=data.identity_hash or not isinstance(scales,(tuple,list)) or not scales:
        raise ValueError('scale selection requires matching data and explicit scale candidates')
    queries = tuple(data.features[i] for i in state.split.validation)
    labels = tuple(data.labels[i] for i in state.split.validation)
    scores = []
    for scale in scales:
        spec,inputs = retrieval_attention(state,queries,scale=scale)
        output = reference_attention(spec,inputs,max_macs=max_macs,max_score_pairs=max_score_pairs).output
        scores.append((float(scale),classification_metrics(output,labels,state.classes)))
    selected = max(range(len(scores)),key=lambda i:scores[i][1].accuracy)
    return scores[selected][0],tuple(scores)

"""Optional external NumPy arithmetic; public workload contracts remain standard-library-only."""

import platform
import sys

from contracts.workload.attention import AttentionInputs, AttentionSpec, validate_attention


# Capture the actual library/environment without treating BLAS host time as target hardware performance.
def numpy_environment() -> dict:
    import numpy as np
    return {'backend':'numpy-attention/v1','numpy_version':np.__version__,'python':sys.version,
            'platform':platform.platform(),'dtype':'float64','scope':'independent functional arithmetic only'}


# Batched NumPy matmul/softmax uses explicit GQA expansion and absolute causal positions.
def numpy_attention(spec: AttentionSpec, inputs: AttentionInputs) -> tuple[float, ...]:
    import numpy as np
    validate_attention(spec,inputs)
    b,h,hk,q,k,d,v = spec.batch_size,spec.query_heads,spec.kv_heads,spec.query_length,spec.kv_length,spec.key_dim,spec.value_dim
    with np.errstate(over='raise',invalid='raise',divide='raise',under='ignore'):
        queries = np.asarray(inputs.q,dtype=np.float64).reshape(b,h,q,d)
        keys = np.repeat(np.asarray(inputs.k,dtype=np.float64).reshape(b,hk,k,d),h//hk,axis=1)
        values = np.repeat(np.asarray(inputs.v,dtype=np.float64).reshape(b,hk,k,v),h//hk,axis=1)
        scores = np.matmul(queries,keys.swapaxes(-1,-2))*spec.scale
        if spec.causal:
            scores = np.where(np.arange(k)[None,:]<=spec.query_start+np.arange(q)[:,None],scores,-np.inf)
        weights = np.exp(scores-np.max(scores,axis=-1,keepdims=True))
        weights /= np.sum(weights,axis=-1,keepdims=True)
        output = np.matmul(weights,values)
    if not np.isfinite(output).all():
        raise ValueError('nonfinite NumPy Attention result')
    return tuple(output.reshape(-1).tolist())


# Independent RBF distance expression bypasses Q/K polynomial construction and the compiler's interpreter.
def numpy_rbf(queries: tuple, keys: tuple, labels: tuple[int, ...], classes: int, scale: float) -> tuple[float, ...]:
    import numpy as np
    with np.errstate(over='raise',invalid='raise',divide='raise',under='ignore'):
        q,k = np.asarray(queries,dtype=np.float64),np.asarray(keys,dtype=np.float64)
        logits = -scale*np.sum((q[:,None,:]-k[None,:,:])**2,axis=-1)
        weights = np.exp(logits-logits.max(axis=-1,keepdims=True))
        weights /= weights.sum(axis=-1,keepdims=True)
        output = weights @ np.eye(classes,dtype=np.float64)[list(labels)]
    if not np.isfinite(output).all():
        raise ValueError('nonfinite NumPy RBF result')
    return tuple(output.reshape(-1).tolist())

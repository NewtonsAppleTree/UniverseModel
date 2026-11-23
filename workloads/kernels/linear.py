"""Independent dense linear workload construction and logical work accounting."""

from dataclasses import dataclass
from hashlib import sha256

from contracts.workload.linear import LinearInputs, LinearSpec, positive_int


# Logical unique tensor storage is independent of mapping, cache behavior and physical transactions.
@dataclass(frozen=True, slots=True, kw_only=True)
class LinearWork:
    macs: int  # Dense logical work M*N*K [MAC].
    conventional_operations: int  # 2*M*N*K [operation], explicit 2-operation-per-MAC convention.
    a_bytes: int  # Unique logical A storage M*K*operand_bytes [B].
    b_bytes: int  # Unique logical B storage K*N*operand_bytes [B].
    output_bytes: int  # Unique logical C storage M*N*result_bytes [B]; excludes partial traffic.


# Return logical counts only; actual movement and scratch allocation belong to the selected plan.
def describe_work(spec: LinearSpec) -> LinearWork:
    return LinearWork(macs=spec.m * spec.n * spec.k, conventional_operations=2 * spec.m * spec.n * spec.k,
                      a_bytes=spec.m * spec.k * spec.operand_bytes,
                      b_bytes=spec.k * spec.n * spec.operand_bytes,
                      output_bytes=spec.m * spec.n * spec.result_bytes)


# MatVec A[rows,columns] @ x[columns] uses N=1 and the same explicit accumulator semantics.
def matvec_spec(rows: int, columns: int, *, dtype: str = "int8") -> LinearSpec:
    return LinearSpec(m=rows, n=1, k=columns, dtype=dtype)


# SHA256-index-v1 deterministically produces bounded codes [-8,8], or codes/16 for binary64.
def generate_inputs(spec: LinearSpec, seed: int, *, max_elements: int = 1_000_000) -> LinearInputs:
    if type(seed) is not int or not 0 <= seed < 1 << 64:
        raise ValueError("seed must be an unsigned 64-bit int")
    positive_int("max_elements", max_elements)
    if spec.m * spec.k + spec.k * spec.n > max_elements:
        raise ValueError("input materialization exceeds max_elements")
    buffers = []
    for label, size in (("a", spec.m * spec.k), ("b", spec.k * spec.n)):
        values = []
        for index in range(size):
            code = sha256(f"linear-input/v1:{seed}:{label}:{index}".encode("ascii")).digest()[0] % 17 - 8
            values.append(code if spec.dtype == "int8" else code / 16.0)
        buffers.append(tuple(values))
    return LinearInputs(a=buffers[0], b=buffers[1])

"""Functional execution of explicit tile plans; no target time or host-performance claims."""

from math import isfinite

from compiler.src.memplan.linear import plan_memory
from contracts.plan.linear import LinearPlan
from contracts.workload.linear import LinearInputs, LinearSpec, positive_int, validate_inputs


# Execute local C residency/spill semantics with K-ordered scalar multiply/add, independently of the reference.
def execute_plan(spec: LinearSpec, inputs: LinearInputs, plan: LinearPlan, capacity_bytes: int, *,
                 max_macs: int = 1_000_000) -> tuple[int | float, ...]:
    validate_inputs(spec, inputs)
    plan_memory(spec, plan, capacity_bytes)
    positive_int("max_macs", max_macs)
    if spec.m * spec.n * spec.k > max_macs:
        raise ValueError("functional execution exceeds max_macs")
    zero = 0 if spec.dtype == "int8" else 0.0
    output = [zero] * (spec.m * spec.n)
    local_c = []
    for step in plan.steps:
        if step.k0 == 0:
            local_c = [zero] * (step.m * step.n)
        elif plan.strategy == "reload_partials":
            local_c = [output[(step.m0 + i) * spec.n + step.n0 + j]
                       for i in range(step.m) for j in range(step.n)]
        local_a = [inputs.a[(step.m0 + i) * spec.k + step.k0 + p]
                   for i in range(step.m) for p in range(step.k)]
        local_b = [inputs.b[(step.k0 + p) * spec.n + step.n0 + j]
                   for p in range(step.k) for j in range(step.n)]
        for p in range(step.k):
            for i in range(step.m):
                for j in range(step.n):
                    index = i * step.n + j
                    product = local_a[i * step.k + p] * local_b[p * step.n + j]
                    local_c[index] = local_c[index] + product
                    if spec.dtype == "float64" and not isfinite(local_c[index]):
                        raise ValueError("nonfinite binary64 partial sum")
        if step.k0 + step.k == spec.k or plan.strategy == "reload_partials":
            for i in range(step.m):
                for j in range(step.n):
                    output[(step.m0 + i) * spec.n + step.n0 + j] = local_c[i * step.n + j]
            local_c = []
    return tuple(output)

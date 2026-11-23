"""Explicit dense tile plans and independent coverage/order legality checks."""

from contracts.plan.linear import LinearPlan, LinearTile, TileShape
from contracts.workload.linear import LinearSpec, positive_int


# Enumerate bounded rectangular updates with real tails; the two policies differ in C residency.
def build_plan(spec: LinearSpec, tile: TileShape, strategy: str, *, max_steps: int = 100_000) -> LinearPlan:
    positive_int("max_steps", max_steps)
    if not isinstance(tile, TileShape):
        raise TypeError("tile must be TileShape")
    if strategy not in ("output_stationary", "reload_partials"):
        raise ValueError("unsupported mapping strategy")
    count = ((spec.m + tile.m - 1) // tile.m * ((spec.n + tile.n - 1) // tile.n)
             * ((spec.k + tile.k - 1) // tile.k))
    if count > max_steps:
        raise ValueError("plan materialization exceeds max_steps")
    rows, columns, reductions = range(0, spec.m, tile.m), range(0, spec.n, tile.n), range(0, spec.k, tile.k)
    if strategy == "output_stationary":
        coordinates = ((i, j, p) for i in rows for j in columns for p in reductions)
    else:
        coordinates = ((i, j, p) for p in reductions for i in rows for j in columns)
    steps = tuple(LinearTile(m0=i, n0=j, k0=p, m=min(tile.m, spec.m - i),
                             n=min(tile.n, spec.n - j), k=min(tile.k, spec.k - p)) for i, j, p in coordinates)
    plan = LinearPlan(workload_hash=spec.identity_hash, tile_shape=tile, strategy=strategy, steps=steps)
    validate_plan(spec, plan)
    return plan


# Check each ROI, per-output contiguous K coverage and C lifetime without rebuilding the producer's sequence.
def validate_plan(spec: LinearSpec, plan: LinearPlan) -> None:
    if not isinstance(plan, LinearPlan) or plan.workload_hash != spec.identity_hash:
        raise ValueError("plan workload identity mismatch")
    progress = {}
    previous = None
    macs = 0
    grid = plan.tile_shape
    for step in plan.steps:
        for start, extent, limit, block in ((step.m0, step.m, spec.m, grid.m),
                                             (step.n0, step.n, spec.n, grid.n),
                                             (step.k0, step.k, spec.k, grid.k)):
            if start >= limit or start % block or extent != min(block, limit - start):
                raise ValueError("tile ROI is outside or inconsistent with the declared grid")
        output = (step.m0, step.n0)
        if step.k0 != progress.get(output, 0):
            raise ValueError("missing, repeated or out-of-order reduction interval")
        if plan.strategy == "output_stationary" and previous is not None and output != previous:
            if progress[previous] != spec.k:
                raise ValueError("output-stationary C released before reduction completion")
        progress[output] = step.k0 + step.k
        previous = output
        macs += step.m * step.n * step.k
    output_tiles = ((spec.m + grid.m - 1) // grid.m) * ((spec.n + grid.n - 1) // grid.n)
    if len(progress) != output_tiles or any(end != spec.k for end in progress.values()):
        raise ValueError("plan does not cover all output/reduction regions")
    if macs != spec.m * spec.n * spec.k:
        raise ValueError("plan work does not match dense workload")

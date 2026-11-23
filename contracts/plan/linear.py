"""Small explicit tile-plan boundary; legality depends on the attached workload."""

from dataclasses import dataclass
from typing import Literal

from contracts.workload.linear import positive_int


# Maximum tile extents; tails are smaller and do not imply padded arithmetic.
@dataclass(frozen=True, slots=True, kw_only=True)
class TileShape:
    m: int  # Maximum output rows per tile [element]; >0.
    n: int  # Maximum output columns per tile [element]; >0.
    k: int  # Maximum reduction terms per tile [element]; >0.

    # Reject fractional/zero tile sizes before plan enumeration.
    def __post_init__(self) -> None:
        for name in ("m", "n", "k"):
            positive_int(name, getattr(self, name))


# One rectangular multiply update; output C[m0:m0+m,n0:n0+n] accumulates this K interval.
@dataclass(frozen=True, slots=True, kw_only=True)
class LinearTile:
    m0: int  # Output row start [element index]; >=0.
    n0: int  # Output column start [element index]; >=0.
    k0: int  # Reduction start [element index]; >=0.
    m: int  # Actual output rows [element]; >0.
    n: int  # Actual output columns [element]; >0.
    k: int  # Actual reduction terms [element]; >0.

    # Validate local extents; workload bounds and reduction coverage are checked by the compiler.
    def __post_init__(self) -> None:
        for name in ("m0", "n0", "k0"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative int")
        for name in ("m", "n", "k"):
            positive_int(name, getattr(self, name))


# Versioned ordered plan: output-stationary keeps C locally; reload-partials spills between K slices.
@dataclass(frozen=True, slots=True, kw_only=True)
class LinearPlan:
    workload_hash: str  # Content hash of LinearSpec; rejects plans for a different shape/format.
    tile_shape: TileShape  # Maximum extents defining the output/reduction grid [element].
    strategy: Literal["output_stationary", "reload_partials"]  # Explicit C lifetime/traffic policy.
    steps: tuple[LinearTile, ...]  # Ordered updates; no implicit parallelism or asynchronous events.
    schema_version: Literal["linear-plan/v1"] = "linear-plan/v1"  # Plan semantics version.

    # Freeze steps and enforce supported local types; no fabricated producer/compiler identity.
    def __post_init__(self) -> None:
        if type(self.workload_hash) is not str or len(self.workload_hash) != 64:
            raise ValueError("workload_hash must be a SHA256 hex identity")
        if any(char not in "0123456789abcdef" for char in self.workload_hash):
            raise ValueError("workload_hash must be lowercase hexadecimal")
        if not isinstance(self.tile_shape, TileShape):
            raise TypeError("tile_shape must be TileShape")
        if self.strategy not in ("output_stationary", "reload_partials") or self.schema_version != "linear-plan/v1":
            raise ValueError("unsupported linear plan strategy/schema")
        if not isinstance(self.steps, (tuple, list)) or not self.steps:
            raise ValueError("steps must be a nonempty list/tuple")
        object.__setattr__(self, "steps", tuple(self.steps))
        if any(not isinstance(step, LinearTile) for step in self.steps):
            raise TypeError("steps must contain LinearTile objects")

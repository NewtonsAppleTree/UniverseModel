"""Fixed dense training lowering with explicit transposes and independently checked tensor lifetimes."""

from dataclasses import dataclass
from typing import Literal

from compiler.src.memplan.linear import LinearMemory, LinearTraffic, count_traffic, plan_memory
from compiler.src.tiling.linear import build_plan
from contracts.plan.linear import LinearPlan, TileShape
from contracts.workload.linear import LinearSpec, positive_int
from contracts.workload.training import TrainingSpec


# Named dense backing-store allocation; scratch is a separate resource and host snapshots are excluded.
@dataclass(frozen=True, slots=True, kw_only=True)
class TrainingTensor:
    name: str  # Unique data/version identity in one step, not a physical memory address.
    rows: int  # Row-major matrix rows [element]; scalars are 1x1.
    columns: int  # Row-major matrix columns [element].
    initial: bool = False  # Available at step entry; x/target and old parameters.
    retained: bool = False  # Must remain observable through the step boundary.

    # Require named positive dense allocations.
    def __post_init__(self) -> None:
        if type(self.name) is not str or not self.name:
            raise ValueError("tensor name must be nonempty")
        positive_int("rows", self.rows)
        positive_int("columns", self.columns)
        if type(self.initial) is not bool or type(self.retained) is not bool:
            raise TypeError("tensor flags must be bool")

    # All training tensors store binary64, including scalar loss and gradients.
    @property
    def size_bytes(self) -> int:
        return 8 * self.rows * self.columns


# One serial semantic operation; GEMM subplans include real tails and the existing row-request accounting.
@dataclass(frozen=True, slots=True, kw_only=True)
class TrainingOperation:
    kind: Literal["gemm", "transpose", "relu", "relu_backward", "mse", "sgd"]  # Fixed operation semantics.
    reads: tuple[str, ...]  # Backing tensors read during this operation; must already be defined.
    writes: tuple[str, ...]  # Fresh tensors produced; updates never overwrite old weights.
    arithmetic_operations: int = 0  # Auxiliary scalar add/subtract/multiply/divide count [operation].
    comparisons: int = 0  # ReLU predicates [comparison].
    selections: int = 0  # ReLU masked choices [selection], separate from arithmetic.
    transpose_elements: int = 0  # Elements explicitly rearranged [element].
    gemm: LinearSpec | None = None  # Dense contraction semantics for GEMM only.
    mapping: LinearPlan | None = None  # Ordered GEMM tile updates; no target-time events.
    scratch: LinearMemory | None = None  # Reserved GEMM scratch [B]; auxiliary register demand is unmodeled.
    traffic: LinearTraffic | None = None  # GEMM backing-to-scratch row requests; no duplicated full-tensor traffic.


# Inclusive birth/last-use interval; inputs and freshly allocated outputs coexist within one operation.
@dataclass(frozen=True, slots=True, kw_only=True)
class TensorLifetime:
    name: str  # Allocation identity tied to TrainingTensor.
    size_bytes: int  # Packed backing-store allocation [B].
    birth: int  # -1 for inputs, otherwise producing operation index.
    last_use: int  # Last consuming operation, or operation_count for retained results.


# Each point is a serial operation boundary occupancy, not a cycle or event timestamp.
@dataclass(frozen=True, slots=True, kw_only=True)
class TrainingMemoryPoint:
    operation_index: int  # -1 initial, 0..N-1 operation, N final observation.
    live_names: tuple[str, ...]  # Simultaneously live named backing allocations.
    live_bytes: int  # Sum of these allocations [B]; scratch and host objects excluded.


# Static backing-memory feasibility is exact for this materializing schedule, not a GPU allocator prediction.
@dataclass(frozen=True, slots=True, kw_only=True)
class TrainingMemory:
    lifetimes: tuple[TensorLifetime, ...]  # One disjoint allocation lifetime per declared tensor.
    points: tuple[TrainingMemoryPoint, ...]  # Occupancy through all serial operations.
    peak_bytes: int  # max(points.live_bytes) [B].
    capacity_bytes: int  # Declared backing-store capacity [B]; independent from GEMM scratch.


# A built schedule contains only the requested training recipe and its static feasibility evidence.
@dataclass(frozen=True, slots=True, kw_only=True)
class TrainingPlan:
    tensors: tuple[TrainingTensor, ...]  # Shape, ownership and observation boundaries.
    operations: tuple[TrainingOperation, ...]  # Forward, loss, reverse differentiation, then all SGD updates.
    memory: TrainingMemory  # Backing-store lifetime check; does not model auxiliary compute registers.


# Check single production, definition-before-use and retained outputs independently of the schedule builder.
def analyze_training_memory(tensors: tuple[TrainingTensor, ...], operations: tuple[TrainingOperation, ...],
                            capacity_bytes: int) -> TrainingMemory:
    positive_int("capacity_bytes", capacity_bytes)
    if not tensors or len({tensor.name for tensor in tensors}) != len(tensors):
        raise ValueError("tensor identities must be nonempty and unique")
    declared = {tensor.name: tensor for tensor in tensors}
    births = {tensor.name: -1 for tensor in tensors if tensor.initial}
    last = dict(births)
    for index, operation in enumerate(operations):
        for name in operation.reads:
            if name not in births:
                raise ValueError(f"tensor {name} used before production")
            last[name] = index
        for name in operation.writes:
            if name not in declared or name in births:
                raise ValueError(f"tensor {name} has missing declaration or duplicate production")
            births[name] = last[name] = index
    if set(births) != set(declared):
        raise ValueError("declared tensor is never produced")
    lifetimes = tuple(TensorLifetime(name=t.name, size_bytes=t.size_bytes, birth=births[t.name],
                                    last_use=len(operations) if t.retained else last[t.name]) for t in tensors)
    points = tuple(TrainingMemoryPoint(operation_index=index,
                                      live_names=tuple(t.name for t in lifetimes if t.birth <= index <= t.last_use),
                                      live_bytes=sum(t.size_bytes for t in lifetimes if t.birth <= index <= t.last_use))
                   for index in range(-1, len(operations) + 1))
    peak = max(point.live_bytes for point in points)
    if peak > capacity_bytes:
        raise ValueError(f"backing capacity exceeded: need {peak} bytes, have {capacity_bytes}")
    return TrainingMemory(lifetimes=lifetimes, points=points, peak_bytes=peak, capacity_bytes=capacity_bytes)


# Lower a bounded chain; transposes are real allocations and old weights remain until backward finishes.
def build_training_plan(spec: TrainingSpec, tile: TileShape, strategy: str, *, scratch_capacity_bytes: int,
                        backing_capacity_bytes: int, max_macs: int = 1_000_000) -> TrainingPlan:
    positive_int("max_macs", max_macs)
    if spec.gemm_macs > max_macs:
        raise ValueError("training plan exceeds max_macs")
    tensors, operations = {}, []
    layers, batch = len(spec.widths) - 1, spec.batch_size

    # Define a new allocation; production order and actual uses are verified after lowering.
    def tensor(name: str, rows: int, columns: int, *, initial: bool = False, retained: bool = False) -> str:
        if name in tensors:
            raise ValueError("duplicate lowering tensor")
        tensors[name] = TrainingTensor(name=name, rows=rows, columns=columns, initial=initial, retained=retained)
        return name

    # Attach the existing three-buffer and row-request models to each actual dense contraction.
    def gemm(a: str, b: str, output: str) -> None:
        left, right, destination = tensors[a], tensors[b], tensors[output]
        if left.columns != right.rows or (destination.rows, destination.columns) != (left.rows, right.columns):
            raise ValueError("lowered GEMM shape mismatch")
        work = LinearSpec(m=left.rows, n=right.columns, k=left.columns, dtype="float64")
        mapping = build_plan(work, tile, strategy)
        scratch = plan_memory(work, mapping, scratch_capacity_bytes)
        traffic = count_traffic(work, mapping)
        operations.append(TrainingOperation(kind="gemm", reads=(a, b), writes=(output,), gemm=work,
                                            mapping=mapping, scratch=scratch, traffic=traffic))

    tensor("a0", batch, spec.widths[0], initial=True)
    tensor("target", batch, spec.widths[-1], initial=True)
    for i in range(layers):
        tensor(f"w{i}", spec.widths[i], spec.widths[i + 1], initial=True)
    for i in range(layers):
        activated = i < layers - 1 and spec.hidden_activation == "relu"
        destination = tensor(f"z{i + 1}" if activated else f"a{i + 1}", batch, spec.widths[i + 1], retained=i == layers - 1)
        gemm(f"a{i}", f"w{i}", destination)
        if activated:
            output = tensor(f"a{i + 1}", batch, spec.widths[i + 1])
            elements = batch * spec.widths[i + 1]
            operations.append(TrainingOperation(kind="relu", reads=(destination,), writes=(output,), comparisons=elements, selections=elements))
    tensor("loss", 1, 1, retained=True)
    tensor(f"g{layers}", batch, spec.widths[-1])
    operations.append(TrainingOperation(kind="mse", reads=(f"a{layers}", "target"), writes=("loss", f"g{layers}"),
                                        arithmetic_operations=4 * batch * spec.widths[-1] + 2))
    for i in reversed(range(layers)):
        din, dout = spec.widths[i:i + 2]
        for source, output, rows, columns in ((f"a{i}", f"at{i}", din, batch), (f"w{i}", f"wt{i}", dout, din)):
            tensor(output, rows, columns)
            operations.append(TrainingOperation(kind="transpose", reads=(source,), writes=(output,), transpose_elements=rows * columns))
        dw = tensor(f"dw{i}", din, dout, retained=True)
        gemm(f"at{i}", f"g{i + 1}", dw)
        masked = i > 0 and spec.hidden_activation == "relu"
        dx = tensor(f"da{i}" if masked else f"g{i}", batch, din, retained=i == 0)
        gemm(f"g{i + 1}", f"wt{i}", dx)
        if masked:
            output = tensor(f"g{i}", batch, din)
            operations.append(TrainingOperation(kind="relu_backward", reads=(dx, f"a{i}"), writes=(output,),
                                                comparisons=batch * din, selections=batch * din))
    for i in range(layers):
        output = tensor(f"updated_w{i}", spec.widths[i], spec.widths[i + 1], retained=True)
        operations.append(TrainingOperation(kind="sgd", reads=(f"w{i}", f"dw{i}"), writes=(output,),
                                            arithmetic_operations=2 * spec.widths[i] * spec.widths[i + 1]))
    declarations, schedule = tuple(tensors.values()), tuple(operations)
    memory = analyze_training_memory(declarations, schedule, backing_capacity_bytes)
    return TrainingPlan(tensors=declarations, operations=schedule, memory=memory)

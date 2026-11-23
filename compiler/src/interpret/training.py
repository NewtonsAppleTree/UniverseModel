"""Functional dense training schedule execution; no framework or target-time engine."""

from compiler.src.interpret.linear import execute_plan
from compiler.src.sched.training import TrainingPlan, build_training_plan
from contracts.plan.linear import TileShape
from contracts.workload.linear import LinearInputs
from contracts.workload.training import TrainingGradients, TrainingInputs, TrainingResult, TrainingSpec, TrainingState, float_buffer, validate_learning_rate, validate_training


# Plain SGD uses distinct scalar multiply and subtraction, with finite output validation.
def _sgd_values(weights: tuple[float, ...], gradients: tuple[float, ...], learning_rate: float) -> tuple[float, ...]:
    return float_buffer(tuple(weight - learning_rate * gradient for weight, gradient in zip(weights, gradients)))


# Apply gradients only to their exact source state; produce a fresh version without altering any caller buffer.
def apply_sgd(spec: TrainingSpec, state: TrainingState, gradients: TrainingGradients, learning_rate: float) -> TrainingState:
    validate_learning_rate(learning_rate)
    expected = tuple(a * b for a, b in zip(spec.widths, spec.widths[1:]))
    if tuple(map(len, state.weights)) != expected or tuple(map(len, gradients.weights)) != expected or len(gradients.x) != spec.batch_size * spec.widths[0]:
        raise ValueError("SGD state/gradient shape mismatch")
    if gradients.state_version != state.version or gradients.state_identity != state.identity_hash:
        raise ValueError("stale or foreign-state gradients cannot update this state")
    return TrainingState(version=state.version + 1,
                         weights=tuple(_sgd_values(w, g, learning_rate) for w, g in zip(state.weights, gradients.weights)))


# Execute the fixed recipe and release backing leases at last use; retained host audit values do not model SRAM.
def execute_training(spec: TrainingSpec, state: TrainingState, inputs: TrainingInputs, learning_rate: float,
                     tile: TileShape, strategy: str, *, scratch_capacity_bytes: int, backing_capacity_bytes: int,
                     max_macs: int = 1_000_000) -> tuple[TrainingResult, TrainingPlan]:
    validate_training(spec, state, inputs)
    validate_learning_rate(learning_rate)
    plan = build_training_plan(spec, tile, strategy, scratch_capacity_bytes=scratch_capacity_bytes,
                               backing_capacity_bytes=backing_capacity_bytes, max_macs=max_macs)
    shapes = {tensor.name: tensor for tensor in plan.tensors}
    values = {"a0": inputs.x, "target": inputs.target, **{f"w{i}": weight for i, weight in enumerate(state.weights)}}
    for index, operation in enumerate(plan.operations):
        source = [values[name] for name in operation.reads]
        if operation.kind == "gemm":
            outputs = (execute_plan(operation.gemm, LinearInputs(a=source[0], b=source[1]), operation.mapping,
                                    scratch_capacity_bytes, max_macs=max_macs),)
        elif operation.kind == "transpose":
            shape = shapes[operation.reads[0]]
            outputs = (tuple(source[0][r * shape.columns + c] for c in range(shape.columns) for r in range(shape.rows)),)
        elif operation.kind == "relu":
            outputs = (tuple(value if value > 0.0 else 0.0 for value in source[0]),)
        elif operation.kind == "relu_backward":
            outputs = (tuple(gradient if activation > 0.0 else 0.0 for gradient, activation in zip(*source)),)
        elif operation.kind == "mse":
            residual = tuple(a - b for a, b in zip(*source))
            squared_sum = 0.0
            for value in residual:
                squared_sum = squared_sum + value * value
            loss = squared_sum / len(residual)
            coefficient = 2.0 / len(residual)
            outputs = ((loss,), tuple(coefficient * value for value in residual))
        elif operation.kind == "sgd":
            outputs = (_sgd_values(source[0], source[1], learning_rate),)
        else:
            raise ValueError("unsupported training operation")
        for name, output in zip(operation.writes, outputs):
            values[name] = float_buffer(output)
        for lifetime in plan.memory.lifetimes:
            if lifetime.last_use == index:
                del values[lifetime.name]
    layers = len(state.weights)
    gradients = TrainingGradients(state_identity=state.identity_hash, state_version=state.version,
                                  weights=tuple(values[f"dw{i}"] for i in range(layers)), x=values["g0"])
    result = TrainingResult(loss=values["loss"][0], prediction=values[f"a{layers}"], gradients=gradients,
                            next_state=TrainingState(version=state.version + 1, weights=tuple(values[f"updated_w{i}"] for i in range(layers))))
    return result, plan

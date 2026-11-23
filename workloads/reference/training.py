"""Independent exact rational reverse-mode reference for a small dense training chain."""

from fractions import Fraction

from contracts.workload.linear import LinearSpec, positive_int
from contracts.workload.training import TrainingGradients, TrainingInputs, TrainingResult, TrainingSpec, TrainingState, validate_learning_rate, validate_training
from workloads.reference.linear import LinearValidation, compare_output


# Evaluate the whole mathematical chain exactly, then round observed values once; no mapped execution is reused.
def reference_training(spec: TrainingSpec, state: TrainingState, inputs: TrainingInputs, learning_rate: float, *,
                       max_macs: int = 1_000_000) -> TrainingResult:
    validate_training(spec, state, inputs)
    validate_learning_rate(learning_rate)
    positive_int("max_macs", max_macs)
    if spec.gemm_macs > max_macs:
        raise ValueError("training reference exceeds max_macs")
    b = spec.batch_size
    weights = [tuple(map(Fraction, values)) for values in state.weights]
    activations = [tuple(map(Fraction, inputs.x))]
    for layer, (din, dout) in enumerate(zip(spec.widths, spec.widths[1:])):
        values = tuple(sum((activations[-1][r * din + k] * weights[layer][k * dout + j] for k in range(din)), Fraction(0))
                       for r in range(b) for j in range(dout))
        if layer < len(weights) - 1 and spec.hidden_activation == "relu":
            values = tuple(max(Fraction(0), value) for value in values)
        activations.append(values)
    residual = tuple(value - Fraction(target) for value, target in zip(activations[-1], inputs.target))
    loss = sum((value * value for value in residual), Fraction(0)) / len(residual)
    gradient = tuple(2 * value / len(residual) for value in residual)
    weight_gradients = [()] * len(weights)
    for layer in reversed(range(len(weights))):
        din, dout = spec.widths[layer:layer + 2]
        weight_gradients[layer] = tuple(sum((activations[layer][r * din + k] * gradient[r * dout + j] for r in range(b)), Fraction(0))
                                        for k in range(din) for j in range(dout))
        dx = tuple(sum((gradient[r * dout + j] * weights[layer][k * dout + j] for j in range(dout)), Fraction(0))
                   for r in range(b) for k in range(din))
        gradient = tuple(value if activation > 0 else Fraction(0) for value, activation in zip(dx, activations[layer])) if layer and spec.hidden_activation == "relu" else dx
    updated = tuple(tuple(float(w - Fraction(learning_rate) * g) for w, g in zip(values, grads))
                    for values, grads in zip(weights, weight_gradients))
    return TrainingResult(loss=float(loss), prediction=tuple(map(float, activations[-1])),
                          gradients=TrainingGradients(state_identity=state.identity_hash, state_version=state.version,
                                                      weights=tuple(tuple(map(float, values)) for values in weight_gradients), x=tuple(map(float, gradient))),
                          next_state=TrainingState(version=state.version + 1, weights=updated))


# Compare all observations and state transitions, not just the final loss or one tensor.
def compare_training(actual: TrainingResult, reference: TrainingResult, *, atol: float = 1e-12, rtol: float = 1e-12) -> dict[str, LinearValidation]:
    if (actual.gradients.state_identity, actual.gradients.state_version, actual.next_state.version) != (reference.gradients.state_identity, reference.gradients.state_version, reference.next_state.version):
        raise ValueError("training result state provenance mismatch")
    if len(actual.gradients.weights) != len(reference.gradients.weights) or len(actual.next_state.weights) != len(reference.next_state.weights):
        raise ValueError("training result layer count mismatch")
    pairs = {"loss": ((actual.loss,), (reference.loss,)), "prediction": (actual.prediction, reference.prediction),
             "dx": (actual.gradients.x, reference.gradients.x)}
    for i, (a, r) in enumerate(zip(actual.gradients.weights, reference.gradients.weights)):
        pairs[f"dw{i}"] = (a, r)
    for i, (a, r) in enumerate(zip(actual.next_state.weights, reference.next_state.weights)):
        pairs[f"updated_w{i}"] = (a, r)
    return {name: compare_output(LinearSpec(m=1, n=len(r), k=1, dtype="float64"), a, r, atol=atol, rtol=rtol)
            for name, (a, r) in pairs.items()}

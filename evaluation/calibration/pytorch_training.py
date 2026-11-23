"""Optional CPU functional reference; importing this module does not import or require PyTorch."""

import platform
import sys

from contracts.workload.training import TrainingGradients, TrainingInputs, TrainingResult, TrainingSpec, TrainingState, validate_learning_rate, validate_training


# Record the actual external implementation/environment, with no target hardware timing claim.
def pytorch_environment() -> dict[str, object]:
    import torch
    return {"backend": "pytorch-autograd/v1", "torch_version": str(torch.__version__), "torch_git_version": torch.version.git_version,
            "python": sys.version, "platform": platform.platform(), "device": "cpu", "dtype": "float64",
            "threads": torch.get_num_threads(), "reference_scope": "functional-only"}


# Use framework Linear, ReLU, MSE autograd and SGD; no hand-written backward equations are reused.
def pytorch_training(spec: TrainingSpec, state: TrainingState, inputs: TrainingInputs, learning_rate: float) -> TrainingResult:
    import torch
    validate_training(spec, state, inputs)
    validate_learning_rate(learning_rate)
    x = torch.tensor(inputs.x, dtype=torch.float64, device="cpu").reshape(spec.batch_size, spec.widths[0]).requires_grad_()
    target = torch.tensor(inputs.target, dtype=torch.float64, device="cpu").reshape(spec.batch_size, spec.widths[-1])
    weights = [torch.tensor(values, dtype=torch.float64, device="cpu").reshape(din, dout).requires_grad_()
               for values, din, dout in zip(state.weights, spec.widths, spec.widths[1:])]
    output = x
    for layer, weight in enumerate(weights):
        output = torch.nn.functional.linear(output, weight.transpose(0, 1))
        if layer < len(weights) - 1 and spec.hidden_activation == "relu":
            output = torch.nn.functional.relu(output)
    loss = torch.nn.functional.mse_loss(output, target, reduction="mean")
    loss.backward()
    gradients = TrainingGradients(state_identity=state.identity_hash, state_version=state.version,
                                  weights=tuple(tuple(weight.grad.reshape(-1).tolist()) for weight in weights),
                                  x=tuple(x.grad.reshape(-1).tolist()))
    optimizer = torch.optim.SGD(weights, lr=learning_rate, momentum=0, weight_decay=0, foreach=False, fused=False)
    optimizer.step()
    return TrainingResult(loss=loss.item(), prediction=tuple(output.detach().reshape(-1).tolist()), gradients=gradients,
                          next_state=TrainingState(version=state.version + 1,
                                                   weights=tuple(tuple(weight.detach().reshape(-1).tolist()) for weight in weights)))

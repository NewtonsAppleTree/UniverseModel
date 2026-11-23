"""Compiler-only training arithmetic, state transitions and independent lifetime counterexamples."""

from dataclasses import replace
import unittest

from compiler.src.interpret.training import apply_sgd, execute_training
from compiler.src.sched.training import TrainingOperation, TrainingTensor, analyze_training_memory, build_training_plan
from contracts.plan.linear import TileShape
from contracts.workload.training import TrainingInputs, TrainingSpec, TrainingState


# Verify explicit training lowering without importing workload references or hardware across compiler boundaries.
class TrainingCompilerTests(unittest.TestCase):
    # Rectangular Linear hand values remain correct with split reductions and preserve caller state.
    def test_single_layer_execution(self):
        spec = TrainingSpec(batch_size=1, widths=(2, 1))
        state = TrainingState(version=0, weights=((1.0, 2.0),))
        data = TrainingInputs(x=(3.0, 4.0), target=(1.0,))
        for strategy in ("output_stationary", "reload_partials"):
            result, _ = execute_training(spec, state, data, 0.1, TileShape(m=1, n=1, k=1), strategy,
                                          scratch_capacity_bytes=24, backing_capacity_bytes=88)
            self.assertEqual((result.prediction, result.loss), ((11.0,), 100.0))
            self.assertEqual((result.gradients.weights, result.gradients.x), (((60.0, 80.0),), (20.0, 40.0)))
            self.assertEqual(result.next_state.weights, ((-5.0, -6.0),))
            self.assertEqual((state.version, state.weights), (0, ((1.0, 2.0),)))

    # ReLU backward uses the saved activation, including derivative zero for both zero and negative preactivation.
    def test_relu_mask_and_zero_boundary(self):
        spec = TrainingSpec(batch_size=1, widths=(2, 2, 1))
        state = TrainingState(version=0, weights=((1.0, 0.0, 0.0, 1.0), (2.0, 3.0)))
        result, _ = execute_training(spec, state, TrainingInputs(x=(1.0, -1.0), target=(0.0,)), 0.0,
                                      TileShape(m=1, n=1, k=1), "output_stationary", scratch_capacity_bytes=24, backing_capacity_bytes=1024)
        self.assertEqual((result.prediction, result.gradients.x), ((2.0,), (8.0, 0.0)))
        self.assertEqual(result.gradients.weights, ((8.0, 0.0, -8.0, 0.0), (4.0, 0.0)))
        zero, _ = execute_training(spec, state, TrainingInputs(x=(-1.0, 0.0), target=(1.0,)), 0.0,
                                    TileShape(m=1, n=1, k=1), "reload_partials", scratch_capacity_bytes=24, backing_capacity_bytes=1024)
        self.assertEqual(zero.gradients.x, (0.0, 0.0))
        self.assertTrue(all(value == 0.0 for weight in zero.gradients.weights for value in weight))

    # Parameter version and content hash both reject stale/foreign gradients; new steps use the updated weights.
    def test_sgd_state_provenance_and_repeated_steps(self):
        spec = TrainingSpec(batch_size=1, widths=(1, 1))
        state = TrainingState(version=0, weights=((1.0,),))
        data = TrainingInputs(x=(2.0,), target=(0.0,))
        result, _ = execute_training(spec, state, data, 0.125, TileShape(m=1, n=1, k=1), "output_stationary",
                                      scratch_capacity_bytes=24, backing_capacity_bytes=128)
        self.assertEqual(apply_sgd(spec, state, result.gradients, 0.125), result.next_state)
        for invalid in (result.next_state, replace(state, weights=((2.0,),))):
            with self.assertRaisesRegex(ValueError, "stale|foreign"):
                apply_sgd(spec, invalid, result.gradients, 0.125)
        with self.assertRaisesRegex(ValueError, "shape"):
            apply_sgd(spec, state, replace(result.gradients, weights=((1.0, 2.0),)), 0.1)
        self.assertEqual(apply_sgd(spec, state, result.gradients, 0.0).version, 1)
        second, _ = execute_training(spec, result.next_state, data, 0.125, TileShape(m=1, n=1, k=1), "output_stationary",
                                      scratch_capacity_bytes=24, backing_capacity_bytes=128)
        self.assertEqual((second.next_state.version, second.loss), (2, 0.0))

    # Inclusive lifetime accounting keeps input/output simultaneously allocated and honors retained observations.
    def test_hand_lifetime_and_capacity(self):
        tensors = (TrainingTensor(name="x", rows=1, columns=1, initial=True), TrainingTensor(name="y", rows=1, columns=1, retained=True))
        operations = (TrainingOperation(kind="relu", reads=("x",), writes=("y",)),)
        memory = analyze_training_memory(tensors, operations, 16)
        self.assertEqual([point.live_bytes for point in memory.points], [8, 16, 8])
        self.assertEqual([(t.name, t.birth, t.last_use) for t in memory.lifetimes], [("x", -1, 0), ("y", 0, 1)])
        with self.assertRaisesRegex(ValueError, "need 16 bytes, have 15"):
            analyze_training_memory(tensors, operations, 15)

    # Missing production, reads from the future and overwriting old input allocations are all invalid.
    def test_lifetime_counterexamples(self):
        tensors = (TrainingTensor(name="x", rows=1, columns=1, initial=True), TrainingTensor(name="y", rows=1, columns=1))
        invalid = ((), (TrainingOperation(kind="relu", reads=("y",), writes=("y",)),),
                   (TrainingOperation(kind="relu", reads=("x",), writes=("x",)),),
                   (TrainingOperation(kind="relu", reads=("x",), writes=("unknown",)),))
        for operations in invalid:
            with self.subTest(operations=operations), self.assertRaises(ValueError):
                analyze_training_memory(tensors, operations, 100)
        with self.assertRaises(ValueError):
            analyze_training_memory((tensors[0], tensors[0]), (), 100)

    # Backward contraction axes differ from forward; all updates follow all backward contractions and transposes.
    def test_lowering_axes_and_update_order(self):
        spec = TrainingSpec(batch_size=2, widths=(3, 4, 2))
        plan = build_training_plan(spec, TileShape(m=2, n=2, k=2), "output_stationary", scratch_capacity_bytes=96, backing_capacity_bytes=568)
        gemms = [op for op in plan.operations if op.kind == "gemm"]
        self.assertEqual([(op.gemm.m, op.gemm.n, op.gemm.k) for op in gemms], [(2, 4, 3), (2, 2, 4), (4, 2, 2), (2, 4, 2), (3, 4, 2), (2, 3, 4)])
        first_update = next(i for i, op in enumerate(plan.operations) if op.kind == "sgd")
        self.assertTrue(all(op.kind == "sgd" for op in plan.operations[first_update:]))
        self.assertEqual(sum(op.transpose_elements for op in plan.operations), 34)
        self.assertEqual(sum(op.arithmetic_operations for op in plan.operations), 58)
        self.assertEqual(sum(op.comparisons for op in plan.operations), 16)
        self.assertEqual(plan.memory.peak_bytes, 568)

    # Scratch and backing capacity are independent budgets, and the full-step work limit is enforced before lowering.
    def test_independent_capacity_and_work_limits(self):
        spec = TrainingSpec(batch_size=2, widths=(3, 4, 2))
        tile = TileShape(m=2, n=2, k=2)
        for scratch, backing, message in ((95, 4096, "scratch"), (128, 567, "backing")):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                build_training_plan(spec, tile, "output_stationary", scratch_capacity_bytes=scratch, backing_capacity_bytes=backing)
        with self.assertRaisesRegex(ValueError, "max_macs"):
            build_training_plan(spec, tile, "output_stationary", scratch_capacity_bytes=128, backing_capacity_bytes=4096, max_macs=119)

    # Nonfinite loss or update is rejected rather than silently producing an apparently successful training state.
    def test_numerical_overflow(self):
        spec = TrainingSpec(batch_size=1, widths=(1, 1))
        with self.assertRaises(ValueError):
            execute_training(spec, TrainingState(version=0, weights=((1e200,),)), TrainingInputs(x=(1.0,), target=(0.0,)),
                             0.1, TileShape(m=1, n=1, k=1), "output_stationary", scratch_capacity_bytes=24, backing_capacity_bytes=128)


if __name__ == "__main__":
    unittest.main()

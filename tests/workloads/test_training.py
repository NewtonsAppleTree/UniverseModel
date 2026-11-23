"""Independent arithmetic, numerical differentiation and immutable training contract checks."""

from dataclasses import replace
import unittest

from contracts.workload.training import TrainingInputs, TrainingSpec, TrainingState, validate_training
from workloads.graphs.training import describe_training, generate_training
from workloads.reference.training import reference_training


# Test training semantics independently of the compiler recipe and target service models.
class TrainingWorkloadTests(unittest.TestCase):
    # Mean MSE differentiates all elements; this hand example also checks weight orientation and SGD sign.
    def test_single_layer_hand_example(self):
        spec = TrainingSpec(batch_size=1, widths=(2, 1))
        state = TrainingState(version=4, weights=((1.0, 2.0),))
        data = TrainingInputs(x=(3.0, 4.0), target=(1.0,))
        result = reference_training(spec, state, data, 0.1)
        self.assertEqual((result.prediction, result.loss), ((11.0,), 100.0))
        self.assertEqual((result.gradients.weights, result.gradients.x), (((60.0, 80.0),), (20.0, 40.0)))
        self.assertEqual((result.next_state.version, result.next_state.weights), (5, ((-5.0, -6.0),)))

    # B=2 and output width=2 require division by four, not by batch or feature count alone.
    def test_mean_mse_normalization(self):
        spec = TrainingSpec(batch_size=2, widths=(1, 2))
        result = reference_training(spec, TrainingState(version=0, weights=((1.0, 2.0),)),
                                    TrainingInputs(x=(1.0, 2.0), target=(0.0, 0.0, 0.0, 0.0)), 0.0)
        self.assertEqual(result.loss, 6.25)
        self.assertEqual(result.gradients.weights, ((2.5, 5.0),))
        self.assertEqual(result.gradients.x, (2.5, 5.0))

    # A rectangular two-layer example independently fixes contractions, auxiliary work and rearrangement counts.
    def test_full_semantic_work(self):
        spec = TrainingSpec(batch_size=2, widths=(3, 4, 2))
        work = describe_training(spec)
        self.assertEqual((work.gemm_macs, work.scalar_arithmetic_operations, work.comparisons, work.selections), (120, 58, 16, 16))
        self.assertEqual((work.transpose_elements, work.parameter_bytes), (34, 160))
        identity = describe_training(replace(spec, hidden_activation="identity"))
        self.assertEqual((identity.comparisons, identity.selections), (0, 0))

    # Caller lists cannot mutate state/data; identity distinguishes logical versions and actual parameter contents.
    def test_snapshot_ownership(self):
        weight = [1.0, 2.0]
        state = TrainingState(version=0, weights=[weight])
        data = TrainingInputs(x=weight, target=[0.0])
        weight[0] = 3.0
        self.assertEqual((state.weights, data.x), (((1.0, 2.0),), (1.0, 2.0)))
        self.assertNotEqual(state.identity_hash, replace(state, version=1).identity_hash)
        self.assertNotEqual(state.identity_hash, replace(state, weights=((3.0, 2.0),)).identity_hash)

    # Strict dimensions, finite explicit float scalars and shape-specific state boundaries reject malformed inputs.
    def test_contract_rejections(self):
        for widths in ((), (1,), (1, True), (1, 0), (1, 1.0), (1,) * 18):
            with self.subTest(widths=widths), self.assertRaises((ValueError, TypeError)):
                TrainingSpec(batch_size=1, widths=widths)
        for value in (1, True, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                TrainingState(version=0, weights=((value,),))
        spec = TrainingSpec(batch_size=1, widths=(2, 1))
        state, data = generate_training(spec, 0)
        for invalid in (replace(state, weights=((1.0,),)), replace(state, weights=state.weights * 2)):
            with self.assertRaises(ValueError):
                validate_training(spec, invalid, data)
        with self.assertRaises(ValueError):
            validate_training(spec, state, TrainingInputs(x=(1.0,), target=(1.0,)))
        with self.assertRaises(ValueError):
            reference_training(spec, state, data, -0.1)

    # Stable generation uses distinct tensor labels and guards total data/parameter materialization.
    def test_generation_and_work_limits(self):
        spec = TrainingSpec(batch_size=2, widths=(3, 4, 2))
        self.assertEqual(generate_training(spec, 7), generate_training(spec, 7))
        self.assertNotEqual(generate_training(spec, 7), generate_training(spec, 8))
        for seed in (True, -1, 1 << 64):
            with self.subTest(seed=seed), self.assertRaises(ValueError):
                generate_training(spec, seed)
        with self.assertRaisesRegex(ValueError, "max_elements"):
            generate_training(spec, 7, max_elements=29)
        state, data = generate_training(spec, 7)
        with self.assertRaisesRegex(ValueError, "max_macs"):
            reference_training(spec, state, data, 0.1, max_macs=119)

    # Central differences use only perturbed forward losses, independently checking reverse equations for all weights and x.
    def test_gradients_by_finite_differences(self):
        spec = TrainingSpec(batch_size=2, widths=(2, 3, 1), hidden_activation="identity")
        state, data = generate_training(spec, 19)
        result = reference_training(spec, state, data, 0.0)
        epsilon = 1e-5
        for layer, weights in enumerate(state.weights):
            for index, value in enumerate(weights):
                states = []
                for sign in (1, -1):
                    changed = list(weights)
                    changed[index] = value + sign * epsilon
                    buffers = list(state.weights)
                    buffers[layer] = tuple(changed)
                    states.append(replace(state, weights=tuple(buffers)))
                derivative = (reference_training(spec, states[0], data, 0.0).loss - reference_training(spec, states[1], data, 0.0).loss) / (2 * epsilon)
                self.assertAlmostEqual(derivative, result.gradients.weights[layer][index], delta=1e-9)
        for index, value in enumerate(data.x):
            losses = []
            for sign in (1, -1):
                changed = list(data.x)
                changed[index] = value + sign * epsilon
                losses.append(reference_training(spec, state, replace(data, x=tuple(changed)), 0.0).loss)
            self.assertAlmostEqual((losses[0] - losses[1]) / (2 * epsilon), result.gradients.x[index], delta=1e-9)


if __name__ == "__main__":
    unittest.main()

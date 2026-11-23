"""Compiler-only legality, lifetime, storage and arithmetic checks with hand-derived expectations."""

from dataclasses import replace
import unittest

from compiler.src.interpret.linear import execute_plan
from compiler.src.memplan.linear import count_traffic, plan_memory
from compiler.src.tiling.linear import build_plan, validate_plan
from contracts.plan.linear import TileShape
from contracts.workload.linear import LinearInputs, LinearSpec


# Verify compiler semantics without importing workloads or hardware across its dependency boundary.
class LinearMappingTests(unittest.TestCase):
    # Tail tiles and oversized tiles execute a rectangular hand-computed GEMM under both policies.
    def test_rectangular_tails_and_oversized_tiles(self):
        spec = LinearSpec(m=2, n=2, k=3)
        inputs = LinearInputs(a=(1, 2, 3, 4, 5, 6), b=(7, 8, 9, 10, 11, 12))
        for strategy in ("output_stationary", "reload_partials"):
            for tile in (TileShape(m=1, n=1, k=2), TileShape(m=9, n=9, k=9)):
                with self.subTest(strategy=strategy, tile=tile):
                    plan = build_plan(spec, tile, strategy)
                    self.assertEqual(execute_plan(spec, inputs, plan, 44), (58, 64, 139, 154))
                    self.assertEqual(count_traffic(spec, plan).executed_macs, 12)

    # Three reserved arenas have nonoverlapping byte intervals and reject capacity one byte too small.
    def test_scratch_capacity_boundary(self):
        spec = LinearSpec(m=5, n=4, k=7)
        plan = build_plan(spec, TileShape(m=2, n=2, k=3), "output_stationary")
        memory = plan_memory(spec, plan, 44)
        self.assertEqual((memory.a_offset, memory.a_bytes, memory.b_offset, memory.b_bytes), (0, 6, 6, 6))
        self.assertEqual((memory.c_offset, memory.c_bytes, memory.allocation_bytes, memory.peak_live_bytes), (12, 32, 44, 44))
        with self.assertRaisesRegex(ValueError, "need 44 bytes, have 43"):
            plan_memory(spec, plan, 43)

    # Hand-derived payload totals include each output once and two extra C transfers per K boundary.
    def test_traffic_counts_and_row_requests(self):
        spec = LinearSpec(m=5, n=4, k=7)
        tile = TileShape(m=2, n=2, k=3)
        resident = count_traffic(spec, build_plan(spec, tile, "output_stationary"))
        spill = count_traffic(spec, build_plan(spec, tile, "reload_partials"))
        self.assertEqual((resident.a_read_bytes, resident.b_read_bytes, resident.output_write_bytes), (70, 84, 160))
        self.assertEqual((resident.partial_read_bytes, resident.partial_write_bytes, resident.external_bytes), (0, 0, 314))
        self.assertEqual((spill.partial_read_bytes, spill.partial_write_bytes, spill.external_bytes), (320, 320, 954))
        first = tuple((item.purpose, item.payload_bytes) for item in resident.transfers if item.step_index == 0)
        self.assertEqual(first, (("a_read", 3), ("a_read", 3), ("b_read", 2), ("b_read", 2), ("b_read", 2)))
        self.assertEqual(sum(item.payload_bytes for item in spill.transfers), 954)
        self.assertEqual((resident.executed_macs, spill.executed_macs), (140, 140))

    # Without a K split both policies have identical traffic, including tail dimensions.
    def test_no_reduction_split_has_no_spill_cost(self):
        spec = LinearSpec(m=3, n=5, k=2)
        tile = TileShape(m=2, n=3, k=8)
        stationary = count_traffic(spec, build_plan(spec, tile, "output_stationary"))
        spilled = count_traffic(spec, build_plan(spec, tile, "reload_partials"))
        self.assertEqual(stationary, spilled)

    # Independent coverage validator rejects omissions, duplicates, overlaps, misalignment and identity changes.
    def test_corrupted_plan_rejected(self):
        spec = LinearSpec(m=3, n=2, k=3)
        plan = build_plan(spec, TileShape(m=2, n=1, k=2), "reload_partials")
        invalid = (
            replace(plan, steps=plan.steps[:-1]),
            replace(plan, steps=plan.steps + (plan.steps[0],)),
            replace(plan, steps=tuple(reversed(plan.steps))),
            replace(plan, workload_hash="0" * 64),
            replace(plan, steps=(replace(plan.steps[0], m0=1),) + plan.steps[1:]),
            replace(plan, steps=(replace(plan.steps[0], m=3),) + plan.steps[1:]),
            replace(plan, steps=(replace(plan.steps[0], k0=4),) + plan.steps[1:]),
            replace(plan, steps=(replace(plan.steps[0], k=1),) + plan.steps[1:]),
        )
        for malformed in invalid:
            with self.subTest(steps=malformed.steps), self.assertRaises(ValueError):
                validate_plan(spec, malformed)

    # A single resident C buffer cannot switch output tiles before the prior reduction finishes.
    def test_premature_c_release_rejected(self):
        spec = LinearSpec(m=2, n=1, k=2)
        interleaved = build_plan(spec, TileShape(m=1, n=1, k=1), "reload_partials")
        with self.assertRaisesRegex(ValueError, "released"):
            validate_plan(spec, replace(interleaved, strategy="output_stationary"))

    # Legal complete output groups may be reordered, so validation is independent of producer enumeration.
    def test_legal_output_group_reordering(self):
        spec = LinearSpec(m=2, n=1, k=2)
        inputs = LinearInputs(a=(1, 2, 3, 4), b=(5, 6))
        plan = build_plan(spec, TileShape(m=1, n=1, k=1), "output_stationary")
        reordered = replace(plan, steps=plan.steps[2:] + plan.steps[:2])
        validate_plan(spec, reordered)
        self.assertEqual(execute_plan(spec, inputs, reordered, 10), (17, 39))

    # Native binary64 operations preserve K order, expose cancellation, and reject overflowing partial sums.
    def test_float_rounding_and_overflow(self):
        spec = LinearSpec(m=1, n=1, k=3, dtype="float64")
        inputs = LinearInputs(a=(1e16, 1.0, -1e16), b=(1.0, 1.0, 1.0))
        for strategy in ("output_stationary", "reload_partials"):
            plan = build_plan(spec, TileShape(m=1, n=1, k=1), strategy)
            self.assertEqual(execute_plan(spec, inputs, plan, 24), (0.0,))
            with self.assertRaisesRegex(ValueError, "nonfinite"):
                execute_plan(spec, LinearInputs(a=(1e308, 1e308, 0.0), b=(2.0, 1.0, 1.0)), plan, 24)

    # Work, plan and request materialization have separate host safety bounds.
    def test_materialization_limits(self):
        spec = LinearSpec(m=2, n=1, k=2)
        tile = TileShape(m=1, n=1, k=1)
        with self.assertRaisesRegex(ValueError, "max_steps"):
            build_plan(spec, tile, "output_stationary", max_steps=3)
        plan = build_plan(spec, tile, "output_stationary")
        with self.assertRaisesRegex(ValueError, "max_transfers"):
            count_traffic(spec, plan, max_transfers=1)
        with self.assertRaisesRegex(ValueError, "max_macs"):
            execute_plan(spec, LinearInputs(a=(1, 2, 3, 4), b=(1, 1)), plan, 10, max_macs=3)


if __name__ == "__main__":
    unittest.main()

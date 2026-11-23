"""CH6的阶段、驻留和格式证据；参考用枚举/手算而非重用生产公式。"""

from dataclasses import replace
from fractions import Fraction
import random
import unittest

from chipmodel.common import ClockDomain, PipelineParams
from chipmodel.compute.cpu.core import CpuCore, CpuCoreParams, CpuWork, analyze_cpu
from chipmodel.compute.gpu.occupancy import GpuSmParams, GpuBlock, derive_occupancy
from chipmodel.compute.npu.mac import MacArithmetic, MacArray, MacWork


# 独立分析夹具；不是具体CPU/GPU/NPU的器件档位。
def fixtures():
    clock = ClockDomain(domain_id="compute", frequency_hz=1e9)
    cpu = CpuCore(params=CpuCoreParams(fetch_uops_per_cycle=4, decode_uops_per_cycle=6,
                  issue_uops_per_cycle=3, retire_uops_per_cycle=2, execution_lanes=8, execution_ii_cycles=2),
                  clock=clock, uop_class="scalar-add/v1", profile_source="analytical-test/v1")
    gpu = GpuSmParams(warp_size=32, max_blocks_per_sm=16, max_warps_per_sm=64,
                      registers_per_sm=65536, shared_memory_bytes=65536, register_allocation_quantum=256,
                      shared_allocation_quantum_bytes=256, max_threads_per_block=1024, max_threads_per_sm=2048,
                      max_registers_per_thread=255, max_registers_per_block=65536, max_shared_bytes_per_block=49152,
                      profile_source="block-rounded-fixture/v1; no vendor calibration")
    arithmetic = MacArithmetic(operation="integer_mac", operand_format="int8", accumulator_format="int64", output_format="int64")
    mac = MacArray(params=PipelineParams(lane_count=4, latency_cycles=3, initiation_interval_cycles=2),
                   clock=clock, arithmetic=arithmetic, profile_source="analytical-test/v1")
    return cpu, gpu, mac


# CPU有限跨度只是不含延迟的必要条件，稳态限制项由精确有理比较确定。
class CpuCapabilityTests(unittest.TestCase):
    # 提交限制稳态2uop/cycle；9项的各阶段最后发起在2/1/2/2/4cycle。
    def test_stages_and_finite_span(self):
        cpu, _, _ = fixtures()
        result = analyze_cpu(cpu, CpuWork(uop_class=cpu.uop_class, executed_uops=9))
        self.assertEqual(result.bottlenecks, ("retire",))
        self.assertEqual(dict(result.stage_issue_spans_cycles), dict(fetch=2, decode=1, issue=2, execute=2, retire=4))
        self.assertEqual(result.issue_span_lower_bound_s, 4e-9)
        self.assertIsNone(result.execution_time_s)
        for count in (0, 1):
            empty = analyze_cpu(cpu, CpuWork(uop_class=cpu.uop_class, executed_uops=count))
            self.assertEqual((empty.issue_span_lower_bound_cycles, empty.span_bottlenecks), (0, ()))

    # 增加执行端口不突破提交；放宽提交才使瓶颈迁移到issue。
    def test_ablation_and_tied_stages(self):
        cpu, _, _ = fixtures()
        work = CpuWork(uop_class=cpu.uop_class, executed_uops=25)
        more = replace(cpu, params=replace(cpu.params, execution_lanes=16))
        self.assertEqual(analyze_cpu(cpu, work).peak_uops_per_s, analyze_cpu(more, work).peak_uops_per_s)
        issue = analyze_cpu(replace(cpu, params=replace(cpu.params, retire_uops_per_cycle=8)), work)
        self.assertEqual(issue.bottlenecks, ("issue",))
        tie = analyze_cpu(replace(cpu, params=replace(cpu.params, decode_uops_per_cycle=2)), work)
        self.assertEqual(tie.bottlenecks, ("decode", "retire"))

    # 用逐cycle发放槽的独立枚举验证有限跨度，涵盖尾组和不同II。
    def test_random_stage_enumeration(self):
        cpu, _, _ = fixtures()
        rng = random.Random(602)
        for _ in range(60):
            widths = [rng.randint(1, 8) for _ in range(5)]
            ii, work = rng.randint(1, 5), rng.randint(0, 40)
            p = CpuCoreParams(fetch_uops_per_cycle=widths[0], decode_uops_per_cycle=widths[1],
                              issue_uops_per_cycle=widths[2], execution_lanes=widths[3], retire_uops_per_cycle=widths[4], execution_ii_cycles=ii)
            result = analyze_cpu(replace(cpu, params=p), CpuWork(uop_class=cpu.uop_class, executed_uops=work))
            expected = []
            for width, interval in zip(widths, (1, 1, 1, ii, 1)):
                remaining, tick = work, 0
                while remaining > width:
                    remaining -= width
                    tick += interval
                expected.append(tick)
            self.assertEqual([value for _, value in result.stage_issue_spans_cycles], expected)
            self.assertEqual(result.peak_uops_per_cycle, float(min(Fraction(w, t) for w, t in zip(widths, (1, 1, 1, ii, 1)))))

    # 大整数在binary64显示上相等，不能把较快执行端口误判为同速瓶颈。
    def test_exact_bottlenecks_and_rejections(self):
        cpu, _, _ = fixtures()
        n = 2**53
        p = CpuCoreParams(fetch_uops_per_cycle=n, decode_uops_per_cycle=n+2, issue_uops_per_cycle=n+2,
                          retire_uops_per_cycle=n+2, execution_lanes=2*n+1, execution_ii_cycles=2)
        self.assertEqual(analyze_cpu(replace(cpu, params=p), CpuWork(uop_class=cpu.uop_class, executed_uops=n+1)).bottlenecks, ("fetch",))
        for core, work in ((replace(cpu, uop_class="unspecified"), CpuWork(uop_class="unspecified", executed_uops=1)),
                           (cpu, CpuWork(uop_class="multiply/v1", executed_uops=1))):
            with self.assertRaises(ValueError):
                analyze_cpu(core, work)
        with self.assertRaises(TypeError):
            CpuWork(uop_class="add", executed_uops=True)
        with self.assertRaises(TypeError):
            replace(cpu, params=None)


# GPU的驻留和单block启动限制分别验证；缺失限额保持未知。
class GpuCapabilityTests(unittest.TestCase):
    # 四个block同时触及register/shared，增加单项预算不能增加驻留。
    def test_limits_and_single_resource_ablation(self):
        _, p, _ = fixtures()
        block = GpuBlock(threads=256, registers_per_thread=64, shared_memory_bytes=16384)
        result = derive_occupancy(p, block)
        self.assertEqual(result.limiting_resources, ("registers", "shared_memory"))
        self.assertEqual((result.resident_blocks, result.resident_threads, result.launch_feasible), (4, 1024, True))
        more = derive_occupancy(replace(p, registers_per_sm=131072), block)
        self.assertEqual((more.resident_blocks, more.limiting_resources), (4, ("shared_memory",)))

    # 同occupancy却有不同有效线程比例；不得从warp占用推出任务吞吐。
    def test_tail_and_equal_occupancy(self):
        _, p, _ = fixtures()
        a = derive_occupancy(p, GpuBlock(threads=33, registers_per_thread=1, shared_memory_bytes=1))
        b = derive_occupancy(p, GpuBlock(threads=64, registers_per_thread=1, shared_memory_bytes=1))
        self.assertEqual(a.occupancy_fraction, b.occupancy_fraction)
        self.assertEqual((a.padded_threads_per_block, a.tail_thread_slots), (64, 31))
        self.assertEqual((a.thread_slot_efficiency, b.thread_slot_efficiency), (33/64, 1))
        self.assertEqual(a.allocated_registers_per_block, 256)

    # 预算足够并不代表单block能启动，每个违反项都返回解释。
    def test_launch_limits_and_unknowns(self):
        _, p, _ = fixtures()
        block = GpuBlock(threads=256, registers_per_thread=64, shared_memory_bytes=16384)
        for field, value in (("max_threads_per_block", 255), ("max_registers_per_thread", 63),
                             ("max_registers_per_block", 16383), ("max_shared_bytes_per_block", 16383)):
            result = derive_occupancy(replace(p, **{field:value}), block)
            self.assertEqual((result.resident_blocks, result.launch_feasible, result.launch_violations), (0, False, (field,)))
        incomplete = derive_occupancy(replace(p, max_threads_per_block=None), block)
        self.assertIsNone(incomplete.launch_feasible)
        self.assertEqual(incomplete.unknown_limits, ("max_threads_per_block",))
        self.assertEqual(incomplete.resident_blocks, 4)

    # 零需求无资源上限；线程槽上限按尾warp完整分配，容量不足不能标可行。
    def test_zero_demands_thread_slots_and_impossible(self):
        _, p, _ = fixtures()
        block = GpuBlock(threads=33, registers_per_thread=0, shared_memory_bytes=0)
        result = derive_occupancy(replace(p, max_threads_per_sm=96), block)
        self.assertEqual(result.resident_blocks, 1)
        self.assertIsNone(dict(result.block_limits)["registers"])
        self.assertIsNone(dict(result.block_limits)["shared_memory"])
        self.assertEqual(result.limiting_resources, ("thread_slots",))
        impossible = derive_occupancy(replace(p, max_threads_per_sm=32), block)
        self.assertFalse(impossible.launch_feasible)
        with self.assertRaises(ValueError):
            replace(p, allocation_policy="vendor-default")
        with self.assertRaises(TypeError):
            replace(p, max_threads_per_block=True)

    # 枚举可容纳的block数，再逐个消耗预算，与实现的商取最小值相互独立。
    def test_random_resource_consumption(self):
        _, base, _ = fixtures()
        rng = random.Random(606)
        for _ in range(80):
            p = replace(base, max_threads_per_sm=rng.randint(1, 2048), registers_per_sm=rng.randint(1, 65536),
                        shared_memory_bytes=rng.randint(0, 65536))
            b = GpuBlock(threads=rng.randint(1, 512), registers_per_thread=rng.randint(0, 100), shared_memory_bytes=rng.randint(0, 10000))
            slots = len(list(range(0, b.threads, 32))) * 32
            registers, shared = 0, 0
            while registers < slots * b.registers_per_thread:
                registers += 256
            while shared < b.shared_memory_bytes:
                shared += 256
            residents = 0
            for n in range(1, 17):
                if n*slots <= min(p.max_threads_per_sm, 2048) and n*registers <= p.registers_per_sm and n*shared <= p.shared_memory_bytes:
                    residents = n
            self.assertEqual(derive_occupancy(p, b).resident_blocks, residents)


# NPU显式服务签名与实际MAC计数；不通过位宽或产品名猜测性能。
class MacCapabilityTests(unittest.TestCase):
    # 九项在cycle0/2/4发起，7完成；12槽中3个尾槽未用，逻辑/实际工作独立。
    def test_service_tail_and_padding(self):
        _, _, array = fixtures()
        result = array.analyze(MacWork(arithmetic=array.arithmetic, logical_macs=7, executed_macs=9))
        self.assertEqual((result.extra_macs, result.issued_lane_slots, result.unused_tail_slots), (2, 12, 3))
        self.assertEqual((result.packing_efficiency, result.useful_work_fraction), (0.75, 7/9))
        self.assertEqual(result.service.completion_cycles, 7)
        self.assertIsNone(result.execution_time_s)
        self.assertIsNone(result.energy_j)
        empty = array.analyze(MacWork(arithmetic=array.arithmetic, logical_macs=0, executed_macs=0))
        self.assertEqual(empty.service.completion_cycles, 0)
        self.assertIsNone(empty.packing_efficiency)

    # 同为16bit的FP16/BF16和融合/非融合计算是不同签名，必须明确选择profile。
    def test_format_and_operation_rejection(self):
        _, _, array = fixtures()
        fp = MacArithmetic(operation="float_mul_add", operand_format="float16", accumulator_format="float32", output_format="float32")
        floating = replace(array, arithmetic=fp)
        for requested in (replace(fp, operand_format="bfloat16"), replace(fp, operation="float_fma"), array.arithmetic):
            with self.assertRaisesRegex(ValueError, "unsupported"):
                floating.analyze(MacWork(arithmetic=requested, logical_macs=4, executed_macs=4))
        with self.assertRaises(ValueError):
            replace(array, arithmetic=None).analyze(MacWork(arithmetic=array.arithmetic, logical_macs=0, executed_macs=0))
        with self.assertRaises(ValueError):
            replace(fp, output_format="float64")
        with self.assertRaises(ValueError):
            replace(fp, accumulator_format="int64", output_format="int64")

    # 时钟只缩放秒，L/II决定小批服务；不支持少算或bool实际工作。
    def test_clock_latency_and_work_contract(self):
        _, _, array = fixtures()
        work = MacWork(arithmetic=array.arithmetic, logical_macs=9, executed_macs=9)
        slow = replace(array, clock=replace(array.clock, frequency_hz=250e6)).analyze(work)
        self.assertEqual((slow.service.completion_cycles, slow.service.completion_time_s), (7, 28e-9))
        with self.assertRaises(ValueError):
            MacWork(arithmetic=array.arithmetic, logical_macs=10, executed_macs=9)
        with self.assertRaises(TypeError):
            replace(work, executed_macs=True)


if __name__ == "__main__":
    unittest.main()

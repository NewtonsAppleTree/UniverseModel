"""基础模型的手算与系统约束反例；不使用模型公式作为测试 oracle。"""

from dataclasses import replace
from math import exp, inf
import unittest

from chipmodel.common import ClockDomain, PipelineParams, estimate_pipeline
from chipmodel.compute.cpu.core import CpuCore, CpuCoreParams
from chipmodel.compute.gpu.occupancy import GpuSmParams, GpuBlock, derive_occupancy
from chipmodel.compute.npu.mac import GemmWorkload, MacArray
from chipmodel.compute.cim.arrays.conductance import ConductanceArray, ConductanceArrayParams, transimpedance
from chipmodel.compute.cim.encoding.accumulate import shift_accumulate
from chipmodel.compute.cim.encoding.bit_serial import BitSerialParams, derive_bit_serial
from chipmodel.compute.cim.periphery.adc import AdcParams, IdealAdc
from chipmodel.compute.cim.periphery.dac import VoltageDac, SampleHoldLimits
from chipmodel.control.data_movement import DmaParams, TensorLayout, estimate_dma
from chipmodel.memory.buffer import BufferParams
from chipmodel.memory.cache import CacheGeometry
from chipmodel.memory.sram.bank import SramParams, peak_sram_bandwidth
from chipmodel.memory.dram.organization import DramOrganization
from chipmodel.memory.controllers.dram_read import DramReadTiming, estimate_dram_read
from chipmodel.memory.flash.nand import NandGeometry, NandTiming
from chipmodel.interconnect.noc.path import NoCPathParams, estimate_noc_time
from chipmodel.interconnect.d2d.link import SerialLinkParams, estimate_link
from chipmodel.packaging.geometry.floorplan import Rectangle, validate_floorplan
from chipmodel.packaging.thermal.rc import ThermalRc
from chipmodel.composition.graph import ResourceNode, Port, Connection, validate_graph, validate_model_selection
from chipmodel.composition.bounds import ActionEstimate, ResourceDemand, ResourceBudget, estimate_time_bounds
from chipmodel.registry.models import ModelRegistry


# 建立手算用 1 GHz 时钟；此值是测试假设，不是器件速度档。
def clock() -> ClockDomain:
    return ClockDomain(domain_id="test", frequency_hz=1e9)


# 覆盖计算能力、位串行动作与真实 CIM 数值路径。
class ComputeTests(unittest.TestCase):
    # 四路 L=3/II=2：三组分别在 cycle 0/2/4 发起，末次在 7 完成。
    def test_pipeline_groups_and_clock(self):
        p = PipelineParams(lane_count=4, latency_cycles=3, initiation_interval_cycles=2)
        result = estimate_pipeline(p, clock(), 9)
        self.assertEqual((result.issue_groups, result.completion_cycles), (3, 7))
        self.assertEqual(result.completion_time_s, 7e-9)
        self.assertEqual(result.peak_items_per_s, 2e9)
        self.assertEqual(estimate_pipeline(p, clock(), 0).completion_time_s, 0)
        with self.assertRaises(TypeError):
            estimate_pipeline(p, clock(), True)
        with self.assertRaises(ValueError):
            ClockDomain(domain_id="test", frequency_hz=inf)

    # 提交宽度 2 限制所有更宽阶段；提高无关阶段不会提高峰值。
    def test_cpu_narrow_stage(self):
        p = CpuCoreParams(fetch_uops_per_cycle=4, decode_uops_per_cycle=6,
                          issue_uops_per_cycle=3, retire_uops_per_cycle=2,
                          execution_lanes=8, execution_ii_cycles=2)
        core = CpuCore(params=p, clock=clock())
        self.assertEqual(core.peak_uops_per_cycle, 2)
        self.assertEqual(core.peak_uops_per_s, 2e9)
        self.assertEqual(replace(core, params=replace(p, execution_lanes=16)).peak_uops_per_s, 2e9)

    # 256 threads/64 registers/thread/16 KiB shared：最多四个 block、32 warps。
    def test_gpu_capacity_and_tail_warp(self):
        p = GpuSmParams(warp_size=32, max_blocks_per_sm=16, max_warps_per_sm=64,
                        registers_per_sm=65536, shared_memory_bytes=65536,
                        register_allocation_quantum=256, shared_allocation_quantum_bytes=256)
        result = derive_occupancy(p, GpuBlock(threads=256, registers_per_thread=64,
                                             shared_memory_bytes=16384))
        self.assertEqual((result.resident_blocks, result.active_warps, result.occupancy_fraction), (4, 32, 0.5))
        tail = derive_occupancy(p, GpuBlock(threads=33, registers_per_thread=1, shared_memory_bytes=1))
        self.assertEqual(tail.allocated_registers_per_block, 256)
        self.assertEqual(tail.allocated_shared_bytes_per_block, 256)
        impossible = derive_occupancy(p, GpuBlock(threads=32, registers_per_thread=0, shared_memory_bytes=65537))
        self.assertEqual(impossible.resident_blocks, 0)

    # 2×4 与 4×3 的 4 bit 输入共 10 B；输出 6 个 16 bit 元素共 12 B。
    def test_gemm_logical_bytes_and_executed_work(self):
        w = GemmWorkload(m=2, n=3, k=4, operand_bits=4, output_bits=16)
        self.assertEqual((w.mac_count, w.input_bytes, w.output_bytes), (24, 10, 12))
        array = MacArray(params=PipelineParams(lane_count=4, latency_cycles=3,
                                               initiation_interval_cycles=2), clock=clock())
        self.assertEqual(array.estimate(w.mac_count).completion_cycles, 13)
        self.assertEqual(replace(w, k=0).output_bytes, 12)

    # 差分两阵列、四输入相位：2048 cell 动作；模拟求差只需 64 次 ADC。
    def test_bit_serial_accounting(self):
        p = BitSerialParams(input_bits=4, magnitude_bits=4, cell_bits=4,
                            differential=True, subtract_before_adc=True)
        work = derive_bit_serial(p, rows=16, columns=16)
        self.assertEqual((work.logical_macs, work.physical_arrays, work.cell_evaluations,
                          work.adc_conversions, work.physical_weight_bits), (256, 2, 2048, 64, 2048))
        digital = derive_bit_serial(replace(p, subtract_before_adc=False), rows=16, columns=16)
        self.assertEqual(digital.adc_conversions, 128)
        self.assertEqual(digital.cell_evaluations, work.cell_evaluations)

    # 使用二进制可精确表示的电导：两个列电流经 128 Ω 变为 0.5/0.75 V。
    def test_dac_array_tia_adc_path_and_input_isolation(self):
        dac = VoltageDac(resolution_bits=1, output_min_v=0, output_max_v=1)
        conductances = [[1 / 1024, 2 / 1024], [3 / 1024, 4 / 1024]]
        p = ConductanceArrayParams(rows=2, columns=2, conductance_min_s=0,
                                    conductance_max_s=4 / 1024, max_abs_input_v=1)
        array = ConductanceArray(params=p, conductances_s=conductances)
        conductances[0][0] = 0
        currents = array.evaluate((dac.convert(1), dac.convert(1)))
        self.assertEqual(currents, (4 / 1024, 6 / 1024))
        volts = transimpedance(currents, gain_ohm=128, offset_v=0)
        self.assertEqual(volts, (0.5, 0.75))
        adc = IdealAdc(params=AdcParams(resolution_bits=4, lane_count=2, conversion_cycles=2,
                                        initiation_interval_cycles=1, input_min_v=0, input_max_v=1), frequency_hz=1e9)
        self.assertEqual([sample.code for sample in adc.convert_many(volts)], [8, 12])
        with self.assertRaises(ValueError):
            array.evaluate((1,))
        with self.assertRaises(ValueError):
            array.evaluate((1, 2))

    # DAC 两端对齐；非法码/过期样本与累加溢出分别诊断。
    def test_conversion_and_accumulation_boundaries(self):
        dac = VoltageDac(resolution_bits=2, output_min_v=-1, output_max_v=2)
        self.assertEqual([dac.convert(i) for i in range(4)], [-1, 0, 1, 2])
        with self.assertRaises(ValueError):
            dac.convert(4)
        hold = SampleHoldLimits(slot_count=2, valid_duration_s=3e-9)
        hold.validate(sample_count=2, age_s=3e-9)
        for samples, age in ((3, 0), (1, 4e-9)):
            with self.assertRaises(ValueError):
                hold.validate(sample_count=samples, age_s=age)
        self.assertEqual(shift_accumulate((3, -1), (2, 1), width_bits=8, overflow="error"), 10)
        self.assertEqual(shift_accumulate((100, 100), (0, 0), width_bits=8, overflow="saturate"), 127)
        self.assertEqual(shift_accumulate((100, 100), (0, 0), width_bits=8, overflow="wrap"), -56)
        with self.assertRaises(ValueError):
            shift_accumulate((200,), (0,), width_bits=8, overflow="error")


# 覆盖容量、访问粒度与搬运量，防止存储组织被误当作数据带宽。
class MemoryAndMovementTests(unittest.TestCase):
    # 4 banks×256 words×8 B=8 KiB；连续 word 在四个 bank 间轮转。
    def test_sram_and_buffer_capacity(self):
        p = SramParams(bank_count=4, words_per_bank=256, word_bits=64,
                       read_ports_per_bank=1, write_ports_per_bank=0, access_ii_cycles=1)
        self.assertEqual(p.capacity_bytes, 8192)
        self.assertEqual([p.bank_for_address(i) for i in (0, 8, 16, 24, 32)], [0, 1, 2, 3, 0])
        self.assertEqual(peak_sram_bandwidth(p, clock(), write=False), 32e9)
        self.assertEqual(peak_sram_bandwidth(p, clock(), write=True), 0)
        buffer = BufferParams(slot_count=2, slot_bytes=72)
        self.assertEqual(buffer.capacity_bytes, 144)
        buffer.validate_payload(72)
        with self.assertRaises(ValueError):
            buffer.validate_payload(73)
        with self.assertRaises(ValueError):
            p.bank_for_address(8192)

    # 48-bit 地址减去 6-bit set 与 6-bit offset，留下 36-bit tag。
    def test_cache_geometry(self):
        cache = CacheGeometry(sets=64, ways=8, line_bytes=64, address_bits=48, status_bits_per_line=2)
        self.assertEqual((cache.capacity_bytes, cache.tag_bits, cache.metadata_bits), (32768, 36, 19456))
        with self.assertRaises(ValueError):
            replace(cache, sets=63)
        with self.assertRaises(ValueError):
            replace(cache, address_bits=8)

    # 5600 MT/s×64 bit 是 44.8 GB/s；rank 加倍只增加容量，2×32 subchannels 与 1×64 等价。
    def test_ddr_no_double_rate_or_rank_counting(self):
        p = DramOrganization(technology="assumed-ddr", channel_count=1, ranks_per_channel=1,
                             banks_per_rank=16, rows_per_bank=32768, columns_per_row=1024,
                             payload_width_bits=64, data_rate_mt_s=5600)
        self.assertEqual(p.capacity_bytes, 4 * 1024**3)
        self.assertEqual(p.peak_bandwidth_bytes_per_s, 44.8e9)
        ranks = replace(p, ranks_per_channel=2)
        self.assertEqual(ranks.capacity_bytes, 8 * 1024**3)
        self.assertEqual(ranks.peak_bandwidth_bytes_per_s, p.peak_bandwidth_bytes_per_s)
        subchannels = replace(p, channel_count=2, payload_width_bits=32)
        self.assertEqual(subchannels.capacity_bytes, p.capacity_bytes)
        self.assertEqual(subchannels.peak_bandwidth_bytes_per_s, p.peak_bandwidth_bytes_per_s)

    # 33 B 需要三个 16 B burst；命中/关闭/冲突的前缀相差 4 cycles。
    def test_dram_read_prefixes(self):
        p = DramReadTiming(t_rcd_cycles=4, t_cl_cycles=4, t_rp_cycles=4,
                           t_ccd_cycles=2, burst_cycles=2, burst_bytes=16)
        for state, cycles in (("hit", 10), ("closed", 14), ("conflict", 18)):
            result = estimate_dram_read(p, clock(), payload_bytes=33, row_state=state)
            self.assertEqual((result.transferred_bytes, result.completion_cycles), (48, cycles))
        self.assertEqual(estimate_dram_read(p, clock(), payload_bytes=0, row_state="hit").completion_cycles, 0)

    # NAND 原始容量包含独立 spare 计量，erase 的操作数以 block 为单位。
    def test_nand_granularity(self):
        geometry = NandGeometry(page_data_bytes=2048, page_spare_bytes=64, pages_per_block=64,
                                blocks_per_plane=1024, planes_per_die=2, die_count=2)
        self.assertEqual(geometry.raw_data_bytes, 512 * 1024**2)
        self.assertEqual(geometry.raw_total_bytes - geometry.raw_data_bytes, 16 * 1024**2)
        timing = NandTiming(page_read_s=10e-6, page_program_s=1e-3, block_erase_s=5e-3)
        self.assertAlmostEqual(timing.estimate_serial("read", 3), 30e-6)
        self.assertEqual(timing.estimate_serial("erase", 2), 0.01)
        with self.assertRaises(ValueError):
            timing.estimate_serial("write-byte", 1)

    # 一次请求启动、三个 burst 控制和五个数据拍，共 9 cycles。
    def test_dma_and_strided_layout(self):
        p = DmaParams(bytes_per_cycle=8, max_burst_bytes=16, startup_cycles=1, burst_overhead_cycles=1)
        result = estimate_dma(p, clock(), 33)
        self.assertEqual((result.burst_count, result.completion_cycles), (3, 9))
        self.assertEqual(estimate_dma(p, clock(), 0).completion_cycles, 0)
        layout = TensorLayout(shape=(2, 3), strides_bytes=(16, 4), element_bytes=4, base_address_bytes=128)
        self.assertEqual((layout.logical_bytes, layout.span_bytes, layout.address((1, 2))), (24, 28, 152))
        self.assertEqual(replace(layout, strides_bytes=(0, 4)).span_bytes, 12)
        with self.assertRaises(ValueError):
            layout.address((2, 0))
        with self.assertRaises(ValueError):
            replace(p, max_burst_bytes=17)


# 验证链路计量守恒与热/几何的物理边界。
class InterconnectAndPhysicalTests(unittest.TestCase):
    # 17 B payload+8 B header 共四 flit；三 hop 头延迟 9 cycles，加三个流水间隔。
    def test_noc_tail_flit(self):
        p = NoCPathParams(flit_bytes=8, header_bytes=8, router_latency_cycles=2,
                          link_latency_cycles=1, flit_ii_cycles=1)
        self.assertEqual(estimate_noc_time(p, clock(), payload_bytes=17, hops=3), 12e-9)

    # 两包各补齐 8b/10b，5 B payload+2 B protocol 形成 70 wire bits。
    def test_link_packet_and_lane_padding(self):
        p = SerialLinkParams(lane_count=2, lane_rate_bps=10e9, coding_data_bits=8,
                             coding_wire_bits=10, max_payload_bytes=4,
                             packet_overhead_bytes=1, fixed_latency_s=1e-9)
        result = estimate_link(p, 5)
        self.assertEqual((result.packet_count, result.protocol_bytes, result.wire_bits), (2, 2, 70))
        self.assertAlmostEqual(result.completion_time_s / 1e-9, 4.5)
        striped = replace(p, lane_count=3, packet_overhead_bytes=0)
        self.assertEqual(estimate_link(striped, 1).wire_bits, 12)
        self.assertEqual(estimate_link(p, 0).completion_time_s, 0)

    # 同层矩形允许边界接触，重叠和越界拒绝。
    def test_floorplan_boundaries(self):
        boundary = Rectangle(x_mm=0, y_mm=0, width_mm=10, height_mm=10)
        a = Rectangle(x_mm=0, y_mm=0, width_mm=5, height_mm=5)
        b = replace(a, x_mm=5)
        validate_floorplan(boundary, (a, b))
        self.assertEqual(boundary.area_mm2, 100)
        for invalid in (replace(b, x_mm=4), replace(b, x_mm=6)):
            with self.assertRaises(ValueError):
                validate_floorplan(boundary, (a, invalid))
        with self.assertRaises(ValueError):
            Rectangle(x_mm=1e20, y_mm=0, width_mm=1, height_mm=1)

    # R=2 K/W、C=5 J/K 的 τ=10 s；恒功率 10 W 后稳态 320 K。
    def test_thermal_energy_balance(self):
        model = ThermalRc(resistance_k_per_w=2, capacitance_j_per_k=5, ambient_temperature_k=300)
        self.assertEqual(model.time_constant_s, 10)
        self.assertEqual(model.steady_temperature(10), 320)
        self.assertEqual(model.temperature_after(initial_temperature_k=300, power_w=10, duration_s=0), 300)
        self.assertAlmostEqual(model.temperature_after(initial_temperature_k=300, power_w=10, duration_s=10),
                               320 - 20 / exp(1))
        cooled = model.temperature_after(initial_temperature_k=320, power_w=0, duration_s=10)
        self.assertTrue(300 < cooled < 320)


# 系统装配检验协议、资源唯一计量、因果 DAG 与带突发 credit 的资源界。
class CompositionTests(unittest.TestCase):
    # 电压和电流即使都是 float，也必须经过显式适配；连接图本身允许环。
    def test_graph_units_and_containment(self):
        a = ResourceNode(instance_id="a", parent_id=None, model_id="a/v1", ports=(
            Port(name="out", direction="output", protocol="sample/v1", unit="A"),
            Port(name="in", direction="input", protocol="sample/v1", unit="A")))
        b = replace(a, instance_id="b")
        edges = (Connection(source_id="a", source_port="out", target_id="b", target_port="in"),
                 Connection(source_id="b", source_port="out", target_id="a", target_port="in"))
        validate_graph((a, b), edges)
        changed = replace(b, ports=(replace(b.ports[0], unit="V"), replace(b.ports[1], unit="V")))
        with self.assertRaises(ValueError):
            validate_graph((a, changed), edges)
        with self.assertRaises(ValueError):
            validate_graph((replace(a, parent_id="b"), replace(b, parent_id="a")), ())

    # 摘要和后代不能对同一指标重复收费；选择单一层次允许。
    def test_summary_selection(self):
        nodes = (ResourceNode(instance_id="macro", parent_id=None, model_id="macro/v1"),
                 ResourceNode(instance_id="adc", parent_id="macro", model_id="adc/v1"))
        validate_model_selection(nodes, ("adc",))
        with self.assertRaises(ValueError):
            validate_model_selection(nodes, ("macro", "adc"))

    # 两个独立 1 s 操作各消耗 10 B，共享 10 B/s 资源使下界升为 2 s。
    def test_resource_and_dependency_bounds(self):
        budget = ResourceBudget(resource_id="link", work_unit="B", rate_per_s=10, initial_credit=0)
        demand = ResourceDemand(resource_id="link", work_unit="B", amount=10)
        a = ActionEstimate(action_id="a", latency_s=1, dependencies=(), demands=(demand,))
        b = replace(a, action_id="b")
        bound = estimate_time_bounds((a, b), (budget,))
        self.assertEqual((bound.critical_path_s, bound.resource_bound_s, bound.lower_bound_s), (1, 2, 2))
        serial = estimate_time_bounds((a, replace(b, dependencies=("a",))), (budget,))
        self.assertEqual(serial.critical_path_s, 2)

    # 首批 credit=1 允许在 t=0 发起，II=10 s 不应强迫单个 latency=1 s 的任务等 10 s。
    def test_initial_credit_and_graph_errors(self):
        demand = ResourceDemand(resource_id="lane", work_unit="item", amount=1)
        a = ActionEstimate(action_id="a", latency_s=1, dependencies=(), demands=(demand,))
        budget = ResourceBudget(resource_id="lane", work_unit="item", rate_per_s=0.1, initial_credit=1)
        self.assertEqual(estimate_time_bounds((a,), (budget,)).lower_bound_s, 1)
        with self.assertRaises(ValueError):
            estimate_time_bounds((replace(a, dependencies=("a",)),), (budget,))
        with self.assertRaises(ValueError):
            estimate_time_bounds((a,), (replace(budget, work_unit="B"),))
        with self.assertRaises(ValueError):
            estimate_time_bounds((a,), ())

    # Registry 不暴露内部映射；独立构造冻结参数，未知/重复 ID 拒绝。
    def test_registry_is_explicit_and_independent(self):
        registry = ModelRegistry()
        registry.register("buffer/v1", BufferParams)
        a = registry.create("buffer/v1", slot_count=2, slot_bytes=16)
        b = registry.create("buffer/v1", slot_count=2, slot_bytes=16)
        self.assertEqual(a, b)
        self.assertIsNot(a, b)
        self.assertEqual(ModelRegistry().model_ids(), ())
        with self.assertRaises(ValueError):
            registry.register("buffer/v1", BufferParams)
        with self.assertRaises(ValueError):
            registry.create("missing")


if __name__ == "__main__":
    unittest.main()

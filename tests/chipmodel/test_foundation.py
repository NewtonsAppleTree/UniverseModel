"""CH1–CH4 的独立算术、地址枚举、守恒与装配反例。"""

from dataclasses import replace
from fractions import Fraction
import random
import unittest

from chipmodel.common import ClockDomain, PipelineParams
from chipmodel.composition.bounds import ActionEstimate, ResourceBudget, ResourceDemand, estimate_time_bounds
from chipmodel.composition.graph import Connection, Port, ResourceNode, validate_graph, validate_model_selection
from chipmodel.composition.tile.digital import DigitalTile, TileWork, analyze_tile
from chipmodel.composition.transfer import (DmaResource, MemoryResource, PathLink, TransferRequest,
                                           TransferResources, analyze_transfers)
from chipmodel.control.data_movement import DmaParams
from chipmodel.interconnect.d2d.link import SerialLinkParams
from chipmodel.interconnect.noc.path import NoCPathParams, estimate_noc
from chipmodel.memory.buffer import BufferParams, BufferReservation, validate_reservations
from chipmodel.memory.sram.access import SramAccess, analyze_sram
from chipmodel.memory.sram.bank import SramParams, peak_sram_bandwidth
from configuration.resolution.dataclass_config import resolve_dataclass


# 独立夹具固定 4 bank × 16 word × 4 B，所有时钟为 1 GHz。
def fixture():
    clock = ClockDomain(domain_id="test", frequency_hz=1e9)
    sram = SramParams(bank_count=4, words_per_bank=16, word_bits=32,
                      read_ports_per_bank=1, write_ports_per_bank=1, access_ii_cycles=1,
                      supports_byte_write=True)
    return sram, clock


# 两 SRAM 经两个同构 hop 拷贝，MAC 作为同 owner 的独立叶子。
def fabric():
    p, clock = fixture()
    ids = ("src", "dst", "dma", "l0", "l1", "mac")
    nodes = (ResourceNode(instance_id="tile", parent_id=None, model_id=None),
             *(ResourceNode(instance_id=key, parent_id="tile", model_id="detail") for key in ids))
    memories = tuple(MemoryResource(resource_id=key, domain_id=key, capacity_bytes=256, sram=p, clock=clock)
                     for key in ("src", "dst"))
    channel = DmaResource(resource_id="dma", clock=clock, direct_memory_ids=("src",),
                          params=DmaParams(bytes_per_cycle=8, max_burst_bytes=16, startup_cycles=1, burst_overhead_cycles=0))
    noc = NoCPathParams(flit_bytes=4, header_bytes=4, router_latency_cycles=1, link_latency_cycles=1, flit_ii_cycles=1)
    links = tuple(PathLink(resource_id=key, source_domain=src, target_domain=dst, params=noc, clock=clock)
                  for key, src, dst in (("l0", "src", "middle"), ("l1", "middle", "dst")))
    return TransferResources(nodes=nodes, memories=memories, channels=(channel,), links=links)


# 默认拷贝 17 B，覆盖 5 个 word，DMA 2 burst、4 cycles，NoC 6 flit。
def copy_request(**changes):
    return replace(TransferRequest(request_id="copy", source_id="src", target_id="dst", source_address_bytes=0,
                                    target_address_bytes=0, payload_bytes=17, channel_id="dma", path=("l0", "l1")), **changes)


# 基础包络使用有理参考，输入契约与配置路径一致。
class ContractTests(unittest.TestCase):
    # G1: 2^53+1 减去 2^53 必须留下 1，JSON 参数也不能提前丢掉整数位。
    def test_integer_credit_and_config(self):
        demand = resolve_dataclass(ResourceDemand, dict(resource_id="r", work_unit="B", amount=2**53 + 1))
        budget = resolve_dataclass(ResourceBudget, dict(resource_id="r", work_unit="B", rate_per_s=1, initial_credit=2**53))
        action = ActionEstimate(action_id="a", latency_s=0, dependencies=(), demands=(demand,))
        self.assertEqual(estimate_time_bounds((action,), (budget,)).resource_bound_s, 1.0)

    # 大数、混合实数、动作乱序均对照 Fraction 独立参考。
    def test_rational_resource_reference_and_order(self):
        rng = random.Random(27)
        for _ in range(60):
            amounts = [2**53 + rng.randrange(20), rng.randrange(20), 0.25]
            credit, rate = 2**53, rng.randrange(1, 10)
            actions = tuple(ActionEstimate(action_id=str(i), latency_s=i / 8, dependencies=(),
                            demands=(ResourceDemand(resource_id="r", work_unit="B", amount=w),)) for i, w in enumerate(amounts))
            budgets = (ResourceBudget(resource_id="r", work_unit="B", rate_per_s=rate, initial_credit=credit),)
            expected = float((sum(map(Fraction, amounts)) - credit) / rate)
            self.assertEqual(estimate_time_bounds(actions, budgets).resource_bound_s, expected)
            self.assertEqual(estimate_time_bounds(actions, budgets), estimate_time_bounds(actions[::-1], budgets))

    # 正数下溢或派生溢出显式失败；真正零工作仍返回零。
    def test_numeric_range_and_zero(self):
        for amount, rate in ((5e-324, 1e308), (1e308, 5e-324)):
            action = ActionEstimate(action_id="a", latency_s=0, dependencies=(),
                                     demands=(ResourceDemand(resource_id="r", work_unit="B", amount=amount),))
            with self.assertRaises(ValueError):
                estimate_time_bounds((action,), (ResourceBudget(resource_id="r", work_unit="B", rate_per_s=rate, initial_credit=0),))
        self.assertEqual(estimate_time_bounds((), ()).lower_bound_s, 0)

    # G2 和嵌套假对象不能绕过直接调用的类型约束。
    def test_sequences_members_and_freezing(self):
        for dependencies, demands in (("load", ()), (("",), ()), ((7,), ()), ((), ("r",))):
            with self.assertRaises((ValueError, TypeError)):
                ActionEstimate(action_id="a", latency_s=0, dependencies=dependencies, demands=demands)
        deps = ["load"]
        action = ActionEstimate(action_id="a", latency_s=1, dependencies=deps, demands=())
        deps.clear()
        self.assertEqual(action.dependencies, ("load",))
        for actions, budgets in (("a", ()), ((object(),), ()), ((), (object(),))):
            with self.assertRaises(TypeError):
                estimate_time_bounds(actions, budgets)

    # 引用、单位和环的非法边界，不允许返回貌似有效的时间。
    def test_dag_and_demand_failures(self):
        base = ActionEstimate(action_id="a", latency_s=1, dependencies=(), demands=())
        for actions in ((base, base), (replace(base, dependencies=("absent",)),),
                        (replace(base, dependencies=("a",)),)):
            with self.assertRaises(ValueError):
                estimate_time_bounds(actions, ())
        demand = ResourceDemand(resource_id="r", work_unit="B", amount=1)
        for budgets in ((), (ResourceBudget(resource_id="r", work_unit="bit", rate_per_s=1, initial_credit=0),)):
            with self.assertRaises(ValueError):
                estimate_time_bounds((replace(base, demands=(demand,)),), budgets)

    # 图的身份、端口类型、重复边及摘要/后代计量互斥。
    def test_graph_contracts(self):
        with self.assertRaises(ValueError):
            Connection(source_id="", source_port="out", target_id="b", target_port="in")
        with self.assertRaises(TypeError):
            ResourceNode(instance_id="a", parent_id=None, model_id="x", ports=("bad",))
        out = Port(name="p", direction="output", protocol="v1", unit="B")
        nodes = (ResourceNode(instance_id="a", parent_id=None, model_id="sum", ports=(out,)),
                 ResourceNode(instance_id="b", parent_id="a", model_id="detail", ports=(replace(out, direction="input"),)))
        edge = Connection(source_id="a", source_port="p", target_id="b", target_port="p")
        validate_graph(nodes, (edge,))
        with self.assertRaises(ValueError):
            validate_graph(nodes, (edge, edge))
        with self.assertRaises(ValueError):
            validate_model_selection(nodes, ("a", "b"))
        with self.assertRaises(TypeError):
            validate_model_selection(nodes, "a")


# 地址枚举 oracle 按每一有效字节触及的 word 去重，每条请求之间不去重。
class SramAccessTests(unittest.TestCase):
    # 同逻辑 16 B 访问，bank 均匀分布 1 cycle，集中则 4 cycles。
    def test_balanced_conflicted_and_unaligned(self):
        p, clock = fixture()
        for addresses, expected, cycles in (((0, 4, 8, 12), (1, 1, 1, 1), 1), ((0, 16, 32, 48), (4, 0, 0, 0), 4)):
            reqs = tuple(SramAccess(request_id=str(i), address_bytes=a, length_bytes=4, direction="read") for i, a in enumerate(addresses))
            result = analyze_sram(p, clock, reqs)
            self.assertEqual((result.logical_read_bytes, result.bank_reads, result.completion_cycles), (16, expected, cycles))
        result = analyze_sram(p, clock, (SramAccess(request_id="tail", address_bytes=3, length_bytes=2, direction="read"),))
        self.assertEqual((result.logical_read_bytes, result.read_service_bytes, result.bank_reads), (2, 8, (1, 1, 0, 0)))

    # 穷举所有边界附近的小区间，与逐 byte 枚举构造的 word 集合比较。
    def test_address_enumeration_reference(self):
        p, clock = fixture()
        for address in range(256):
            for length in range(min(19, 256 - address) + 1):
                words = {byte // 4 for byte in range(address, address + length)}
                expected = tuple(sum(word % 4 == bank for word in words) for bank in range(4))
                request = SramAccess(request_id="a", address_bytes=address, length_bytes=length, direction="read")
                self.assertEqual(analyze_sram(p, clock, (request,)).bank_reads, expected)

    # 1R1W 与 1RW 在同 bank 不同 word 上的资源消融；L 和 II 不混同。
    def test_shared_port_and_latency(self):
        p, clock = fixture()
        reqs = (SramAccess(request_id="r", address_bytes=0, length_bytes=4, direction="read"),
                SramAccess(request_id="w", address_bytes=16, length_bytes=4, direction="write"))
        shared = replace(p, read_ports_per_bank=0, write_ports_per_bank=0, shared_rw_ports_per_bank=1)
        self.assertEqual(analyze_sram(p, clock, reqs).completion_cycles, 1)
        self.assertEqual(analyze_sram(shared, clock, reqs).completion_cycles, 2)
        self.assertEqual(analyze_sram(replace(shared, access_latency_cycles=3, access_ii_cycles=2), clock, reqs).completion_cycles, 5)
        self.assertEqual(peak_sram_bandwidth(shared, clock, write=True), 16e9)
        with self.assertRaises(ValueError):
            replace(p, shared_rw_ports_per_bank=1)

    # 零请求只验证地址边界；非整字写需要显式 byte-enable，无写端口则拒绝。
    def test_access_rejections_and_zero(self):
        p, clock = fixture()
        empty = SramAccess(request_id="e", address_bytes=256, length_bytes=0, direction="write")
        self.assertEqual(analyze_sram(p, clock, (empty,)).completion_time_s, 0)
        for changed, request in ((p, replace(empty, address_bytes=255, length_bytes=2)),
                                 (replace(p, supports_byte_write=False), replace(empty, address_bytes=1, length_bytes=1)),
                                 (replace(p, write_ports_per_bank=0), replace(empty, address_bytes=0, length_bytes=4))):
            with self.assertRaises(ValueError):
                analyze_sram(changed, clock, (request,))
        with self.assertRaises(ValueError):
            analyze_sram(p, clock, (empty, empty))

    # 预留 2×128 B 不新增 backing；重叠/越界/错误 backing 身份皆失败。
    def test_buffer_backing(self):
        first = BufferReservation(reservation_id="a", backing_id="s", offset_bytes=0,
                                   buffer=BufferParams(slot_count=1, slot_bytes=128))
        second = replace(first, reservation_id="b", offset_bytes=128)
        validate_reservations("s", 256, (second, first))
        for changed in (replace(second, offset_bytes=127), replace(second, offset_bytes=129), replace(second, backing_id="other")):
            with self.assertRaises(ValueError):
                validate_reservations("s", 256, (first, changed))


# 资源守恒和跨边界诊断；不以模型摘要自己证明其正确性。
class TransferTests(unittest.TestCase):
    # 手算：17 B→两端各 5 word，4 DMA cycles，6 flit/hop，2-hop 共9ns而非14ns。
    def test_ledger_and_wormhole(self):
        result = analyze_transfers(fabric(), (copy_request(),))
        self.assertEqual([(leg.role, leg.service_amount) for leg in result.legs],
                         [("source_read", 5), ("target_write", 5), ("dma", 4), ("link", 6), ("link", 6)])
        self.assertTrue(all(leg.logical_bytes == 17 for leg in result.legs))
        self.assertEqual(result.bounds.critical_path_s, 9e-9)
        self.assertEqual(result.lower_bound_s, 9e-9)
        self.assertEqual(sum(s.logical_read_bytes for _, s in result.sram_services), 17)
        self.assertEqual(sum(s.logical_write_bytes for _, s in result.sram_services), 17)

    # 多请求累计到同一通道/链路；资源和顺序约束分别有效。
    def test_shared_demands_and_dependencies(self):
        requests = (copy_request(request_id="a"), copy_request(request_id="b"))
        result = analyze_transfers(fabric(), requests)
        contributions = {c.resource_id: c for c in result.contributions}
        self.assertEqual((contributions["dma"].amount, contributions["l0"].amount), (8, 12))
        self.assertEqual(result.lower_bound_s, 11e-9)
        serial = analyze_transfers(fabric(), (requests[0], replace(requests[1], dependencies=("a",))))
        self.assertEqual(serial.bounds.critical_path_s, 18e-9)

    # 缺路径、反方向、不连续、错地址和重复 ID 不会被解释为免费服务。
    def test_invalid_routes_and_ownership(self):
        for changes in (dict(path=()), dict(path=("l1", "l0")), dict(path=("absent",)),
                        dict(path=("l0",)), dict(source_address_bytes=250), dict(channel_id="missing")):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                analyze_transfers(fabric(), (copy_request(**changes),))
        resources = fabric()
        with self.assertRaises(ValueError):
            replace(resources, nodes=tuple(replace(n, parent_id=None) if n.instance_id == "dma" else n for n in resources.nodes))
        with self.assertRaises(ValueError):
            replace(resources, channels=(*resources.channels, resources.channels[0]))
        changed = replace(resources.links[1], params=replace(resources.links[1].params, flit_bytes=8))
        with self.assertRaisesRegex(ValueError, "bridge"):
            analyze_transfers(replace(resources, links=(resources.links[0], changed)), (copy_request(),))

    # D2D独立分包：17 B拆16+1，每包4B开销，8b/10b共250 wire bits。
    def test_d2d_encoding_and_unknown_memory(self):
        resources = fabric()
        serial = SerialLinkParams(lane_count=1, lane_rate_bps=1e9, coding_data_bits=8, coding_wire_bits=10,
                                   max_payload_bytes=16, packet_overhead_bytes=4, fixed_latency_s=2e-9)
        link = PathLink(resource_id="l0", source_domain="src", target_domain="dst", params=serial)
        memories = (MemoryResource(resource_id="src", domain_id="src", capacity_bytes=256,
                                    unknown_reason="No external memory profile"), resources.memories[1])
        result = analyze_transfers(replace(resources, links=(link,), memories=memories), (copy_request(path=("l0",)),))
        leg = result.legs[-1]
        self.assertEqual((leg.service_unit, leg.service_amount, leg.packet_count, leg.protocol_bytes), ("bit", 250, 2, 8))
        self.assertIsNone(result.legs[0].isolated_time_s)
        self.assertTrue(result.unknown_costs)
        self.assertAlmostEqual(result.lower_bound_s, 252e-9, delta=1e-20)

    # 明确直接可达才允许空路径；零请求不发起协议或端口工作。
    def test_direct_route_empty_and_noc_api(self):
        resources = fabric()
        resources = replace(resources, channels=(replace(resources.channels[0], direct_memory_ids=("src", "dst")),))
        result = analyze_transfers(resources, (copy_request(path=(), payload_bytes=0),))
        self.assertEqual(result.lower_bound_s, 0)
        self.assertTrue(all(leg.service_amount == 0 for leg in result.legs))
        noc = estimate_noc(resources.links[0].params, resources.links[0].clock, payload_bytes=0, hops=2)
        self.assertEqual((noc.packet_count, noc.protocol_bytes, noc.flit_count), (0, 0, 0))


# 无 compiler 的 Tile 台架也能直接验证供数、预留和零工作。
class DigitalTileTests(unittest.TestCase):
    # DMA写与本地读共用1RW端口会累计，独立R/W则可以各用一组端口。
    def test_local_and_dma_share_backing(self):
        resources = fabric()
        dst = resources.memories[1]
        shared = replace(dst, sram=replace(dst.sram, read_ports_per_bank=0, write_ports_per_bank=0, shared_rw_ports_per_bank=1))
        resources = replace(resources, memories=(resources.memories[0], shared))
        tile = DigitalTile(resources=resources, scratch_id="dst", mac_resource_id="mac",
                            mac=PipelineParams(lane_count=4, latency_cycles=1, initiation_interval_cycles=1),
                            compute_clock=fixture()[1])
        reads = tuple(SramAccess(request_id=f"r{i}", address_bytes=0, length_bytes=4, direction="read") for i in range(10))
        reservation = BufferReservation(reservation_id="slot", backing_id="dst", offset_bytes=0,
                                          buffer=BufferParams(slot_count=2, slot_bytes=128))
        work = TileWork(work_id="test", executed_macs=4, local_accesses=reads,
                         transfers=(copy_request(payload_bytes=4),), reservations=(reservation,))
        analysis = analyze_tile(tile, work)
        self.assertEqual(analysis.scratch_service.bank_reads, (10, 0, 0, 0))
        self.assertEqual(analysis.scratch_service.bank_writes, (1, 0, 0, 0))
        self.assertEqual(analysis.lower_bound_s, 11e-9)
        self.assertIn("dst/bank/0", analysis.bottlenecks)
        self.assertIsNone(analysis.energy_j)
        with self.assertRaisesRegex(ValueError, "reserved"):
            analyze_tile(tile, replace(work, reservations=()))
        empty = TileWork(work_id="empty", executed_macs=0, local_accesses=(), transfers=(), reservations=())
        self.assertEqual(analyze_tile(tile, empty).lower_bound_s, 0)


if __name__ == "__main__":
    unittest.main()

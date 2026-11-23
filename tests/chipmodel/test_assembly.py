"""CH8共享容量、实际跨界流量、依赖/时钟及同指标摘要的独立检查。"""

from dataclasses import replace
from fractions import Fraction
import random
import unittest

from chipmodel.common import ClockDomain, PipelineParams
from chipmodel.composition.die.topology import DomainPlacement
from chipmodel.composition.graph import ResourceNode
from chipmodel.composition.package.assembly import AssemblyJob, ChipAssembly, analyze_assembly, project_scopes
from chipmodel.composition.tile.binding import TileBinding
from chipmodel.composition.tile.digital import TileWork, analyze_tile
from chipmodel.composition.transfer import DmaResource, MemoryResource, PathLink, TransferRequest, TransferResources
from chipmodel.compute.npu.mac import MacArray
from chipmodel.control.data_movement import DmaParams
from chipmodel.interconnect.d2d.link import SerialLinkParams
from chipmodel.interconnect.noc.path import NoCPathParams
from chipmodel.memory.buffer import BufferParams, BufferReservation
from chipmodel.memory.sram.access import SramAccess
from chipmodel.memory.sram.bank import SramParams


# 单Die两个MAC引用同一个512B单bank SRAM；通道/时钟身份均显式。
def shared_fixture(tile_count=2):
    clock = ClockDomain(domain_id="sram", frequency_hz=1e9)
    sram = SramParams(bank_count=1, words_per_bank=128, word_bits=32, read_ports_per_bank=1,
                      write_ports_per_bank=1, access_ii_cycles=1, supports_byte_write=True)
    nodes = [ResourceNode(instance_id="die", parent_id=None, model_id=None),
             ResourceNode(instance_id="scratch", parent_id="die", model_id="sram"),
             ResourceNode(instance_id="dma", parent_id="die", model_id="dma")]
    tiles = []
    for i in range(tile_count):
        nodes.extend((ResourceNode(instance_id=f"tile{i}", parent_id="die", model_id=None),
                      ResourceNode(instance_id=f"mac{i}", parent_id=f"tile{i}", model_id="mac")))
        tiles.append(TileBinding(tile_id=f"tile{i}", scratch_id="scratch", mac_resource_id=f"mac{i}",
                     mac=MacArray(params=PipelineParams(lane_count=4, latency_cycles=1, initiation_interval_cycles=1),
                                  clock=ClockDomain(domain_id=f"mac{i}", frequency_hz=1e9), profile_source="synthetic")))
    resources = TransferResources(nodes=tuple(nodes), memories=(MemoryResource(resource_id="scratch", domain_id="mem",
        capacity_bytes=512, sram=sram, clock=clock),), channels=(DmaResource(resource_id="dma", clock=clock,
        params=DmaParams(bytes_per_cycle=16, max_burst_bytes=64, startup_cycles=0, burst_overhead_cycles=0),
        direct_memory_ids=("scratch",)),))
    return ChipAssembly(scope_id="die", die_ids=("die",), resources=resources,
                        domains=(DomainPlacement(domain_id="mem", die_id="die"),), tiles=tuple(tiles), profile_source="synthetic")


# 每job默认32MAC、8次4B本地读，声明32B窗口；同一工作可改变Tile位置。
def job(i, *, tile="tile0", base=0, macs=32, reads=8, scratch="scratch", transfers=(), dependencies=()):
    return AssemblyJob(job_id=str(i), tile_id=tile, dependencies=dependencies, work=TileWork(work_id="block",
        executed_macs=macs, local_accesses=tuple(SramAccess(request_id=f"r{n}", address_bytes=base + n * 4,
            length_bytes=4, direction="read") for n in range(reads)), transfers=transfers,
        reservations=(BufferReservation(reservation_id="buffer", backing_id=scratch, offset_bytes=base,
                      buffer=BufferParams(slot_count=1, slot_bytes=max(32, reads * 4))),)))


# 双Die各有SRAM/MAC/DMA，两方向D2D使用独立资源；17B产生两packet、250wire bit。
def package_fixture():
    base = shared_fixture()
    clock = base.resources.memories[0].clock
    nodes = [ResourceNode(instance_id="package", parent_id=None, model_id=None)]
    memories, channels, domains, tiles = [], [], [], []
    for i in range(2):
        nodes.extend((ResourceNode(instance_id=f"die{i}", parent_id="package", model_id=None),
            ResourceNode(instance_id=f"s{i}", parent_id=f"die{i}", model_id="sram"),
            ResourceNode(instance_id=f"dma{i}", parent_id=f"die{i}", model_id="dma"),
            ResourceNode(instance_id=f"tile{i}", parent_id=f"die{i}", model_id=None),
            ResourceNode(instance_id=f"mac{i}", parent_id=f"tile{i}", model_id="mac")))
        memories.append(replace(base.resources.memories[0], resource_id=f"s{i}", domain_id=f"mem{i}"))
        channels.append(replace(base.resources.channels[0], resource_id=f"dma{i}", direct_memory_ids=(f"s{i}",)))
        domains.append(DomainPlacement(domain_id=f"mem{i}", die_id=f"die{i}"))
        tiles.append(replace(base.tiles[i], scratch_id=f"s{i}"))
    params = SerialLinkParams(lane_count=1, lane_rate_bps=1e9, coding_data_bits=8, coding_wire_bits=10,
                               max_payload_bytes=16, packet_overhead_bytes=4, fixed_latency_s=2e-9)
    links = []
    for source, target in ((0, 1), (1, 0)):
        key = f"d{source}{target}"
        nodes.append(ResourceNode(instance_id=key, parent_id="package", model_id="d2d"))
        links.append(PathLink(resource_id=key, source_domain=f"mem{source}", target_domain=f"mem{target}", params=params))
    resources = TransferResources(nodes=tuple(nodes), memories=tuple(memories), channels=tuple(channels), links=tuple(links))
    return ChipAssembly(scope_id="package", die_ids=("die0", "die1"), resources=resources,
                        domains=tuple(domains), tiles=tuple(tiles), profile_source="synthetic")


# 跨界读入目标scratch；逻辑byte、协议byte和线路bit在边界分别计量。
def copy_request(i="copy", source=0, target=1, target_address=0):
    return TransferRequest(request_id=i, source_id=f"s{source}", target_id=f"s{target}", source_address_bytes=0,
        target_address_bytes=target_address, payload_bytes=17, channel_id=f"dma{source}", path=(f"d{source}{target}",))


# 容量、包络、依赖和边界语义，不把运行成功当作真实可行调度。
class AssemblyTests(unittest.TestCase):
    # 一job与原独立Tile服务界一致；没有第二份容器服务或budget。
    def test_single_tile_equivalence(self):
        assembly, work = shared_fixture(), job("one")
        a = analyze_assembly(assembly, (work,))
        b = analyze_tile(assembly.tiles[0].bind(assembly.resources), work.work)
        self.assertEqual(a.lower_bound_s, b.lower_bound_s)
        self.assertEqual(dict(a.memory_services)["scratch"], b.scratch_service)
        self.assertEqual(a.memory_capacities, (("scratch", 512),))
        self.assertIsNone(a.execution_time_s)
        self.assertIsNone(a.energy_j)

    # 两Tile共享一份SRAM，MAC并行不能减少16次共享bank服务；加一个读端口才降到8ns。
    def test_shared_memory_limits_scaling(self):
        p = shared_fixture()
        jobs = (job("a"), job("b", base=64))
        serial = analyze_assembly(p, jobs)
        parallel = analyze_assembly(p, (jobs[0], replace(jobs[1], tile_id="tile1")))
        self.assertEqual((serial.lower_bound_s, parallel.lower_bound_s), (16e-9, 16e-9))
        memory = p.resources.memories[0]
        faster = replace(p, resources=replace(p.resources, memories=(replace(memory, sram=replace(memory.sram, read_ports_per_bank=2)),)))
        improved = analyze_assembly(faster, (jobs[0], replace(jobs[1], tile_id="tile1")))
        self.assertEqual(improved.lower_bound_s, 8e-9)
        self.assertEqual(sum(size for _, size in parallel.memory_capacities), 512)
        port = next(c for c in parallel.contributions if c.resource_id == "scratch/bank/0/read")
        self.assertEqual((port.amount, port.lower_bound_s), (16, 15e-9))

    # 计算主导时同硬件把两份工作分给两Tile有收益，实际MAC和访问保持不变。
    def test_compute_placement_and_shared_engine(self):
        p = shared_fixture()
        jobs = (job("a", macs=64), job("b", base=64, macs=64))
        a = analyze_assembly(p, jobs)
        b = analyze_assembly(p, (jobs[0], replace(jobs[1], tile_id="tile1")))
        self.assertEqual((a.lower_bound_s, b.lower_bound_s), (32e-9, 16e-9))
        self.assertEqual(sum(c.amount for c in a.contributions if c.work_unit == "MAC"), 128)
        self.assertEqual(sum(c.amount for c in b.contributions if c.work_unit == "MAC"), 128)

    # 同一MAC的L/II不重置为两份硬件；独立16项为9cycle，完整job依赖则为5+5cycle。
    def test_shared_mac_latency_and_interval(self):
        p = shared_fixture()
        first = replace(p.tiles[0], mac=replace(p.tiles[0].mac, params=PipelineParams(
            lane_count=4, latency_cycles=3, initiation_interval_cycles=2)))
        p = replace(p, tiles=(first, p.tiles[1]))
        jobs = (job("a", macs=8, reads=0), job("b", macs=8, reads=0, base=64))
        self.assertEqual(analyze_assembly(p, jobs).lower_bound_s, 9e-9)
        self.assertEqual(analyze_assembly(p, (jobs[0], replace(jobs[1], dependencies=("a",)))).lower_bound_s, 10e-9)

    # 预留半开区间邻接合法；并发重叠失败，完整前驱允许重复使用地址。
    def test_live_region_and_dependency_bounds(self):
        p = shared_fixture()
        first, second = job("a", macs=64), job("b", tile="tile1", macs=64)
        with self.assertRaisesRegex(ValueError, "overlapping"):
            analyze_assembly(p, (first, second))
        ordered = analyze_assembly(p, (replace(second, dependencies=("a",)), first))
        self.assertEqual(ordered.bounds.critical_path_s, 32e-9)
        self.assertEqual(ordered.lower_bound_s, 32e-9)
        self.assertEqual(analyze_assembly(p, (first, job("c", base=32))).memory_capacities, (("scratch", 512),))

    # 随机两job独立手算：每bank离散端口组和MAC组，最后取必要最大值。
    def test_random_integer_service_oracle(self):
        rng = random.Random(801)
        for _ in range(45):
            p = shared_fixture()
            lanes0, lanes1, ports = rng.randint(1, 8), rng.randint(1, 8), rng.randint(1, 4)
            f0, f1, fs = rng.choice((5e8, 1e9)), rng.choice((5e8, 2e9)), rng.choice((5e8, 1e9))
            tiles = tuple(replace(t, mac=replace(t.mac, params=replace(t.mac.params, lane_count=lanes),
                           clock=replace(t.mac.clock, frequency_hz=f))) for t, lanes, f in zip(p.tiles, (lanes0, lanes1), (f0, f1)))
            m = p.resources.memories[0]
            # DMA与原SRAM同域；一并换域以免给同一身份两种频率。
            memory = replace(m, sram=replace(m.sram, read_ports_per_bank=ports), clock=ClockDomain(domain_id="memory-only", frequency_hz=fs))
            p = replace(p, tiles=tiles, resources=replace(p.resources, memories=(memory,)))
            r0, r1, w0, w1 = (rng.randint(1, 8) for _ in range(4))
            result = analyze_assembly(p, (job("a", reads=r0, macs=w0), job("b", tile="tile1", base=64, reads=r1, macs=w1)))
            expected = max(Fraction((r0 + r1 + ports - 1) // ports) / Fraction(fs),
                           Fraction((w0 + lanes0 - 1) // lanes0) / Fraction(f0),
                           Fraction((w1 + lanes1 - 1) // lanes1) / Fraction(f1))
            self.assertEqual(result.lower_bound_s, float(expected))

    # 同一D2D串行方向累计两个请求；每次17B→2packet、8B协议、250bit。
    def test_cross_die_shared_link(self):
        p = package_fixture()
        jobs = (job("a", tile="tile1", scratch="s1", reads=0, macs=0, transfers=(copy_request(),)),
                job("b", tile="tile1", scratch="s1", base=64, reads=0, macs=0,
                    transfers=(copy_request(target_address=64),)))
        result = analyze_assembly(p, jobs)
        traffic = next(t for t in result.boundary_traffic if t.link_id == "d01")
        self.assertEqual((traffic.payload_bytes, traffic.protocol_bytes, traffic.wire_bits, traffic.packet_count), (34, 16, 500, 4))
        self.assertEqual(result.lower_bound_s, 500e-9)
        self.assertEqual(dict(result.memory_services)["s0"].bank_reads, (10,))
        self.assertEqual(dict(result.memory_services)["s1"].bank_writes, (10,))
        faster_link = replace(p.resources.links[0], params=replace(p.resources.links[0].params, lane_count=2))
        faster = replace(p, resources=replace(p.resources, links=(faster_link, p.resources.links[1])))
        self.assertEqual(analyze_assembly(faster, jobs).lower_bound_s, 250e-9)

    # 两方向由独立link预算实现full duplex，不能把总wire量再除单方向带宽。
    def test_full_duplex_and_namespaces(self):
        p = package_fixture()
        jobs = (job("a/b", tile="tile1", scratch="s1", reads=0, macs=0, transfers=(copy_request(),)),
                job("a", tile="tile0", scratch="s0", reads=0, macs=0, transfers=(copy_request(source=1, target=0),)))
        result = analyze_assembly(p, jobs)
        self.assertEqual([t.wire_bits for t in result.boundary_traffic], [250, 250])
        self.assertEqual(result.lower_bound_s, 252e-9)
        self.assertEqual(len({a.action_id for a in result.actions}), len(result.actions))

    # 摘要和叶子视图使用同一包络指标；容量和贡献无重复，混选祖先/后代失败。
    def test_summary_projection_and_overlap(self):
        p = package_fixture()
        r = analyze_assembly(p, (job("a", tile="tile1", scratch="s1", reads=0, macs=0, transfers=(copy_request(),)),))
        whole = project_scopes(r, ("package",))
        dies = project_scopes(r, ("die0", "die1", "d01", "d10"))
        leaves = project_scopes(r, ("s0", "s1", "dma0", "dma1", "mac0", "mac1", "d01", "d10"))
        for reports in (whole, dies, leaves):
            self.assertEqual(sum(s.memory_capacity_bytes for s in reports), 1024)
            self.assertEqual(max(s.resource_lower_bound_s for s in reports), r.bounds.resource_bound_s)
            self.assertEqual(len([c for s in reports for c in s.contributions]), len(r.contributions))
        for selected in (("package", "die0"), ("die0",), ("missing",), ("package", "package")):
            with self.assertRaises(ValueError):
                project_scopes(r, selected)

    # 错放置、缺domain、伪造NoC跨Die、远程scratch和同名异频都在装配时拒绝。
    def test_topology_and_clock_guards(self):
        p = package_fixture()
        with self.assertRaisesRegex(ValueError, "exactly once"):
            replace(p, domains=p.domains[:1])
        with self.assertRaisesRegex(ValueError, "backing die"):
            replace(p, domains=(replace(p.domains[0], die_id="die1"), p.domains[1]))
        with self.assertRaisesRegex(ValueError, "local scratch"):
            replace(p, tiles=(replace(p.tiles[0], scratch_id="s1"), p.tiles[1]))
        link = replace(p.resources.links[0], params=NoCPathParams(flit_bytes=4, header_bytes=0,
                        router_latency_cycles=1, link_latency_cycles=1, flit_ii_cycles=1), clock=p.tiles[0].mac.clock)
        with self.assertRaisesRegex(ValueError, "NoC"):
            replace(p, resources=replace(p.resources, links=(link, p.resources.links[1])))
        changed = replace(p.tiles[1], mac=replace(p.tiles[1].mac,
                          clock=ClockDomain(domain_id="mac0", frequency_hz=2e9)))
        with self.assertRaisesRegex(ValueError, "inconsistent frequency"):
            replace(p, tiles=(p.tiles[0], changed))

    # 不能通过DMA直接附加远程backing跳过D2D；缺路由和错误方向也拒绝。
    def test_cross_boundary_bypass_and_owner(self):
        p = package_fixture()
        with self.assertRaisesRegex(ValueError, "remote memory"):
            replace(p, resources=replace(p.resources, channels=(replace(p.resources.channels[0], direct_memory_ids=("s0", "s1")), p.resources.channels[1])))
        for path in ((), ("d10",)):
            work = job("a", tile="tile1", scratch="s1", reads=0, macs=0, transfers=(replace(copy_request(), path=path),))
            with self.assertRaises(ValueError):
                analyze_assembly(p, (work,))
        nodes = tuple(replace(n, parent_id="tile1") if n.instance_id == "mac0" else n for n in p.resources.nodes)
        with self.assertRaisesRegex(ValueError, "owning tile"):
            replace(p, resources=replace(p.resources, nodes=nodes))

    # 不完整依赖、环、重复任务、未知tile和宿主展开超限都保留诊断。
    def test_job_guards_and_zero(self):
        p = shared_fixture()
        for jobs in ((job("a", dependencies=("none",)),), (job("a", dependencies=("b",)), job("b", base=64, dependencies=("a",))),
                     (job("a"), job("a", base=64)), (job("a", tile="unknown"),)):
            with self.assertRaises(ValueError):
                analyze_assembly(p, jobs)
        with self.assertRaisesRegex(ValueError, "host limit"):
            analyze_assembly(p, (job("a"), job("b", base=64)), max_jobs=1)
        with self.assertRaisesRegex(ValueError, "host limit"):
            analyze_assembly(p, (job("a"),), max_accesses=1)
        empty = analyze_assembly(p, ())
        self.assertEqual((empty.lower_bound_s, empty.actions, empty.unknown_costs), (0, (), ()))


if __name__ == "__main__":
    unittest.main()

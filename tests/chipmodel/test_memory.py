"""CH7的地址/流量/状态独立参考；不以分析成功证明器件性能。"""

from dataclasses import replace
from itertools import permutations, product
import random
import unittest

from chipmodel.common import ClockDomain
from chipmodel.composition.graph import ResourceNode
from chipmodel.composition.memory import analyze_cached_dram
from chipmodel.composition.transfer import DmaResource, MemoryResource, TransferRequest, TransferResources, analyze_transfers
from chipmodel.control.data_movement import DmaParams
from chipmodel.memory.access import MemoryAccess
from chipmodel.memory.cache import CacheGeometry, CacheParams, CacheState, trace_cache
from chipmodel.memory.controllers.dram_read import DramReadProfile, DramReadTiming, estimate_dram_access, estimate_dram_span
from chipmodel.memory.dram.organization import DramOrganization, decode_dram_address
from chipmodel.memory.flash.nand import NandGeometry, NandReadProfile, NandReadRequest, NandReadState, NandTiming, analyze_nand_reads


# 合成64B行、16B burst、1GHz CK、2GT/s、16-bit有效接口；无器件性能主张。
def dram_fixture(**changes):
    organization = DramOrganization(technology="synthetic", channel_count=1, ranks_per_channel=1, banks_per_rank=2,
                                    rows_per_bank=4, columns_per_row=32, payload_width_bits=16, data_rate_mt_s=2000)
    timing = DramReadTiming(t_rcd_cycles=3, t_cl_cycles=4, t_rp_cycles=5, t_ccd_cycles=4, burst_cycles=4, burst_bytes=16)
    clock = ClockDomain(domain_id="ck", frequency_hz=1e9)
    return replace(DramReadProfile(organization=organization, timing=timing, ck=clock, data_clock=clock,
                                   transfers_per_data_clock=2, burst_transfers=8, profile_source="synthetic-v1"), **changes)


# 标准两set单路16B缓存；状态预算不包含真实LRU电路成本。
def cache_fixture(**changes):
    return CacheParams(geometry=replace(CacheGeometry(sets=2, ways=1, line_bytes=16, address_bits=16,
                                                       status_bits_per_line=2), **changes), profile_source="synthetic-v1")


# 页数据32B/OOB4B，阵列10us，外部1MB/s，命令2us的串行合成路径。
def nand_fixture(**changes):
    return replace(NandReadProfile(geometry=NandGeometry(page_data_bytes=32, page_spare_bytes=4, pages_per_block=4,
                                                        blocks_per_plane=2, planes_per_die=1, die_count=1),
                                  timing=NandTiming(page_read_s=10e-6, page_program_s=20e-6, block_erase_s=100e-6),
                                  output_bytes_per_s=1e6, command_overhead_s=2e-6, profile_source="synthetic-v1"), **changes)


# 简写输入仍走生产校验；identity取序号，所有长度单位为byte。
def access(i, address, length=1, direction="read"):
    return MemoryAccess(request_id=str(i), address_bytes=address, length_bytes=length, direction=direction)


# DRAM逐地址枚举、burst集合和共享总线的独立检查。
class DramTests(unittest.TestCase):
    # 用嵌套笛卡尔积产生物理坐标，不重复生产混合进制除法。
    def test_mixed_radix_mapping(self):
        p = replace(dram_fixture().organization, channel_count=2, ranks_per_channel=2, banks_per_rank=3,
                    rows_per_bank=2, columns_per_row=2)
        sizes = {"channel": 2, "rank": 2, "bank": 3, "row": 2}
        for order in permutations(sizes):
            expected = product(*(range(sizes[d]) for d in reversed(order)))
            for block, coords in enumerate(expected):
                values = dict(zip(reversed(order), coords))
                for offset in range(4):
                    decoded = decode_dram_address(p, block * 4 + offset, row_order=order)
                    self.assertEqual({d: getattr(decoded, d) for d in sizes}, values)
                    self.assertEqual((decoded.column, decoded.byte_in_column, decoded.row_offset_bytes), (offset // 2, offset % 2, offset))
        with self.assertRaises(ValueError):
            decode_dram_address(p, p.capacity_bytes)
        with self.assertRaises(ValueError):
            decode_dram_address(p, 0, row_order=("bank", "bank", "row", "rank"))

    # 穷举单行byte集合映射到burst集合；验证头尾不对齐和三种命令前缀。
    def test_burst_coverage_and_row_states(self):
        p = dram_fixture()
        for start in range(64):
            for length in range(65 - start):
                result = estimate_dram_access(p, access("r", start, length), row_state="hit")
                count = len({b // 16 for b in range(start, start + length)})
                self.assertEqual((result.burst_count, result.transferred_bytes), (count, count * 16))
        self.assertEqual([estimate_dram_access(p, access("r", 15, 2), row_state=s).completion_cycles
                          for s in ("hit", "closed", "conflict")], [12, 15, 20])

    # 单行入口拒绝越界；span保留每个片段条件而非虚构连续执行时间。
    def test_cross_row_and_host_limit(self):
        p, request = dram_fixture(), access("cross", 63, 3)
        with self.assertRaisesRegex(ValueError, "row boundary"):
            estimate_dram_access(p, request, row_state="closed")
        span = estimate_dram_span(p, request, row_state="closed")
        self.assertEqual([(f.address_bytes, f.logical_bytes, f.transferred_bytes) for f in span.fragments], [(63, 1, 16), (64, 2, 16)])
        self.assertEqual(span.channel_transferred_bytes, ((0, 32),))
        self.assertEqual(span.lower_bound_s, 11e-9)
        self.assertIsNone(span.execution_time_s)
        with self.assertRaisesRegex(ValueError, "host limit"):
            estimate_dram_span(p, request, row_state="hit", max_fragments=1)

    # 有效速率、BL字节和整数CK持续时间任一矛盾均失败；WCK显式换算可通过。
    def test_clock_binding(self):
        p = dram_fixture()
        for changes in (dict(organization=replace(p.organization, data_rate_mt_s=4000)),
                        dict(timing=replace(p.timing, burst_bytes=32)), dict(timing=replace(p.timing, burst_cycles=3)),
                        dict(organization=replace(p.organization, columns_per_row=31))):
            with self.assertRaises(ValueError):
                replace(p, **changes)
        wck = replace(p, data_clock=ClockDomain(domain_id="wck", frequency_hz=2e9),
                      organization=replace(p.organization, data_rate_mt_s=4000), timing=replace(p.timing, burst_cycles=2))
        self.assertEqual(wck.channel_bandwidth_bytes_per_s, 8e9)
        with self.assertRaisesRegex(ValueError, "two frequencies"):
            replace(wck, data_clock=replace(wck.data_clock, domain_id="ck"))

    # rank只增加容量；跨channel的满行工作各使用自己的总线。
    def test_rank_and_channel_bandwidth(self):
        p = dram_fixture()
        ranks = replace(p.organization, ranks_per_channel=2)
        self.assertEqual(ranks.capacity_bytes, 2 * p.organization.capacity_bytes)
        self.assertEqual(ranks.peak_bandwidth_bytes_per_s, p.organization.peak_bandwidth_bytes_per_s)
        dual = replace(p, organization=replace(p.organization, channel_count=2), row_order=("channel", "bank", "row", "rank"))
        span = estimate_dram_span(dual, access(0, 0, 128), row_state="hit")
        self.assertEqual(span.channel_transferred_bytes, ((0, 64), (1, 64)))
        self.assertEqual(span.interface_lower_bound_s, 16e-9)

    # 零读允许容量末端；越界、write和无效行状态不可套读时序。
    def test_zero_and_invalid(self):
        p = dram_fixture()
        self.assertEqual(estimate_dram_span(p, access(0, 512, 0), row_state="hit").lower_bound_s, 0)
        for request, state in ((access(0, 512), "hit"), (access(0, 0, 1, "write"), "hit"), (access(0, 0), "guess")):
            with self.assertRaises(ValueError):
                estimate_dram_span(p, request, row_state=state)
        for changes in (dict(address_bytes=True), dict(length_bytes=-1), dict(direction="execute")):
            with self.assertRaises((ValueError, TypeError)):
                replace(access(0, 0), **changes)


# 缓存状态/脏流量参考与冷暖状态边界。
class CacheTests(unittest.TestCase):
    # 两set单路0/32冲突；dirty逐出先写回后填充，flush清dirty但保留有效行。
    def test_dirty_eviction_and_flush(self):
        p = cache_fixture()
        requests = (access(0, 0, 1, "write"), access(1, 0), access(2, 32), access(3, 16, 1, "write"))
        r = trace_cache(p, requests)
        self.assertEqual((r.line_hits, r.line_misses, r.fill_bytes, r.writeback_bytes, r.deferred_dirty_bytes), (1, 3, 48, 16, 16))
        self.assertEqual([(a.direction, a.address_bytes) for a in r.backing_accesses], [("read", 0), ("write", 0), ("read", 32), ("read", 16)])
        flushed = trace_cache(p, (), initial_state=r.final_state, flush=True)
        self.assertEqual((flushed.writeback_bytes, flushed.deferred_dirty_bytes), (16, 0))
        self.assertEqual(flushed.final_state.lru_lines, r.final_state.lru_lines)

    # 独立时间戳参考：每set选最小last-access，而非复用生产LRU列表操作。
    def test_random_timestamp_oracle(self):
        rng = random.Random(731)
        for case in range(60):
            p = cache_fixture(sets=rng.choice((1, 2, 4)), ways=rng.randint(1, 4))
            requests = tuple(access(i, rng.randrange(256), rng.randrange(20), rng.choice(("read", "write"))) for i in range(40))
            actual = trace_cache(p, requests, flush=True)
            residents, expected, backing, tick = {}, [], [], 0
            for request in requests:
                lines = sorted({b // 16 for b in range(request.address_bytes, request.address_bytes + request.length_bytes)})
                for line in lines:
                    hit = line in residents
                    if not hit:
                        peers = [n for n in residents if n % p.geometry.sets == line % p.geometry.sets]
                        if len(peers) == p.geometry.ways:
                            victim = min(peers, key=lambda n: residents[n][0])
                            if residents[victim][1]:
                                backing.append(("write", victim * 16))
                            del residents[victim]
                        backing.append(("read", line * 16))
                    dirty = request.direction == "write" or (hit and residents[line][1])
                    residents[line] = (tick, dirty)
                    expected.append(hit)
                    tick += 1
            backing.extend(("write", n * 16) for n in sorted(residents) if residents[n][1])
            self.assertEqual([t.hit for t in actual.touches], expected, case)
            self.assertEqual([(a.direction, a.address_bytes) for a in actual.backing_accesses], backing, case)

    # 整行覆盖写仍write-allocate；跨行触及统计与原请求数分开。
    def test_cross_line_full_write_and_zero(self):
        p = cache_fixture()
        r = trace_cache(p, (access(0, 15, 2), access(1, 16, 16, "write")))
        self.assertEqual((r.line_hits, r.line_misses, r.fill_bytes), (1, 2, 32))
        cold = trace_cache(p, (access(0, 0, 16, "write"),))
        self.assertEqual((cold.fill_bytes, cold.deferred_dirty_bytes), (16, 16))
        empty = trace_cache(p, (access(0, 1 << 16, 0),))
        self.assertEqual((empty.touches, empty.backing_accesses), ((), ()))

    # 两批显式快照恢复与一次完整运行在状态和实际事务上等价。
    def test_chunked_resume(self):
        p = cache_fixture(ways=2)
        requests = tuple(access(i, a, 1, "write" if i % 2 else "read") for i, a in enumerate((0, 32, 0, 64, 16, 32, 96)))
        full = trace_cache(p, requests)
        first = trace_cache(p, requests[:3])
        second = trace_cache(p, requests[3:], initial_state=first.final_state)
        self.assertEqual(second.final_state, full.final_state)
        self.assertEqual(first.touches + second.touches, full.touches)
        self.assertEqual([(a.direction, a.address_bytes) for a in first.backing_accesses + second.backing_accesses],
                         [(a.direction, a.address_bytes) for a in full.backing_accesses])

    # 非法快照、未知策略、host超限和输入身份均显式失败。
    def test_invalid_states_and_limits(self):
        p = cache_fixture()
        for lines, dirty in (((0, 32), ()), ((1,), ()), ((0, 0), ()), ((), (0,)), ((1 << 16,), ())):
            with self.assertRaises(ValueError):
                CacheState(params=p, lru_lines=lines, dirty_lines=dirty)
        with self.assertRaises(ValueError):
            trace_cache(p, (), initial_state=CacheState(params=cache_fixture(ways=2)))
        with self.assertRaisesRegex(ValueError, "host limit"):
            trace_cache(p, (access(0, 0, 33),), max_line_touches=2)
        for requests in ((access(0, 0), access(0, 1)), (access(0, 1 << 16),)):
            with self.assertRaises(ValueError):
                trace_cache(p, requests)
        for changes in (dict(policy="random"), dict(geometry=replace(p.geometry, status_bits_per_line=1))):
            with self.assertRaises(ValueError):
                replace(p, **changes)


# NAND页buffer与外部列传输严格分开；不验证FTL/写入状态。
class NandTests(unittest.TestCase):
    # 冷页读data+OOB36B入buffer，输出6B；同页再输出1B只增加接口和命令。
    def test_page_buffer_and_output(self):
        p = nand_fixture()
        requests = (NandReadRequest(request_id="a", page_index=0, data_bytes=4, spare_bytes=2),
                    NandReadRequest(request_id="b", page_index=0, spare_offset_bytes=3, spare_bytes=1))
        r = analyze_nand_reads(p, requests)
        self.assertEqual([s.page_buffer_hit for s in r.steps], [False, True])
        self.assertEqual([s.array_loaded_bytes for s in r.steps], [36, 0])
        self.assertEqual((r.array_read_pages, r.data_output_bytes, r.spare_output_bytes), (1, 4, 3))
        self.assertAlmostEqual(r.modeled_time_s, 21e-6)
        evicted = analyze_nand_reads(p, (replace(requests[0], page_index=1), requests[1]), initial_state=r.final_state)
        self.assertEqual(evicted.array_read_pages, 2)

    # 分批恢复保存页命中与同一串行策略时间；未知接口/命令不能变成0。
    def test_resume_and_unknown(self):
        p = nand_fixture()
        requests = tuple(NandReadRequest(request_id=str(i), page_index=i // 2, data_bytes=1) for i in range(4))
        first = analyze_nand_reads(p, requests[:1])
        second = analyze_nand_reads(p, requests[1:], initial_state=first.final_state)
        full = analyze_nand_reads(p, requests)
        self.assertEqual(first.steps + second.steps, full.steps)
        self.assertEqual(second.final_state, full.final_state)
        self.assertAlmostEqual(first.modeled_time_s + second.modeled_time_s, full.modeled_time_s)
        r = analyze_nand_reads(replace(p, output_bytes_per_s=None, command_overhead_s=None), requests[:1])
        self.assertIsNone(r.modeled_time_s)
        self.assertEqual(len(r.unknown_costs), 2)
        self.assertEqual(r.known_service_s, 10e-6)

    # 零输出不加载页、不改变缓冲，在profile缺失部分成本时仍是0工作。
    def test_zero_and_geometry_bounds(self):
        p = nand_fixture(output_bytes_per_s=None, command_overhead_s=None)
        request = NandReadRequest(request_id="z", page_index=7, data_offset_bytes=32, spare_offset_bytes=4)
        r = analyze_nand_reads(p, (request,))
        self.assertEqual((r.array_read_pages, r.modeled_time_s, r.final_state.buffered_page, r.unknown_costs), (0, 0, None, ()))
        for changes in (dict(page_index=8), dict(data_bytes=1), dict(spare_bytes=1)):
            with self.assertRaises(ValueError):
                analyze_nand_reads(p, (replace(request, **changes),))

    # 多die或跨profile缓冲不能隐式套用单路径；读/编程/擦除各自独立特征化。
    def test_profile_state_and_operation_separation(self):
        p = nand_fixture()
        with self.assertRaises(ValueError):
            replace(p, geometry=replace(p.geometry, die_count=2))
        with self.assertRaises(ValueError):
            analyze_nand_reads(p, (), initial_state=NandReadState(profile=replace(p, profile_source="other")))
        self.assertEqual([p.timing.estimate_serial(op, 1) for op in ("read", "program", "erase")], [10e-6, 20e-6, 100e-6])


# 对同一个物理backing累计工作，保持读写成本和全执行时间边界。
class MemoryCompositionTests(unittest.TestCase):
    # 0/32冲突流量64B；相同访问增加一路可降至32B，但容量预算翻倍。
    def test_cache_to_dram_reuse_and_dirty(self):
        requests = tuple(access(i, address) for i, address in enumerate((0, 32, 0, 32)))
        a = analyze_cached_dram(cache_fixture(), dram_fixture(), requests, row_state="hit")
        b = analyze_cached_dram(cache_fixture(ways=2), dram_fixture(), requests, row_state="hit")
        self.assertEqual((a.cache.fill_bytes, b.cache.fill_bytes), (64, 32))
        self.assertEqual((a.channel_read_bytes, b.channel_read_bytes), (((0, 64),), ((0, 32),)))
        self.assertEqual((a.read_lower_bound_s, b.read_lower_bound_s), (16e-9, 8e-9))
        dirty = analyze_cached_dram(cache_fixture(), dram_fixture(), (access(0, 0, 1, "write"),), row_state="hit", flush=True)
        self.assertEqual(dirty.cache.writeback_bytes, 16)
        self.assertTrue(any("writeback" in reason for reason in dirty.unknown_costs))
        self.assertIsNone(dirty.execution_time_s)
        with self.assertRaises(ValueError):
            analyze_cached_dram(cache_fixture(), dram_fixture(), (access(0, 512),), row_state="hit")

    # 构建两个明确端点和一个DMA；资源owner不由介质profile偷偷增加。
    def fabric(self):
        p = dram_fixture(organization=replace(dram_fixture().organization, ranks_per_channel=2))
        memories = tuple(MemoryResource(resource_id=i, domain_id=i, capacity_bytes=p.organization.capacity_bytes,
                                         dram_read=p) for i in ("src", "dst"))
        nodes = (ResourceNode(instance_id="owner", parent_id=None, model_id=None), *(ResourceNode(instance_id=i, parent_id="owner", model_id=i)
                                                     for i in ("src", "dst", "dma")))
        dma = DmaResource(resource_id="dma", params=DmaParams(bytes_per_cycle=16, max_burst_bytes=64,
                          startup_cycles=0, burst_overhead_cycles=0), clock=p.ck, direct_memory_ids=("src", "dst"))
        return TransferResources(nodes=nodes, memories=memories, channels=(dma,))

    # 两rank请求进入同一个channel预算；目标write未知，没有复用读时序或再次收费摘要。
    def test_transfer_shared_rank_bus_and_unknown_write(self):
        fabric = self.fabric()
        requests = tuple(TransferRequest(request_id=str(i), source_id="src", target_id="dst", source_address_bytes=i * 512,
                          target_address_bytes=i * 64, payload_bytes=64, channel_id="dma", source_row_state="hit") for i in range(2))
        r = analyze_transfers(fabric, requests)
        contribution = next(c for c in r.contributions if c.resource_id == "src/channel/0/read_bus")
        self.assertEqual((contribution.amount, contribution.lower_bound_s), (128, 32e-9))
        self.assertEqual(r.lower_bound_s, 32e-9)
        self.assertEqual(len(r.dram_services), 2)
        self.assertTrue(all(l.isolated_time_s is None for l in r.legs if l.role == "target_write"))
        self.assertTrue(any("write service" in reason for reason in r.unknown_costs))
        with self.assertRaisesRegex(ValueError, "explicit source_row_state"):
            analyze_transfers(fabric, (replace(requests[0], source_row_state=None),))

    # 互斥profile、容量不一致和派生ID碰撞都在计量前失败。
    def test_transfer_profile_and_id_guards(self):
        fabric = self.fabric()
        for changes in (dict(capacity_bytes=1), dict(clock=dram_fixture().ck), dict(unknown_reason="other")):
            with self.assertRaises(ValueError):
                replace(fabric.memories[0], **changes)
        collision = ResourceNode(instance_id="src/channel/0/read_bus", parent_id="owner", model_id=None)
        with self.assertRaisesRegex(ValueError, "collides"):
            analyze_transfers(replace(fabric, nodes=(*fabric.nodes, collision)), ())


if __name__ == "__main__":
    unittest.main()

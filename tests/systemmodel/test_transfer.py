"""Independent conventional packet, byte-conservation, ownership and whole-copy service-bound evidence."""

from dataclasses import replace
from pathlib import Path
import json
import random
import unittest
from unittest.mock import patch

from configuration.resolution.dataclass_config import resolve_dataclass
from systemmodel.io.dma.analysis import analyze_transfers, validate_transfers
from systemmodel.io.dma.model import CopyBatch, DmaSystem
from systemmodel.io.pcie.model import packetize_write


ROOT = Path(__file__).resolve().parents[2]  # Local hand-reviewable inputs; no experiment producer used by model tests.


# Professional models are checked independently of the study's expected outcomes and summary implementation.
class TransferTests(unittest.TestCase):
    # Immutable fixture copies permit adversarial replacements without cross-test state.
    def setUp(self):
        raw = json.loads((ROOT/'config/experiments/system_transfer.json').read_text(encoding='utf-8'))
        self.system = resolve_dataclass(DmaSystem,raw['system'])
        self.cases = {c['name']:c for c in raw['cases']}
        self.batch = resolve_dataclass(CopyBatch,self.cases['direct']['batch'])

    # Two aligned 256 B writes carry 512 useful + 48 protocol bytes; coding belongs to capacity, not this count.
    def test_hand_packet_and_rate(self):
        traffic = packetize_write(self.system.profile,4096,512)
        self.assertEqual((traffic.packet_count,traffic.padding_bytes,traffic.frame_bytes),(2,0,560))
        rate = self.system.pcie_services[0].frame_capacity_Bps(self.system.profile)
        self.assertAlmostEqual(rate,4*8e9*128/130/8)
        self.assertEqual(packetize_write(self.system.profile,4096,1).frame_bytes,28)

    # Unaligned DWORD byte enables and the 4 KiB split add payload padding independently of TLP headers.
    def test_tail_and_page_boundary(self):
        tail = packetize_write(self.system.profile,4099,513)
        self.assertEqual((tail.packet_count,tail.padded_payload_bytes,tail.padding_bytes,tail.frame_bytes),(3,516,3,588))
        boundary = packetize_write(self.system.profile,4095,2)
        self.assertEqual((boundary.packet_count,boundary.padded_payload_bytes,boundary.frame_bytes),(2,8,56))
        end = packetize_write(self.system.profile,(1<<64)-1,1)
        self.assertEqual((end.packet_count,end.padded_payload_bytes),(1,4))
        with self.assertRaises(ValueError):
            packetize_write(self.system.profile,(1<<64)-1,2)

    # Enumerate DWORD addresses per packet as an independent reference for 160 fixed-seed address/length/MPS cases.
    def test_packetization_against_word_oracle(self):
        rng = random.Random(60719)
        for trial in range(160):
            profile = replace(self.system.profile,max_payload_bytes=rng.choice((128,256,512,1024,2048,4096)))
            start,length = rng.randrange(8192),rng.randrange(1,18000)
            words = list(range(start//4,(start+length-1)//4+1))
            packets,padded,index = 0,0,0
            while index<len(words):
                first = words[index]
                packet = []
                while index<len(words) and len(packet)<profile.max_payload_bytes//4 and words[index]//1024==first//1024:
                    packet.append(words[index])
                    index += 1
                packets += 1
                padded += len(packet)*4
            actual = packetize_write(profile,start,length)
            with self.subTest(trial=trial):
                self.assertEqual((actual.packet_count,actual.padded_payload_bytes,actual.frame_bytes),(packets,padded,padded+24*packets))
                self.assertEqual(actual.payload_bytes+actual.padding_bytes+actual.protocol_bytes,actual.frame_bytes)

    # Page batching handles large byte extents without per-packet allocation or iteration across the whole payload.
    def test_large_transfer_packet_count(self):
        size = 1<<44
        traffic = packetize_write(self.system.profile,0,size)
        self.assertEqual(traffic.packet_count,size//256)
        self.assertEqual(traffic.frame_bytes,size+size//256*24)

    # Direct copy hand ledger: DMA=100+2*4+16=124 cycles; shared payload ceiling gives 512 ns.
    def test_direct_hand_ledger(self):
        result = analyze_transfers(self.system,self.batch)
        self.assertEqual(result.legs[0].dma.completion_cycles,124)
        work = {c.resource_id:c for c in result.contributions}
        self.assertEqual(work['gpu0.dma'].amount,124)
        self.assertEqual(work['root_bus'].amount,512)
        self.assertEqual(work['service.gpu0.tx'].amount,560)
        self.assertEqual(work['service.gpu1.rx'].amount,560)
        self.assertAlmostEqual(result.bounds.lower_bound_s,512e-9)
        self.assertEqual(result.actions[0].dependencies,())
        self.assertEqual(result.staging_allocation_ids,())
        self.assertEqual([(m.backing_id,m.read_bytes,m.write_bytes) for m in result.memory_work],[('gpu0.mem',512,0),('gpu1.mem',0,512)])
        self.assertTrue(result.unknown_costs)

    # Whole-buffer staging conserves useful bytes but performs two copies and charges host read/write separately.
    def test_staging_conservation_and_dependencies(self):
        batch = resolve_dataclass(CopyBatch,self.cases['staged']['batch'])
        result = analyze_transfers(self.system,batch)
        self.assertEqual([l.traffic.payload_bytes for l in result.legs],[512,512])
        self.assertEqual(result.actions[1].dependencies,('to_host',))
        self.assertEqual(result.staging_allocation_ids,('staging.copy',))
        host = next(w for w in result.memory_work if w.backing_id=='host.mem')
        self.assertEqual((host.read_bytes,host.write_bytes),(512,512))
        self.assertAlmostEqual(result.bounds.critical_path_s,1024e-9)
        self.assertAlmostEqual(result.bounds.lower_bound_s,1024e-9)
        self.assertEqual(result.legs[0].target.physical_offset_bytes,result.legs[1].source.physical_offset_bytes)

    # Independent copies keep single-copy critical latency while their work accumulates at the shared root resource.
    def test_shared_batch_bound(self):
        batch = resolve_dataclass(CopyBatch,self.cases['two_shared']['batch'])
        result = analyze_transfers(self.system,batch)
        self.assertAlmostEqual(result.bounds.critical_path_s,512e-9)
        self.assertAlmostEqual(result.bounds.resource_bound_s,1024e-9)
        self.assertEqual(len([b for b in result.budgets if b.resource_id=='root_bus']),1)
        self.assertEqual(next(c.amount for c in result.contributions if c.resource_id=='root_bus'),1024)

    # Startup controls small transfers; removing it is an explicit hardware ablation, not a new workload.
    def test_startup_and_bandwidth_sensitivity(self):
        batch = resolve_dataclass(CopyBatch,self.cases['small_1B']['batch'])
        full = analyze_transfers(self.system,batch)
        engines = tuple(replace(e,params=replace(e.params,startup_cycles=0)) for e in self.system.engines)
        reduced = analyze_transfers(replace(self.system,engines=engines),batch)
        self.assertAlmostEqual(full.bounds.lower_bound_s,105e-9)
        self.assertLess(reduced.bounds.lower_bound_s,full.bounds.lower_bound_s)
        topology = self.system.memory.node.topology
        topology = replace(topology,constraints=tuple(replace(c,capacity_Bps=2e9) for c in topology.constraints))
        memory = replace(self.system.memory,node=replace(self.system.memory.node,topology=topology))
        system = replace(self.system,memory=memory)
        rebound = replace(self.batch,placement=replace(self.batch.placement,memory_identity=memory.identity_hash))
        self.assertAlmostEqual(analyze_transfers(system,rebound).bounds.lower_bound_s,256e-9)

    # All reviewed negative candidates fail for actual model reasons, independent of expected_status labels.
    def test_negative_controls(self):
        for case in self.cases.values():
            if case['expected_status']=='failed':
                with self.subTest(case=case['name']),self.assertRaises(ValueError):
                    analyze_transfers(self.system,resolve_dataclass(CopyBatch,case['batch']))

    # A saved path must remain legal; replay never replaces it by a newly searched route.
    def test_saved_route_validation(self):
        result = analyze_transfers(self.system,self.batch)
        with patch('systemmodel.io.dma.analysis.find_path',side_effect=AssertionError('searched')):
            self.assertEqual(result,validate_transfers(self.system,self.batch,tuple(l.path for l in result.legs)))
        with self.assertRaises(ValueError):
            validate_transfers(self.system,self.batch,())
        wrong = replace(result.legs[0].path,target_domain_id='host.address')
        with self.assertRaises(ValueError):
            validate_transfers(self.system,self.batch,(wrong,))

    # Shared physical line references count each real visit; a half-duplex declaration cannot invent two capacities.
    def test_repeated_physical_line_service(self):
        source = next(s for s in self.system.pcie_services if s.resource_id=='service.gpu0.tx')
        services = tuple(s for s in self.system.pcie_services if s.resource_id not in ('service.gpu0.tx','service.gpu1.rx'))
        combined = replace(source,link_ids=('gpu0.tx','gpu1.rx'))
        system = replace(self.system,pcie_services=(*services,combined))
        result = analyze_transfers(system,self.batch)
        self.assertEqual(next(c.amount for c in result.contributions if c.resource_id==source.resource_id),1120)
        self.assertEqual(len([b for b in result.budgets if b.resource_id==source.resource_id]),1)

    # A different source address alias for the same staging bytes retains physical continuity and capacity identity.
    def test_staging_alias_continuity(self):
        batch = resolve_dataclass(CopyBatch,self.cases['staged']['batch'])
        view = next(r for r in batch.placement.regions if r.region_id=='staging')
        placement = replace(batch.placement,regions=(*batch.placement.regions,replace(view,region_id='stage_alias',base_address=8192)))
        chain = batch.chains[0]
        chain = replace(chain,legs=(chain.legs[0],replace(chain.legs[1],source_region_id='stage_alias',source_address=8192)))
        result = analyze_transfers(self.system,replace(batch,placement=placement,chains=(chain,)))
        self.assertEqual(result.staging_allocation_ids,('staging.copy',))

    # Read/read sharing is valid, but independently writing bytes read by another chain needs explicit ordering.
    def test_cross_chain_read_write_hazard(self):
        direct = self.batch.chains[0]
        reverse = resolve_dataclass(CopyBatch,self.cases['reverse_staged']['batch']).chains[0]
        with self.assertRaisesRegex(ValueError,'hazard'):
            analyze_transfers(self.system,replace(self.batch,chains=(direct,replace(reverse,chain_id='reverse'))))

    # Invalid ownership, duplicate summaries and incomplete wire service cannot silently create throughput.
    def test_service_ownership_and_coverage(self):
        engine = self.system.engines[0]
        for engine_change in ({'egress_port_id':'missing'},{'read_backing_ids':('host.mem',)}):
            with self.assertRaises(ValueError):
                replace(self.system,engines=(replace(engine,**engine_change),))
        service = self.system.pcie_services[0]
        for service_change in ({'resource_id':'missing'},{'resource_id':'root_bus'},{'resource_id':'gpu0'}, {'link_ids':('missing',)}):
            with self.assertRaises(ValueError):
                replace(self.system,pcie_services=(replace(service,**service_change),))
        with self.assertRaises(ValueError):
            replace(self.system,pcie_services=(*self.system.pcie_services,service))
        incomplete = replace(self.system,pcie_services=tuple(s for s in self.system.pcie_services if 'gpu1.rx' not in s.link_ids))
        with self.assertRaisesRegex(ValueError,'unmodeled PCIe'):
            analyze_transfers(incomplete,self.batch)

    # Fitted average bandwidth is not a necessary service ceiling; frame summaries require exact format identity.
    def test_constraint_basis_and_ceiling(self):
        for changes in ({'capacity_kind':'effective_service'},{'byte_basis':'frame','frame_format_id':'other'}):
            topology = self.system.memory.node.topology
            topology = replace(topology,constraints=tuple(replace(c,**changes) for c in topology.constraints))
            memory = replace(self.system.memory,node=replace(self.system.memory.node,topology=topology))
            with self.assertRaises(ValueError):
                replace(self.system,memory=memory)

    # Counts, MPS, clock/rate and route budgets must reject malformed scalar inputs rather than coerce them.
    def test_scalar_guards_and_identity(self):
        for changes in ({'max_payload_bytes':64},{'max_payload_bytes':True},{'coding_wire_bits':127},{'tlp_overhead_bytes':0}):
            with self.assertRaises((TypeError,ValueError)):
                replace(self.system.profile,**changes)
        for changes in ({'lane_count':0},{'lane_rate_transfers_s':float('inf')}):
            with self.assertRaises((TypeError,ValueError)):
                replace(self.system.pcie_services[0],**changes)
        with self.assertRaises(ValueError):
            replace(self.batch.chains[0],payload_bytes=0)
        with self.assertRaises(ValueError):
            replace(self.batch,chains=(*self.batch.chains,*self.batch.chains))
        ordered = replace(self.system,engines=list(reversed(self.system.engines)),pcie_services=list(reversed(self.system.pcie_services)))
        self.assertEqual(ordered.identity_hash,self.system.identity_hash)
        self.assertNotEqual(replace(self.system,source_ref='different').identity_hash,self.system.identity_hash)


if __name__=='__main__':
    unittest.main()

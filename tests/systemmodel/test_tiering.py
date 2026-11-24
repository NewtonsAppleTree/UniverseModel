"""Independent native-line, tier-capacity and before/overlap/after migration invariants."""

from dataclasses import replace
from pathlib import Path
import json
import random
import unittest
from unittest.mock import patch

from configuration.resolution.dataclass_config import resolve_dataclass
from systemmodel.io.cxl.model import CxlAccessRequest, CxlMemorySystem, analyze_cxl_access, validate_cxl_access
from systemmodel.io.dma.model import CopyBatch, DmaSystem
from systemmodel.memory.migration import CxlCopyRequest, analyze_cxl_migration, analyze_dma_migration, validate_cxl_migration, validate_dma_migration
from systemmodel.memory.model import MemoryPlan
from systemmodel.memory.tiering import TieredMemorySystem, TierMigration, analyze_migration, analyze_residency


ROOT = Path(__file__).resolve().parents[2]  # Local synthetic declarations; expected results use separate hand/finite-set calculations.


# Models remain independently callable without the study producer or actual hardware.
class TieringTests(unittest.TestCase):
    # Each test starts with immutable professional models decoded directly from fixture data.
    def setUp(self):
        raw = json.loads((ROOT/'config/experiments/system_tiering.json').read_text(encoding='utf-8'))
        self.system = resolve_dataclass(TieredMemorySystem,raw['system'])
        self.cxl = resolve_dataclass(CxlMemorySystem,raw['cxl'])
        self.dma = resolve_dataclass(DmaSystem,raw['dma'])
        self.cases = {c['name']:c for c in raw['cases']}
        self.plan = resolve_dataclass(MemoryPlan,self.cases['expanded_residency']['placement'])
        self.request = resolve_dataclass(CxlAccessRequest,self.cases['native_read']['access'])
        self.promote = resolve_dataclass(TierMigration,self.cases['promote']['migration'])
        self.copy = resolve_dataclass(CxlCopyRequest,self.cases['promote']['cxl_copy'])

    # Fixed hardware holds 1024 useful B as 256 host + 768 CXL, while host-only placement exceeds its 512 B capacity.
    def test_capacity_and_fixed_demand(self):
        result = analyze_residency(self.system,self.plan,1)
        usage = {t.tier_id:t for t in result.tiers}
        self.assertEqual((usage['host_local'].capacity_bytes,usage['host_local'].reserved_bytes),(512,256))
        self.assertEqual((usage['cxl_expansion'].capacity_bytes,usage['cxl_expansion'].reserved_bytes),(4096,768))
        self.assertEqual(sum(t.reserved_bytes for t in result.tiers),1024)
        local = resolve_dataclass(MemoryPlan,self.cases['local_capacity_failed']['placement'])
        self.assertEqual(local.objects,self.plan.objects)
        with self.assertRaisesRegex(ValueError,'capacity'):
            analyze_residency(self.system,local,1)

    # All tiers report the same queried logical phase; ended allocations free simultaneous occupancy without changing capacity.
    def test_liveness_and_partition(self):
        after = analyze_residency(self.system,self.plan,3)
        self.assertTrue(all(t.reserved_bytes==0 and not t.allocation_ids for t in after.tiers))
        self.assertEqual(sum(t.capacity_bytes for t in after.tiers),6656)
        first = self.system.tiers[0]
        for tiers in (self.system.tiers[:-1],(*self.system.tiers,first),tuple(replace(t,backing_ids=(*t.backing_ids,'missing')) if t==first else t for t in self.system.tiers)):
            with self.assertRaises(ValueError):
                replace(self.system,tiers=tiers)

    # The proposed move duplicates 256 B during copy, then retires only the source; no snapshot is mutated.
    def test_transition_hand_and_purity(self):
        original = self.promote.identity_hash
        result = analyze_migration(self.system,self.promote,1)
        totals = tuple(sum(t.reserved_bytes for t in stage.tiers) for stage in (result.before,result.during,result.after))
        self.assertEqual(totals,(1024,1280,1024))
        self.assertEqual((result.payload_bytes,result.additional_reserved_bytes),(256,256))
        self.assertEqual((result.source_tier_id,result.target_tier_id),('cxl_expansion','host_local'))
        self.assertEqual(self.promote.identity_hash,original)

    # A copy retains two physical versions; a move retires one. Demotion releases host bytes only in the proposed after state.
    def test_copy_and_demotion_accounting(self):
        for name,host,far,total in (('replicate',512,768,1280),('demote',0,1024,1024)):
            migration = resolve_dataclass(TierMigration,self.cases[name]['migration'])
            result = analyze_migration(self.system,migration,1)
            after = {t.tier_id:t.reserved_bytes for t in result.after.tiers}
            self.assertEqual((after['host_local'],after['cxl_expansion'],sum(after.values())),(host,far,total))

    # Before/after can each fit while copying into the still-live source slot fails the mandatory overlap snapshot.
    def test_transient_headroom(self):
        bad = resolve_dataclass(TierMigration,self.cases['reuse_source_too_early']['migration'])
        analyze_residency(self.system,bad.before,1)
        analyze_residency(self.system,bad.after,1)
        with self.assertRaisesRegex(ValueError,'overlapping live'):
            analyze_migration(self.system,bad,1)
        retired = replace(self.promote,during=self.promote.after)
        with self.assertRaisesRegex(ValueError,'retain all prior'):
            analyze_migration(self.system,retired,1)

    # Unrelated view edits, source retention after a move, changed objects and stale bindings invalidate a transition.
    def test_transition_roster_guards(self):
        changed_view = replace(self.promote.after,regions=tuple(replace(r,base_address=r.base_address+2048) if r.region_id=='hot' else r for r in self.promote.after.regions))
        cases = (replace(self.promote,after=self.promote.during),replace(self.promote,after=changed_view),
                 replace(self.promote,after=replace(self.promote.after,objects=tuple(replace(o,source_ref='changed') if o.object_id=='hot' else o for o in self.promote.after.objects))),
                 replace(self.promote,during=replace(self.promote.during,memory_identity='0'*64)))
        for migration in cases:
            with self.assertRaises(ValueError):
                analyze_migration(self.system,migration,1)

    # Native data is counted by memory lines; a one-byte read returns one 64 B quantum with 63 B extra data.
    def test_native_line_counts(self):
        result = analyze_cxl_access(self.cxl,self.plan,self.request)
        self.assertEqual((result.line_count,result.data_bytes,result.extra_data_bytes),(4,256,0))
        partial = resolve_dataclass(CxlAccessRequest,self.cases['partial_read_1B']['access'])
        result = analyze_cxl_access(self.cxl,self.plan,partial)
        self.assertEqual((result.line_count,result.data_bytes,result.extra_data_bytes),(1,64,63))
        self.assertTrue(any('coherence' in text for text in result.unknown_costs))

    # Independent byte-to-line sets validate 100 fixed-seed legal read intervals, including first/last-line edges.
    def test_read_lines_against_byte_oracle(self):
        rng = random.Random(44019)
        for trial in range(100):
            offset = rng.randrange(256)
            length = rng.randrange(1,257-offset)
            expected = len({address//64 for address in range(65536+offset,65536+offset+length)})
            request = replace(self.request,access=replace(self.request.access,address=65536+offset,length_bytes=length))
            actual = analyze_cxl_access(self.cxl,self.plan,request)
            with self.subTest(trial=trial):
                self.assertEqual(actual.line_count,expected)
                self.assertEqual(actual.data_bytes,length+actual.extra_data_bytes)

    # A type-3 label alone and CXL.io/cache queries cannot grant host memory semantics.
    def test_enabled_modes_and_device_types(self):
        attachment = self.cxl.attachments[0]
        disabled = replace(self.cxl,attachments=(replace(attachment,enabled_protocols=('io',)),))
        with self.assertRaisesRegex(ValueError,'enabled CXL.mem'):
            analyze_cxl_access(disabled,self.plan,self.request)
        type2 = replace(self.cxl,attachments=(replace(attachment,device_type='type2',enabled_protocols=('io','cache','mem')),))
        analyze_cxl_access(type2,self.plan,self.request)
        for protocol in ('io','cache'):
            with self.assertRaises(ValueError):
                analyze_cxl_access(type2,self.plan,replace(self.request,protocol=protocol))
        for changes in ({'device_type':'type1'},{'enabled_protocols':('io','cache','mem')},{'enabled_protocols':('mem',)}):
            with self.assertRaises(ValueError):
                replace(attachment,**changes)
        type1 = replace(attachment,device_type='type1',enabled_protocols=('io','cache'))
        with self.assertRaisesRegex(ValueError,'memory-capable'):
            replace(self.cxl,attachments=(type1,))

    # Flat apertures preserve unique host addresses and physical ranges; neither another view nor window adds storage.
    def test_window_ownership_alignment_and_overlap(self):
        window = self.cxl.windows[0]
        for changes in ({'backing_id':'host.mem'},{'base_address':65537},{'length_bytes':8192},{'backing_offset_bytes':64}):
            with self.assertRaises(ValueError):
                replace(self.cxl,windows=(replace(window,**changes),))
        first = replace(window,length_bytes=1024)
        second = replace(window,window_id='second',base_address=67584,backing_offset_bytes=1024,length_bytes=1024)
        replace(self.cxl,windows=(first,second))
        for changed in (replace(second,base_address=65536),replace(second,backing_offset_bytes=0)):
            with self.assertRaisesRegex(ValueError,'overlapping'):
                replace(self.cxl,windows=(first,changed))

    # A legal S2 view still must match the explicit CXL decoder, host terminal and host-local aperture reservation.
    def test_decoder_and_host_namespace(self):
        plan = resolve_dataclass(MemoryPlan,self.cases['decoder_mismatch']['placement'])
        request = resolve_dataclass(CxlAccessRequest,self.cases['decoder_mismatch']['access'])
        with self.assertRaisesRegex(ValueError,'decoder mapping'):
            analyze_cxl_access(self.cxl,plan,request)
        wrong_host = replace(self.request,access=replace(self.request.access,source_port_id='host.out'))
        with self.assertRaisesRegex(ValueError,'host/address'):
            analyze_cxl_access(self.cxl,self.plan,wrong_host)
        collision = replace(self.plan,regions=tuple(replace(r,base_address=65536) if r.region_id=='hot' else r for r in self.plan.regions))
        analyze_residency(self.system,collision,1)
        with self.assertRaisesRegex(ValueError,'host-local address'):
            analyze_cxl_access(self.cxl,collision,self.request)

    # Full-line writes are modeled explicitly; masked writes, out-of-window requests and expired views fail.
    def test_write_range_and_lifetime(self):
        write = replace(self.request,access=replace(self.request.access,operation='write'))
        self.assertEqual(analyze_cxl_access(self.cxl,self.plan,write).data_bytes,256)
        for changes in ({'address':65537,'length_bytes':64},{'length_bytes':63},{'phase':3},{'address':69632}):
            with self.assertRaises(ValueError):
                analyze_cxl_access(self.cxl,self.plan,replace(write,access=replace(write.access,**changes)))

    # Native migrations retain line evidence and unknown service; no DMA TLP framing or zero latency is fabricated.
    def test_native_migration_and_replay(self):
        result = analyze_cxl_migration(self.system,self.promote,1,self.cxl,self.copy)
        self.assertEqual((result.method,result.transport_data_bytes),('host-cxl.mem',256))
        self.assertIsNone(result.known_service_lower_bound_s)
        self.assertIsNone(result.dma)
        self.assertEqual(result.local_span.allocation_id,'cold.new')
        with patch('systemmodel.memory.access.find_path',side_effect=AssertionError('searched')):
            self.assertEqual(result,validate_cxl_migration(self.system,self.promote,1,self.cxl,self.copy,result.cxl_access.access.path))
            self.assertEqual(result.cxl_access,validate_cxl_access(self.cxl,self.promote.during,self.copy.request,result.cxl_access.access.path))

    # A wrong object, partial extent or different logical phase cannot bind to the intended full-object transition.
    def test_native_transport_binding(self):
        wrong = resolve_dataclass(CxlCopyRequest,self.cases['wrong_copy_object']['cxl_copy'])
        for copy in (wrong,replace(self.copy,request=replace(self.request,access=replace(self.request.access,length_bytes=128))),
                     replace(self.copy,request=replace(self.request,access=replace(self.request.access,phase=2)))):
            with self.assertRaises(ValueError):
                analyze_cxl_migration(self.system,self.promote,1,self.cxl,copy)
        policies = tuple(replace(t,access_kind='dma_only') if t.tier_id=='host_local' else t for t in self.system.tiers)
        with self.assertRaisesRegex(ValueError,'host-local tiers'):
            analyze_cxl_migration(replace(self.system,tiers=policies),self.promote,1,self.cxl,self.copy)

    # Compatible host-to-device migration reuses the S3 byte/route ledger and its partial 256 ns service bound.
    def test_dma_migration_and_replay(self):
        case = self.cases['dma_to_accelerator']
        migration = resolve_dataclass(TierMigration,case['migration'])
        batch = resolve_dataclass(CopyBatch,case['dma_copy'])
        result = analyze_dma_migration(self.system,migration,1,self.dma,batch)
        self.assertEqual((result.method,result.transport_data_bytes),('dma',256))
        self.assertAlmostEqual(result.known_service_lower_bound_s,256e-9)
        self.assertIsNone(result.cxl_access)
        with patch('systemmodel.io.dma.analysis.find_path',side_effect=AssertionError('searched')):
            self.assertEqual(result,validate_dma_migration(self.system,migration,1,self.dma,batch,tuple(l.path for l in result.dma.legs)))
        with self.assertRaises(ValueError):
            analyze_dma_migration(self.system,migration,1,self.dma,replace(batch,phase=2))
        policies = tuple(replace(t,access_kind='cxl.mem') if t.tier_id=='host_local' else t for t in self.system.tiers)
        with self.assertRaisesRegex(ValueError,'cannot stand in'):
            analyze_dma_migration(replace(self.system,tiers=policies),migration,1,self.dma,batch)

    # Removing an explicit CXL wire removes reachability even though type, mode, capacity and decoder remain valid.
    def test_path_is_separate_from_capability(self):
        topology = self.system.memory.node.topology
        topology = replace(topology,links=tuple(l for l in topology.links if l.link_id!='host_cxl0'))
        memory = replace(self.system.memory,node=replace(self.system.memory.node,topology=topology))
        cxl = replace(self.cxl,memory=memory)
        plan = replace(self.plan,memory_identity=memory.identity_hash)
        with self.assertRaisesRegex(ValueError,'no admissible path'):
            analyze_cxl_access(cxl,plan,self.request)

    # Exact scalar validation and source-bound identity prevent silent hardware/phase rebinding.
    def test_scalars_and_identity(self):
        for changes in ({'line_bytes':0},{'line_bytes':3},{'decoder_granule_bytes':65},{'line_bytes':True}):
            with self.assertRaises((TypeError,ValueError)):
                replace(self.cxl.profile,**changes)
        with self.assertRaises(TypeError):
            analyze_residency(self.system,self.plan,True)
        self.assertEqual(replace(self.system,tiers=list(reversed(self.system.tiers))).identity_hash,self.system.identity_hash)
        self.assertNotEqual(replace(self.cxl,source_ref='different').identity_hash,self.cxl.identity_hash)
        changed = replace(self.system,memory=replace(self.system.memory,source_ref='new-hardware'))
        with self.assertRaisesRegex(ValueError,'stale'):
            analyze_residency(changed,self.plan,1)


if __name__=='__main__':
    unittest.main()

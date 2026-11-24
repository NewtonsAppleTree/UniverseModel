"""Independent finite-byte/lifetime oracles and adversarial static memory/NUMA invariants."""

from dataclasses import replace
from pathlib import Path
import json
import random
import unittest

from configuration.resolution.dataclass_config import resolve_dataclass
from systemmodel.memory.access import MemoryAccessRequest, analyze_access, resolve_span, validate_access
from systemmodel.memory.model import MemoryAllocation, MemoryBacking, MemoryObject, MemoryPlan, MemoryRegion, MemorySystem, NumaDomain
from systemmodel.memory.placement import analyze_placement


ROOT = Path(__file__).resolve().parents[2]  # Repository fixture data, independent of experiment execution.


# Load only professional memory/plan types; expectations come from explicit hand checks and separate tiny oracles.
class MemoryTests(unittest.TestCase):
    # Each test uses immutable declarations; altered cases replace values without sharing mutable model state.
    def setUp(self):
        raw = json.loads((ROOT/'config/experiments/system_memory.json').read_text(encoding='utf-8'))
        self.memory = resolve_dataclass(MemorySystem,raw['memory'])
        self.cases = {c['name']:c for c in raw['cases']}
        self.plan = resolve_dataclass(MemoryPlan,self.cases['local']['plan'])
        self.request = resolve_dataclass(MemoryAccessRequest,self.cases['local']['request'])

    # Fixture peak: ceil(160/64)*64 + ceil(96/64)*64 = 320 B, logical 256 B and padding 64 B.
    def test_hand_capacity(self):
        first,second = analyze_placement(self.memory,self.plan).backings
        self.assertEqual((first.peak_reserved_bytes,first.logical_bytes_at_peak,first.padding_bytes_at_peak,first.peak_phase),(320,256,64,1))
        self.assertEqual(first.allocation_ids_at_peak,('activation.copy','weights.copy'))
        self.assertEqual((second.peak_reserved_bytes,second.peak_phase,second.allocation_ids_at_peak),(0,None,()))
        self.assertEqual(first.capacity_bytes-first.peak_reserved_bytes,704)

    # Extra address aliases do not reserve bytes; a second physical copy of the same object does.
    def test_alias_and_replica_accounting(self):
        for case,peak in (('alias',320),('replicated_copy',512),('lifetime_reuse',320)):
            plan = resolve_dataclass(MemoryPlan,self.cases[case]['plan'])
            usage = analyze_placement(self.memory,plan).backings[0]
            self.assertEqual(usage.peak_reserved_bytes,peak,case)

    # End phase equals next begin phase safely reuses both physical and domain addresses; one phase earlier collides.
    def test_lifetime_boundary_reuse(self):
        plan = resolve_dataclass(MemoryPlan,self.cases['lifetime_reuse']['plan'])
        analyze_placement(self.memory,plan)
        overlap = replace(plan,allocations=tuple(replace(a,begin_phase=2) if a.allocation_id=='weights.later' else a for a in plan.allocations))
        with self.assertRaisesRegex(ValueError,'physical backing'):
            analyze_placement(self.memory,overlap)
        with self.assertRaisesRegex(ValueError,'lifetime'):
            resolve_span(self.memory,self.plan,replace(self.request,phase=3))
        resolve_span(self.memory,self.plan,replace(self.request,phase=0))

    # A view's logical offset and queried address delta both contribute to its physical location.
    def test_subrange_resolution_and_padding(self):
        region = next(r for r in self.plan.regions if r.region_id=='weights.view')
        view = replace(region,object_offset_bytes=32,length_bytes=64)
        plan = replace(self.plan,regions=(view,))
        span = resolve_span(self.memory,plan,replace(self.request,address=4112,length_bytes=48))
        self.assertEqual((span.physical_offset_bytes,span.length_bytes),(48,48))
        for address,length in ((4095,1),(4112,49),(4160,1)):
            with self.assertRaisesRegex(ValueError,'span'):
                resolve_span(self.memory,plan,replace(self.request,address=address,length_bytes=length))
        with self.assertRaisesRegex(ValueError,'padding'):
            analyze_placement(self.memory,replace(plan,regions=(replace(view,object_offset_bytes=128),)))

    # Capacity can be valid while aliases collide in one namespace; different domains can use equal addresses.
    def test_address_namespace_and_overlap(self):
        plan = resolve_dataclass(MemoryPlan,self.cases['remote']['plan'])
        plan = replace(plan,regions=tuple(replace(r,base_address=4096) for r in plan.regions))
        analyze_placement(self.memory,plan)
        collision = replace(self.plan,regions=tuple(replace(r,base_address=4096) for r in self.plan.regions))
        with self.assertRaisesRegex(ValueError,'address domain'):
            analyze_placement(self.memory,collision)
        alias = replace(self.plan.regions[0],region_id='overlapping.alias')
        with self.assertRaisesRegex(ValueError,'address domain'):
            analyze_placement(self.memory,replace(self.plan,regions=(*self.plan.regions,alias)))

    # The final byte of a 32-bit address space is valid; the first byte beyond it is not physical capacity.
    def test_address_width_boundary(self):
        region = replace(self.plan.regions[0],base_address=(1<<32)-1,length_bytes=1)
        analyze_placement(self.memory,replace(self.plan,regions=(region,)))
        with self.assertRaises(ValueError):
            analyze_placement(self.memory,replace(self.plan,regions=(replace(region,length_bytes=2),)))

    # Rounded extents, physical intersections and region permissions are separate negative controls.
    def test_fixture_failures(self):
        for case in self.cases.values():
            if case['expected_status']=='failed':
                plan = resolve_dataclass(MemoryPlan,case['plan'])
                request = resolve_dataclass(MemoryAccessRequest,case['request'])
                with self.subTest(case=case['name']),self.assertRaises(ValueError):
                    analyze_access(self.memory,plan,request)

    # Equal hop counts distinguish local/remote placement; neither carries a target time or energy field.
    def test_numa_and_request_path(self):
        local = analyze_access(self.memory,self.plan,self.request)
        remote_plan = resolve_dataclass(MemoryPlan,self.cases['remote']['plan'])
        remote = analyze_access(self.memory,remote_plan,self.request)
        self.assertEqual((local.locality,remote.locality),('local','remote'))
        self.assertEqual((local.initiator_numa_id,remote.backing_numa_id),('numa0','numa1'))
        self.assertEqual(len(local.path.link_ids),len(remote.path.link_ids))
        self.assertEqual(local,validate_access(self.memory,self.plan,self.request,local.path.link_ids))
        self.assertEqual(remote.path.link_ids,('cpu0_fabric','fabric_mc1'))
        with self.assertRaises(ValueError):
            validate_access(self.memory,self.plan,self.request,remote.path.link_ids)

    # Removing exact membership yields unknown locality; controller membership does not place descendant storage.
    def test_unknown_locality_no_inheritance(self):
        memory = replace(self.memory,numa_domains=(NumaDomain(numa_id='controller',member_ids=('cpu0','mc0'),source_ref='test'),))
        plan = replace(self.plan,memory_identity=memory.identity_hash)
        result = analyze_access(memory,plan,self.request)
        self.assertEqual((result.locality,result.initiator_numa_id,result.backing_numa_id),('unknown','controller',None))

    # Legal address resolution makes no connectivity assertion; a missing initiator is rejected by access analysis.
    def test_resolution_separate_from_access(self):
        request = replace(self.request,source_port_id='missing')
        self.assertEqual(resolve_span(self.memory,self.plan,request).backing_id,'dram0')
        with self.assertRaises(ValueError):
            analyze_access(self.memory,self.plan,request)
        with self.assertRaises(ValueError):
            analyze_access(self.memory,self.plan,replace(self.request,max_hops=1))

    # Duplicated/missing ownership, foreign attachment and summary-plus-child capacity cannot pass inventory validation.
    def test_backing_and_numa_ownership(self):
        backing = self.memory.backings[0]
        for backings in ((backing,backing),(replace(backing,resource_id='missing'),),(replace(backing,access_port_ids=('mc1.in',)),),
                         (replace(backing,access_port_ids=('cpu0.out',)),),(backing,replace(backing,resource_id='mc0'))):
            with self.subTest(backings=backings),self.assertRaises(ValueError):
                replace(self.memory,backings=backings)
        for member in ('cpu0','missing'):
            with self.assertRaises(ValueError):
                replace(self.memory,numa_domains=(*self.memory.numa_domains,NumaDomain(numa_id='extra',member_ids=(member,),source_ref='test')))

    # All declared demands must be allocated, while unmapped allocations and an explicitly empty workload are legal.
    def test_reference_completeness_and_empty_plan(self):
        empty = replace(self.plan,objects=(),allocations=(),regions=())
        self.assertTrue(all(b.peak_reserved_bytes==0 for b in analyze_placement(self.memory,empty).backings))
        analyze_placement(self.memory,replace(self.plan,regions=()))
        for field,missing in (('objects',()),('allocations',()),('regions',(replace(self.plan.regions[0],allocation_id='missing'),))):
            with self.subTest(field=field),self.assertRaises(ValueError):
                analyze_placement(self.memory,replace(self.plan,**{field:missing}))
        with self.assertRaises(ValueError):
            analyze_placement(self.memory,replace(self.plan,allocations=(replace(self.plan.allocations[0],backing_id='missing'),)))

    # Scalar counts reject bool/floats, invalid granules, empty lifetimes and unsupported permissions.
    def test_scalar_validation(self):
        invalid = ((self.memory.backings[0],{'capacity_bytes':True}),(self.memory.backings[0],{'capacity_bytes':1000}),
                   (self.memory.backings[0],{'allocation_granule_bytes':0}),(self.plan.objects[0],{'size_bytes':0}),
                   (self.plan.allocations[0],{'end_phase':0}),(self.plan.allocations[0],{'offset_bytes':-1}),
                   (self.plan.regions[0],{'permissions':('copy',)}),(self.plan.regions[0],{'permissions':()}),
                   (self.request,{'length_bytes':0}),(self.request,{'phase':1.0}),(self.request,{'operation':'copy'}))
        for value,changes in invalid:
            with self.subTest(changes=changes),self.assertRaises((TypeError,ValueError)):
                replace(value,**changes)
        with self.assertRaisesRegex(ValueError,'alignment'):
            analyze_placement(self.memory,replace(self.plan,allocations=tuple(replace(a,offset_bytes=a.offset_bytes+1) for a in self.plan.allocations)))

    # A view cannot gain write capability from its name or from a different path's permissions.
    def test_ingress_permission(self):
        ports = tuple(replace(p,operations=('read',)) if p.port_id=='mc0.in' else p for p in self.memory.node.topology.ports)
        links = tuple(replace(l,operations=('read',)) if l.link_id=='fabric_mc0' else l for l in self.memory.node.topology.links)
        topology = replace(self.memory.node.topology,ports=ports,links=links)
        memory = replace(self.memory,node=replace(self.memory.node,topology=topology))
        with self.assertRaisesRegex(ValueError,'ingress capability'):
            analyze_placement(memory,replace(self.plan,memory_identity=memory.identity_hash))

    # Reordering declarations is identity-neutral; caller arrays are frozen and provenance changes invalidate a plan.
    def test_identity_and_immutability(self):
        memory = replace(self.memory,backings=list(reversed(self.memory.backings)),numa_domains=list(reversed(self.memory.numa_domains)))
        self.assertEqual(memory.identity_hash,self.memory.identity_hash)
        objects = list(self.plan.objects)
        plan = replace(self.plan,objects=objects,allocations=tuple(reversed(self.plan.allocations)))
        objects.clear()
        self.assertEqual(plan.identity_hash,self.plan.identity_hash)
        with self.assertRaisesRegex(ValueError,'stale'):
            analyze_placement(replace(memory,source_ref='changed'),plan)
        with self.assertRaises(ValueError):
            replace(plan,regions=(*plan.regions,plan.regions[0]))

    # Large sparse byte/phase values use exact integers and events, without iteration across address or phase space.
    def test_sparse_large_intervals_and_peak_tie(self):
        w = next(a for a in self.plan.allocations if a.object_id=='weights')
        obj = next(o for o in self.plan.objects if o.object_id=='weights')
        plan = replace(self.plan,objects=(obj,),allocations=(replace(w,begin_phase=10**18,end_phase=10**18+1),
                      replace(w,allocation_id='later',begin_phase=10**20,end_phase=10**20+1)),regions=())
        usage = analyze_placement(self.memory,plan).backings[0]
        self.assertEqual((usage.peak_phase,usage.peak_reserved_bytes),(10**18,192))
        self.assertEqual(usage.allocation_ids_at_peak,('weights.copy',))

    # Two disjoint backing peaks at different phases stay separate instead of producing a fictitious node peak.
    def test_independent_backing_peaks(self):
        plan = replace(self.plan,regions=(),allocations=tuple(replace(a,backing_id='dram1',begin_phase=4,end_phase=6) if a.object_id=='weights' else a for a in self.plan.allocations))
        usages = analyze_placement(self.memory,plan).backings
        self.assertEqual(tuple((b.peak_reserved_bytes,b.peak_phase) for b in usages),((128,1),(192,4)))

    # Independently enumerate occupied bytes/phases for 120 seeded tiny physical plans, including collisions and ties.
    def test_physical_sweep_against_byte_oracle(self):
        rng = random.Random(72931)
        memory = replace(self.memory,backings=(replace(self.memory.backings[0],capacity_bytes=32,allocation_granule_bytes=4),))
        for trial in range(120):
            objects,allocations = [],[]
            for i in range(rng.randint(0,7)):
                objects.append(MemoryObject(object_id=f'o{i}',size_bytes=rng.randint(1,7),source_ref='tiny-oracle'))
                begin = rng.randrange(5)
                allocations.append(MemoryAllocation(allocation_id=f'a{i}',object_id=f'o{i}',backing_id='dram0',offset_bytes=rng.randrange(8)*4,begin_phase=begin,end_phase=rng.randint(begin+1,6)))
            plan = MemoryPlan(memory_identity=memory.identity_hash,objects=objects,allocations=allocations,regions=(),source_ref='tiny-oracle')
            invalid,peak,peak_phase,logical,ids = False,0,None,0,()
            for phase in range(6):
                occupied,current_demand,current_ids = set(),0,[]
                for obj,a in zip(objects,allocations):
                    if a.begin_phase<=phase<a.end_phase:
                        # Independent byte-set oracle rounds by adding bytes until divisibility, not the producer's formula.
                        extent = obj.size_bytes
                        while extent%4:
                            extent += 1
                        cells = set(range(a.offset_bytes,a.offset_bytes+extent))
                        invalid |= bool(cells & occupied) or max(cells)>=32
                        occupied |= cells
                        current_demand += obj.size_bytes
                        current_ids.append(a.allocation_id)
                if len(occupied)>peak:
                    peak,peak_phase,logical,ids = len(occupied),phase,current_demand,tuple(sorted(current_ids))
            with self.subTest(trial=trial):
                if invalid:
                    with self.assertRaises(ValueError):
                        analyze_placement(memory,plan)
                else:
                    usage = analyze_placement(memory,plan).backings[0]
                    self.assertEqual((usage.peak_reserved_bytes,usage.peak_phase,usage.logical_bytes_at_peak,usage.allocation_ids_at_peak),(peak,peak_phase,logical,ids))

    # A separate byte-set oracle checks domain overlap using 80 random mappings with disjoint physical offsets.
    def test_address_sweep_against_byte_oracle(self):
        rng = random.Random(195)
        obj = MemoryObject(object_id='o',size_bytes=8,source_ref='tiny-oracle')
        for trial in range(80):
            allocations,regions = [],[]
            for i in range(4):
                begin = rng.randrange(4)
                allocations.append(MemoryAllocation(allocation_id=f'a{i}',object_id='o',backing_id='dram0',offset_bytes=64*i,begin_phase=begin,end_phase=rng.randint(begin+1,5)))
                regions.append(MemoryRegion(region_id=f'r{i}',allocation_id=f'a{i}',access_port_id='mc0.in',base_address=rng.randrange(24),object_offset_bytes=0,length_bytes=8,permissions=('read',)))
            invalid = False
            for phase in range(5):
                seen = set()
                for a,r in zip(allocations,regions):
                    if a.begin_phase<=phase<a.end_phase:
                        cells = set(range(r.base_address,r.base_address+8))
                        invalid |= bool(seen & cells)
                        seen |= cells
            plan = MemoryPlan(memory_identity=self.memory.identity_hash,objects=(obj,),allocations=allocations,regions=regions,source_ref='tiny-oracle')
            with self.subTest(trial=trial):
                if invalid:
                    with self.assertRaisesRegex(ValueError,'address domain'):
                        analyze_placement(self.memory,plan)
                else:
                    analyze_placement(self.memory,plan)


if __name__=='__main__':
    unittest.main()

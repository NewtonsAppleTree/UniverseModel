"""NIC buffer/registration/service ownership tests with independent shared-work hand checks."""

from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

from configuration.resolution.dataclass_config import load_config
from evaluation.experiments.runner.system_network import NetworkStudy, analyze_network
from systemmodel.io.nic.model import analyze_nic


ROOT = Path(__file__).resolve().parents[2]  # Reviewed synthetic node fixture, not measured NIC hardware.


# Verify professional NIC calls independently of immutable experiment production.
class NicTests(unittest.TestCase):
    # Decode the actual sourced common hardware once; all replacements remain immutable.
    @classmethod
    def setUpClass(cls):
        cls.study=load_config(NetworkStudy,ROOT/'config/experiments/system_network.json')
        cls.cases={c.name:c for c in cls.study.cases}
        cls.system=cls.study.systems[0]
        cls.batch=cls.cases['single'].nodes[0].nic

    # A 512 B supply writes two conventional TLPs on two wires, and charges one 1 GB/s root once.
    def test_supply_hand_ledger(self):
        result=analyze_nic(self.system,self.batch)
        self.assertEqual(sum(l.traffic.frame_bytes*len(l.path.link_ids) for l in result.dma.legs),1120)
        work={c.resource_id:c.amount for c in result.dma.contributions}
        self.assertEqual(work['n0.root_bus'],512)
        self.assertAlmostEqual(result.dma.bounds.lower_bound_s,512e-9)
        self.assertFalse(set(work)&{c.resource_id for c in self.system.constraints})
        self.assertEqual((result.flows[0].object_id,result.flows[0].content_version,result.flows[0].payload_bytes),('data0','input:v1',512))

    # Two independent host/device sources share one root and NIC; no rank multiplication of capacity is allowed.
    def test_shared_node_and_nic(self):
        result=analyze_network(self.study,self.cases['shared_nic'])
        self.assertEqual(result['logical_payload_bytes'],1024)
        loads={r.resource_id:r for r in result['fabric'].resources}
        self.assertEqual((loads['n0.nic.tx_limit'].service_bytes,loads['n0.nic.tx_limit'].capacity_Bps),(1024,2e9))
        self.assertAlmostEqual(result['local_lower_bound_s'],1024e-9)
        self.assertAlmostEqual(result['known_service_lower_bound_s'],1024e-9)

    # Drain writes application memory from an actual receive buffer; remote receipt alone does not publish memory.
    def test_receive_buffer(self):
        result=analyze_nic(self.study.systems[1],self.cases['single'].nodes[1].nic)
        flow=result.flows[0]
        self.assertEqual((flow.direction,flow.application_allocation_id,flow.buffer_allocation_id),('rx','app0','buffer0'))
        self.assertTrue(any('publication' in text for text in result.unknown_costs))

    # Ordinary sends cannot silently acquire remote-write permission; valid registered RDMA still has unknown completion.
    def test_explicit_rdma_capability(self):
        rdma=self.cases['rdma_write'].nodes[0].nic
        analyze_nic(self.system,rdma)
        disabled=replace(self.system,ports=(replace(self.system.ports[0],rdma_write_enabled=False),))
        with self.assertRaisesRegex(ValueError,'capability'):
            analyze_nic(disabled,rdma)
        bad=replace(self.batch,flows=(replace(self.batch.flows[0],registration_id='invented'),))
        with self.assertRaises(ValueError):
            analyze_nic(self.system,bad)

    # Exact physical allocation, subrange, phase and direction authority are independently necessary.
    def test_registration_guards(self):
        rdma=self.cases['rdma_write'].nodes[0].nic
        grant=rdma.registrations[0]
        for changes in ({'allocation_id':'buffer0'},{'offset_bytes':1},{'length_bytes':511},{'end_phase':1},{'operations':('write',)}, {'end_phase':4}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                analyze_nic(self.system,replace(rdma,registrations=(replace(grant,**changes),)))

    # Buffer ownership, finite lifetime and useful-byte capacity cannot be granted by a NIC label.
    def test_buffer_and_lifetime_guards(self):
        with self.assertRaises(ValueError):
            replace(self.system,ports=(replace(self.system.ports[0],buffer_backing_ids=('n0.host.mem',)),))
        with self.assertRaises(ValueError):
            analyze_nic(self.system,replace(self.batch,copies=replace(self.batch.copies,phase=3)))
        with self.assertRaises(ValueError):
            analyze_network(self.study,self.cases['buffer_capacity'])

    # Same-size different content identities and offsets cannot be substituted for the promised application data.
    def test_content_binding(self):
        plan=self.batch.copies.placement
        obj=replace(plan.objects[0],object_id='different')
        plan=replace(plan,objects=(*plan.objects,obj),allocations=tuple(replace(a,object_id='different') if a.allocation_id=='buffer0' else a for a in plan.allocations))
        with self.assertRaisesRegex(ValueError,'exact application data'):
            analyze_nic(self.system,replace(self.batch,copies=replace(self.batch.copies,placement=plan)))

    # Existing local service cannot also be exported as NIC capacity, even with a different role name.
    def test_duplicate_budget_rejection(self):
        endpoint=self.system.ports[0].endpoint
        root=self.system.dma.memory.node.topology.constraints[0]
        endpoint=replace(endpoint,tx_constraint_ids=(root.resource_id,))
        limits=tuple(c for c in self.system.constraints if c.resource_id not in self.system.ports[0].endpoint.tx_constraint_ids)+(root,)
        with self.assertRaisesRegex(ValueError,'already charged'):
            replace(self.system,ports=(replace(self.system.ports[0],endpoint=endpoint),),constraints=limits)

    # A cluster must consume the actual node exports; a faster stale NIC snapshot is rejected.
    def test_cluster_export_identity(self):
        graph=self.study.cluster.graph
        limits=tuple(replace(c,capacity_Bps=c.capacity_Bps*2) if c.resource_id=='n0.nic.tx_limit' else c for c in graph.constraints)
        with self.assertRaisesRegex(ValueError,'authoritative'):
            replace(self.study,cluster=replace(self.study.cluster,graph=replace(graph,constraints=limits)))

    # Same-node traffic consumes DMA/root work only and never traverses or charges the external NIC/fabric.
    def test_local_path_adapter(self):
        result=analyze_network(self.study,self.cases['same_node'])
        self.assertEqual(result['local_payload_bytes'],512)
        self.assertEqual(result['fabric'].logical_payload_bytes,0)
        self.assertTrue(all(r.service_bytes==0 for r in result['fabric'].resources))
        self.assertAlmostEqual(result['known_service_lower_bound_s'],512e-9)

    # Capacity and local/fabric bounds combine by max; fabric serialization is not added to each node's full copy bound.
    def test_nic_bandwidth_sensitivity(self):
        systems=tuple(replace(s,constraints=tuple(replace(c,capacity_Bps=0.25e9) for c in s.constraints)) for s in self.study.systems)
        graph=replace(self.study.cluster.graph,constraints=tuple(c for s in systems for c in s.constraints))
        changed=replace(self.study,systems=systems,cluster=replace(self.study.cluster,graph=graph))
        result=analyze_network(changed,self.cases['shared_nic'])
        self.assertAlmostEqual(result['known_service_lower_bound_s'],4096e-9)

    # An immutable replay validates existing DMA paths without a new path search or data-copy execution.
    def test_local_replay_and_purity(self):
        identity=self.system.identity_hash
        result=analyze_nic(self.system,self.batch)
        with patch('systemmodel.io.dma.analysis.find_path',side_effect=AssertionError('searched')):
            self.assertEqual(result,analyze_nic(self.system,self.batch,saved_paths=tuple(l.path for l in result.dma.legs)))
        self.assertEqual(identity,self.system.identity_hash)

    # All eight reviewed rejection cases actually fail; no failed case is omitted from the candidate comparison.
    def test_negative_cases(self):
        failed=[c for c in self.study.cases if c.expected_status=='failed']
        self.assertEqual(len(failed),8)
        for case in failed:
            with self.subTest(case=case.name),self.assertRaises(ValueError):
                analyze_network(self.study,case)


if __name__=='__main__':
    unittest.main()

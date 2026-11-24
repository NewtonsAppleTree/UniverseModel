"""Independent ownership, permission, path and shared-capacity invariants for the node foundation."""

from dataclasses import replace
from pathlib import Path
import itertools
import json
import random
import unittest

from chipmodel.composition.graph import ResourceNode
from configuration.resolution.dataclass_config import resolve_dataclass
from contracts.hardware.system import AddressDomainSpec, SystemPortSpec
from contracts.versions.json_codec import canonical_json
from systemmodel.composition.board.model import BoardSpec
from systemmodel.composition.node.model import NodeSpec
from systemmodel.topology.graph import PortForwarding, SystemLink, SystemTopology
from systemmodel.topology.query import PathRequest, find_path, validate_path


ROOT = Path(__file__).resolve().parents[2]  # Local source fixture; no equipment or network access.


# Load just the professional node model, independently of the experiment runner and its expected outcomes.
def fixture_node():
    return resolve_dataclass(NodeSpec,json.loads((ROOT/'config/experiments/system_connectivity.json').read_text(encoding='utf-8'))['node'])


# Subtree ownership and explicit port relations are invariants, not numerical performance claims.
class NodeFoundationTests(unittest.TestCase):
    # Immutable fixture values are shared; each adversarial case builds a new topology.
    def setUp(self):
        self.node = fixture_node()
        self.topology = self.node.topology
        self.request = PathRequest(source_port_id='host.out',target_port_id='gpu0.in',operation='copy')

    # Board/card composition is independently callable and does not duplicate devices or service resources.
    def test_board_and_node_inventory(self):
        for board in self.node.boards:
            board.validate(self.topology)
        self.assertEqual(self.node.device_ids,('gpu0','gpu1','host'))
        self.assertEqual(len(self.topology.constraints),3)
        self.assertEqual(len(self.node.boards),2)
        standalone = replace(self.node,boards=(),standalone_device_ids=('host','gpu0','gpu1'))
        self.assertEqual(standalone.device_ids,self.node.device_ids)
        local = replace(self.topology,scope_id='card0',resources=tuple(replace(r,parent_id=None) if r.instance_id=='card0' else r for r in self.topology.resources if r.instance_id in ('card0','gpu0')),
                        domains=tuple(d for d in self.topology.domains if d.owner_id=='gpu0'),ports=tuple(p for p in self.topology.ports if p.owner_id=='gpu0'),links=(),forwardings=(),constraints=())
        self.node.boards[0].validate(local)

    # Canonical inventory order and copied lists keep identity stable after caller-owned arrays are edited.
    def test_canonical_identity_and_ownership(self):
        fields = ('resources','domains','ports','links','forwardings','constraints')
        shuffled = replace(self.topology,**{name:list(reversed(getattr(self.topology,name))) for name in fields})
        self.assertEqual(shuffled.identity_hash,self.topology.identity_hash)
        ports = list(self.topology.ports)
        copied = replace(self.topology,ports=ports)
        ports.clear()
        self.assertEqual(copied,self.topology)
        changed = replace(self.topology,source_ref='different:source')
        self.assertNotEqual(changed.identity_hash,self.topology.identity_hash)

    # Duplicate identities, missing parents and ownership cycles cannot be hidden by dictionary construction.
    def test_resource_graph_failures(self):
        root = next(r for r in self.topology.resources if r.instance_id=='node0')
        gpu = next(r for r in self.topology.resources if r.instance_id=='gpu0')
        cases = [(*self.topology.resources,root),
                 tuple(replace(r,parent_id='missing') if r==gpu else r for r in self.topology.resources),
                 tuple(replace(r,parent_id='gpu0') if r==root else r for r in self.topology.resources),
                 (*self.topology.resources,ResourceNode(instance_id='second-root',parent_id=None,model_id=None))]
        for resources in cases:
            with self.assertRaises(ValueError):
                replace(self.topology,resources=resources)

    # Board scopes must not overlap, and device internals cannot be presented as additional independent devices.
    def test_board_membership_failures(self):
        bad = replace(self.node.boards[0],device_ids=('gpu1',))
        with self.assertRaises(ValueError):
            bad.validate(self.topology)
        with self.assertRaises(ValueError):
            replace(self.node,standalone_device_ids=('gpu0',))
        with self.assertRaises(ValueError):
            replace(self.node,boards=(*self.node.boards,self.node.boards[0]))
        resources = (*self.topology.resources,ResourceNode(instance_id='inner',parent_id='gpu0',model_id='inner/v1'))
        with self.assertRaises(ValueError):
            replace(self.node,topology=replace(self.topology,resources=resources),boards=(replace(self.node.boards[0],device_ids=('gpu0','inner')),self.node.boards[1]))
        enclosing = BoardSpec(board_id='node0',device_ids=('host',),source_ref='manual:test')
        with self.assertRaises(ValueError):
            replace(self.node,boards=(enclosing,*self.node.boards),standalone_device_ids=())

    # Domain names distinguish spaces with equal numeric addresses; ownership mismatch never implies translation.
    def test_domain_owner_and_address_spaces(self):
        for domain in self.topology.domains:
            domain.validate_span(0,4096)
        ports = tuple(replace(p,domain_id='gpu1.address') if p.port_id=='gpu0.in' else p for p in self.topology.ports)
        with self.assertRaisesRegex(ValueError,'domain'):
            replace(self.topology,ports=ports)
        with self.assertRaisesRegex(ValueError,'owner'):
            replace(self.topology,domains=(*self.topology.domains,AddressDomainSpec(domain_id='x',owner_id='missing',address_bits=48,source_ref='test')))

    # Directed wiring checks exact protocol and attachment; a connection cannot grant unsupported operations.
    def test_link_direction_protocol_and_attachment(self):
        first = self.topology.links[0]
        for changed in (replace(first,source_port_id='missing'),replace(first,source_port_id='gpu0.in'),replace(first,operations=('read',))):
            with self.assertRaises(ValueError):
                replace(self.topology,links=(changed,*self.topology.links[1:]))
        duplicate = replace(first,link_id='extra')
        with self.assertRaisesRegex(ValueError,'attached'):
            replace(self.topology,links=(*self.topology.links,duplicate))
        ports = tuple(replace(p,protocol='other/v1') if p.port_id=='host.out' else p for p in self.topology.ports)
        with self.assertRaisesRegex(ValueError,'protocol'):
            replace(self.topology,ports=ports)

    # Shared references must resolve to the original ownership tree and cannot duplicate a summary and its internals.
    def test_shared_resource_validation(self):
        limits = self.topology.constraints
        with self.assertRaises(ValueError):
            replace(self.topology,constraints=(*limits,limits[0]))
        with self.assertRaises(ValueError):
            replace(self.topology,constraints=(replace(limits[0],owner_id='card0'),*limits[1:]))
        link = next(link for link in self.topology.links if link.link_id=='host_to_rc')
        for refs in (('missing',),('gpu0',)):
            with self.assertRaises(ValueError):
                replace(self.topology,links=tuple(replace(x,constraint_ids=refs) if x==link else x for x in self.topology.links))
        ports = tuple(replace(p,constraint_ids=('host_bus',)) if p.port_id=='host.out' else p for p in self.topology.ports)
        with self.assertRaisesRegex(ValueError,'charged'):
            replace(self.topology,ports=ports)
        child = ResourceNode(instance_id='host_bus.internal',parent_id='host_bus',model_id='detail/v1')
        with self.assertRaisesRegex(ValueError,'overlap'):
            replace(self.topology,resources=(*self.topology.resources,child),constraints=(*limits,replace(limits[0],resource_id=child.instance_id,owner_id='host_bus')))

    # Two device routes reference one host uplink rather than manufacturing an uplink per card.
    def test_shared_uplink_is_one_reference(self):
        a = find_path(self.topology,self.request)
        b = find_path(self.topology,replace(self.request,target_port_id='gpu1.in'))
        self.assertEqual(a.link_ids,('host_to_rc','rc_to_gpu0'))
        self.assertEqual(a.forwarding_ids,('host_via_rc_to_gpu0',))
        self.assertEqual(a.constraint_visits,('host_bus','gpu0_bus'))
        self.assertEqual(b.constraint_visits,('host_bus','gpu1_bus'))
        self.assertEqual(set(a.constraint_ids)&set(b.constraint_ids),{'host_bus'})
        self.assertEqual(next(c.capacity_Bps for c in self.topology.constraints if c.resource_id=='host_bus'),16e9)

    # A forward P2P permission does not authorize the reverse direction or remote load/store access.
    def test_directional_permission_and_no_implicit_staging(self):
        peer = PathRequest(source_port_id='gpu0.out',target_port_id='gpu1.in',operation='copy')
        self.assertEqual(find_path(self.topology,peer).link_ids,('gpu0_to_rc','rc_to_gpu1'))
        with self.assertRaisesRegex(ValueError,'no admissible'):
            find_path(self.topology,replace(peer,source_port_id='gpu1.out',target_port_id='gpu0.in'))
        with self.assertRaisesRegex(ValueError,'denied'):
            find_path(self.topology,replace(self.request,operation='read'))
        without = replace(self.topology,forwardings=())
        with self.assertRaises(ValueError):
            find_path(without,self.request)

    # A terminal owning two ports is still not a forwarding device; internal port pairs must be unique and same-owner.
    def test_forwarding_guards(self):
        original = self.topology.forwardings[0]
        variants = (replace(original,ingress_port_id='host.in',egress_port_id='host.out'),
                    replace(original,egress_port_id='gpu0.out'),replace(original,operations=('read',)),
                    replace(original,forwarding_id='duplicate-pair'))
        for changed in variants:
            with self.assertRaises(ValueError):
                replace(self.topology,forwardings=(*self.topology.forwardings,changed))

    # Exact routes retain ordered evidence; broken chains, repeated links and exhausted host budgets fail explicitly.
    def test_explicit_paths_and_budget(self):
        actual = find_path(self.topology,self.request)
        self.assertEqual(find_path(self.topology,replace(self.request,link_ids=actual.link_ids)),actual)
        visits=list(actual.constraint_visits)
        copied=replace(actual,constraint_visits=visits)
        visits.clear()
        self.assertEqual(copied,actual)
        with self.assertRaises(ValueError):
            replace(actual,forwarding_ids=())
        for links in (('host_to_rc',),('rc_to_gpu0','host_to_rc'),('host_to_rc','host_to_rc'),('host_to_rc','rc_to_gpu1')):
            with self.assertRaises(ValueError):
                validate_path(self.topology,self.request,links)
        with self.assertRaisesRegex(ValueError,'max_hops'):
            find_path(self.topology,replace(self.request,max_hops=1))
        for changes in ({'max_hops':True},{'max_hops':0},{'link_ids':()},{'operation':'coherent'}):
            with self.assertRaises((ValueError,TypeError)):
                replace(self.request,**changes)

    # Service metadata changes the topology hash; immutable queries leave every original resource byte unchanged.
    def test_queries_are_pure_and_source_bound(self):
        before = canonical_json(self.topology)
        original = find_path(self.topology,self.request)
        limits = tuple(replace(c,capacity_Bps=32e9) if c.resource_id=='host_bus' else c for c in self.topology.constraints)
        updated = find_path(replace(self.topology,constraints=limits),self.request)
        self.assertEqual(updated.link_ids,original.link_ids)
        self.assertNotEqual(updated.topology_identity,original.topology_identity)
        self.assertEqual(before,canonical_json(self.topology))

    # Disconnected but valid structures are inspectable; missing routes cannot be converted into successful zero-hop paths.
    def test_disconnected_and_wrong_terminals(self):
        disconnected = replace(self.topology,links=(),forwardings=())
        with self.assertRaises(ValueError):
            find_path(disconnected,self.request)
        for changes in ({'source_port_id':'rc.host.out'},{'target_port_id':'host.out'},{'target_port_id':'missing'}):
            with self.assertRaises(ValueError):
                find_path(self.topology,replace(self.request,**changes))


# Independent exhaustive simple-path enumeration checks shortest reachability on small cyclic switch graphs.
class RandomPathTests(unittest.TestCase):
    # Enumerate intermediate owner permutations instead of reusing the production breadth-first traversal.
    def test_random_graphs_against_exhaustive_paths(self):
        rng = random.Random(417)
        for trial in range(30):
            owners = ('source','a','b','c','target')
            edges = {(a,b) for a in owners[:-1] for b in owners[1:] if a!=b and rng.random()<.35}
            resources = (ResourceNode(instance_id='root',parent_id=None,model_id=None),*(ResourceNode(instance_id=o,parent_id='root',model_id='fixture') for o in owners))
            domains = tuple(AddressDomainSpec(domain_id=o,owner_id=o,address_bits=8,source_ref='test') for o in ('source','target'))
            ports,links,forwardings = [],[],[]
            # Shared terminal ports require one physical neighbor; source/target adapters collect all candidate graph edges.
            resources += (ResourceNode(instance_id='source-terminal',parent_id='root',model_id='fixture'),ResourceNode(instance_id='target-terminal',parent_id='root',model_id='fixture'))
            domains = tuple(replace(d,owner_id=d.domain_id+'-terminal') for d in domains)
            graph_edges = edges|{('source-terminal','source'),('target','target-terminal')}
            for a,b in sorted(graph_edges):
                key=a+'>'+b
                ports.extend((SystemPortSpec(port_id=key+'.out',owner_id=a,direction='egress',protocol='test',operations=('copy',),source_ref='test',domain_id='source' if a=='source-terminal' else None),
                              SystemPortSpec(port_id=key+'.in',owner_id=b,direction='ingress',protocol='test',operations=('copy',),source_ref='test',domain_id='target' if b=='target-terminal' else None)))
                links.append(SystemLink(link_id=key,source_port_id=key+'.out',target_port_id=key+'.in',operations=('copy',),source_ref='test'))
            for a,b in sorted(graph_edges):
                for c,d in sorted(graph_edges):
                    if b==c:
                        forwardings.append(PortForwarding(forwarding_id=a+'>'+b+'>'+d,ingress_port_id=a+'>'+b+'.in',egress_port_id=c+'>'+d+'.out',operations=('copy',),source_ref='test'))
            topology = SystemTopology(scope_id='root',resources=resources,domains=domains,ports=tuple(ports),links=tuple(links),forwardings=tuple(forwardings),constraints=(),source_ref='test',coverage=('No service model',))
            candidates=[]
            for n in range(4):
                for middle in itertools.permutations(('a','b','c'),n):
                    route=('source',*middle,'target')
                    if all(pair in edges for pair in zip(route,route[1:])):
                        candidates.append(tuple(a+'>'+b for a,b in zip(route,route[1:])))
            request=PathRequest(source_port_id='source-terminal>source.out',target_port_id='target>target-terminal.in',operation='copy')
            with self.subTest(trial=trial):
                if not candidates:
                    with self.assertRaises(ValueError):
                        find_path(topology,request)
                else:
                    expected=min(candidates,key=lambda p:(len(p),p))
                    actual=find_path(topology,request)
                    self.assertEqual(actual.link_ids,('source-terminal>source',*expected,'target>target-terminal'))


if __name__=='__main__':
    unittest.main()

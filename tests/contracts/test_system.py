"""Standalone standard-library address/port boundary checks."""

from dataclasses import replace
import unittest

from contracts.hardware.system import AddressDomainSpec, SystemPortSpec


# Public boundaries validate exact integers and immutable explicit permissions without importing hardware models.
class SystemContractTests(unittest.TestCase):
    # The last byte is addressable; address width says nothing about resident physical capacity.
    def test_address_spans(self):
        domain = AddressDomainSpec(domain_id='host.virtual',owner_id='cpu',address_bits=64,source_ref='manual:test')
        domain.validate_span((1<<64)-1,1)
        for address,length in (((1<<64)-1,2),(-1,1),(0,0),(True,1),(0,1.)):
            with self.subTest(address=address,length=length),self.assertRaises((TypeError,ValueError)):
                domain.validate_span(address,length)
        for changes in ({'address_bits':65},{'address_bits':0},{'address_bits':True},{'source_ref':''},{'schema_version':'unknown'}):
            with self.assertRaises((TypeError,ValueError)):
                replace(domain,**changes)

    # Sequence ownership is immutable, and protocol identity alone never enables an extra operation.
    def test_port_ownership_and_permissions(self):
        operations,limits = ['write','copy'],['shared']
        port = SystemPortSpec(port_id='p',owner_id='cpu',direction='egress',protocol='CXL-assumed/v1',
                              operations=operations,source_ref='manual:test',constraint_ids=limits)
        operations.append('read')
        limits.append('another')
        self.assertEqual(port.operations,('copy','write'))
        self.assertEqual(port.constraint_ids,('shared',))
        for changes in ({'operations':('copy','copy')},{'operations':('rdma',)},{'operations':()},
                        {'constraint_ids':('x','x')},{'direction':'bidirectional'},{'domain_id':'  '},{'schema_version':'bad'}):
            with self.assertRaises((TypeError,ValueError)):
                replace(port,**changes)


if __name__=='__main__':
    unittest.main()

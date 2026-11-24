"""Complete NIC/cluster evidence retains failures and rejects modified boundary, work and path observations."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from configuration.resolution.dataclass_config import load_config
from contracts.versions.json_codec import canonical_json, parse_json
from evaluation.experiments.runner.system_network import NetworkStudy, run_study, summarize_records, write_study, read_study


ROOT=Path(__file__).resolve().parents[2]  # Synthetic sourced two-node comparison.


# Saved static composition is checked without producer execution or any route selection.
class NetworkStudyTests(unittest.TestCase):
    # Preserve the complete 12-case fixture, including all eight rejected candidates.
    @classmethod
    def setUpClass(cls):
        cls.study=load_config(NetworkStudy,ROOT/'config/experiments/system_network.json')
        cls.records=run_study(cls.study,source_revision='network-test')

    # Shared NIC work and local-only work use distinct accounting scopes; unknown complete costs remain explicit.
    def test_complete_roster(self):
        rows=summarize_records(self.records)
        self.assertEqual((len(rows),sum(r['status']=='succeeded' for r in rows)),(12,4))
        self.assertTrue(all(r['expectation_met'] for r in rows))
        for record in self.records:
            if record.status=='succeeded':
                metrics={m.name:m for m in record.metrics}
                self.assertTrue(all(metrics[n].value is None and metrics[n].unknown_reason for n in ('target_execution_time','target_energy')))

    # Only fixed fabric routes and saved local paths are validated during immutable replay.
    def test_roundtrip_without_producer_or_search(self):
        with TemporaryDirectory() as root:
            destination=Path(root)/'study'
            write_study(self.records,destination)
            with patch('evaluation.experiments.runner.system_network._evaluate',side_effect=AssertionError('producer')), \
                 patch('systemmodel.io.dma.analysis.find_path',side_effect=AssertionError('local search')), \
                 patch('clustermodel.fabric.routing.paths.heapq.heappop',side_effect=AssertionError('fabric search')):
                self.assertEqual(summarize_records(self.records),summarize_records(read_study(destination)))
            with self.assertRaises(FileExistsError):
                write_study(self.records,destination)

    # Rehashing cannot conceal modified payloads, shared charges, local routes or composed service bounds.
    def test_observation_tampering(self):
        position=next(i for i,r in enumerate(self.records) if r.spec.experiment_id=='shared_nic')
        record=self.records[position]
        for path,value in ((('logical_payload_bytes',),512),(('known_service_lower_bound_s',),0),
                           (('nodes','n0.node','flows',0,'object_id'),'wrong'),
                           (('nodes','n0.node','dma','legs',0,'path','link_ids'),[]),
                           (('fabric','resources',0,'service_bytes'),1),
                           (('fabric','messages',0,'route','link_ids'),['wire.1']),
                           (('unknown_costs',),[])):
            payload=parse_json(record.output_json); target=payload
            for key in path[:-1]: target=target[key]
            target[path[-1]]=value
            records=list(self.records); records[position]=replace(record,output_json=canonical_json(payload))
            with self.subTest(path=path),self.assertRaises(ValueError): summarize_records(tuple(records))

    # Complete case rosters and shared source/budget identity are part of the comparison contract.
    def test_source_roster_and_inputs(self):
        first=self.records[0]
        for records in (self.records[:-1],(*self.records,first),
                        (replace(first,spec=replace(first.spec,source_revision='changed')),*self.records[1:]),
                        (replace(first,inputs_json='{}'),*self.records[1:])):
            with self.assertRaises(ValueError): summarize_records(records)

    # Unknown complete execution cannot become zero and a conditional lower bound cannot become measured performance.
    def test_metric_integrity(self):
        position=next(i for i,r in enumerate(self.records) if r.status=='succeeded')
        first=self.records[position]
        for name,change in (('target_energy',{'value':0,'unknown_reason':None}),('known_service_lower_bound',{'kind':'estimated'})):
            records=list(self.records)
            records[position]=replace(first,metrics=tuple(replace(m,**change) if m.name==name else m for m in first.metrics))
            with self.assertRaises(ValueError): summarize_records(tuple(records))

    # Unavailable producers produce recorded failures rather than missing candidate rows.
    def test_unexpected_failure_retention(self):
        with patch('evaluation.experiments.runner.system_network._evaluate',side_effect=ValueError('injected')):
            rows=summarize_records(run_study(self.study))
        self.assertEqual(sum(not r['expectation_met'] for r in rows),4)
        self.assertTrue(all(r['status']=='failed' and r['diagnostic'] for r in rows))


if __name__=='__main__':
    unittest.main()

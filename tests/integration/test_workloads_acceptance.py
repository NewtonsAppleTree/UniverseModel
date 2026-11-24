"""Complete workloads acceptance cannot omit cases, mutate bytes or execute models during replay."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools.validate_workloads import check_rows,read_acceptance,validate_workloads


# Full reviewed acceptance is shared across read-only and tamper checks.
class WorkloadsAcceptanceTests(unittest.TestCase):
    # Run the standard-library path once, saving every success, expected failure and negative control.
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory()
        cls.path = Path(cls.temp.name)/'acceptance'
        cls.report = validate_workloads(cls.path)

    # Remove only the test-owned temporary directory through its lifecycle API.
    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    # The fixed roster covers 27 attempts, four execution failures and three successful-but-low-quality controls.
    def test_complete_roster_and_no_execution_replay(self):
        self.assertEqual([self.report['studies'][k]['cases'] for k in ('foundation','mapping','quality')],[10,5,12])
        self.assertEqual(sum(len(s['expected_failures']) for s in self.report['studies'].values()),4)
        self.assertEqual(len(self.report['studies']['quality']['quality_negative_controls']),3)
        with patch('tools.validate_workloads.workload_source_snapshot',side_effect=AssertionError('source access')), \
             patch('evaluation.experiments.runner.retrieval.evaluate_retrieval',side_effect=AssertionError('execution')):
            self.assertEqual(read_acceptance(self.path),self.report)
        with self.assertRaises(ValueError):
            check_rows('mapping',())

    # Raw byte changes are rejected before any summary can replace the committed observation.
    def test_raw_artifact_integrity(self):
        path = self.path/'mapping_summary.json'
        original = path.read_bytes()
        try:
            path.write_bytes(original+b' ')
            with self.assertRaisesRegex(ValueError,'SHA256'):
                read_acceptance(self.path)
        finally:
            path.write_bytes(original)


if __name__=='__main__':
    unittest.main()

"""Local data provenance, semantic binding and finite workload profile boundaries."""

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from configuration.resolution.dataclass_config import load_config, resolve_dataclass
from contracts.versions.json_codec import canonical_json, parse_json
from workloads.datasets.attention import load_attention_dataset
from workloads.profiles.attention import AttentionCase, AttentionSuite, prepare_attention


ROOT = Path(__file__).resolve().parents[2]  # Repository fixture root; tests never download data.


# Profile tests distinguish declared provenance, verified input bytes and representativeness.
class AttentionProfileTests(unittest.TestCase):
    # Load the reviewed finite suite with its shared host budgets and hand fixture.
    def setUp(self):
        self.suite = load_config(AttentionSuite, ROOT / 'config/experiments/attention_workloads.json')
        self.case = next(c for c in self.suite.cases if c.name == 'dataset_uniform')
        self.raw = (ROOT / 'config/workloads/attention_inputs.json').read_bytes()

    # Exact source bytes and the complete spec determine the loaded tensors.
    def test_fixture_source_and_values(self):
        data = prepare_attention(self.case, self.suite, data_root=ROOT / 'config/workloads')
        self.assertEqual(data.q, (0.0,) * 8)
        self.assertEqual(data.v, (1.0, 2.0, 3.0, 5.0, 6.0, 7.0))
        self.assertEqual(sha256(self.raw).hexdigest(), self.case.dataset.sha256)
        self.assertEqual((self.case.dataset.kind, self.case.dataset.split), ('synthetic', 'test'))
        self.assertEqual(resolve_dataclass(AttentionSuite, parse_json(canonical_json(self.suite))), self.suite)

    # Hashing includes whitespace; byte limits apply before parsing and semantic checks follow hashing.
    def test_hash_byte_budget_and_spec_binding(self):
        with TemporaryDirectory() as root:
            path = Path(root) / self.case.dataset.relative_path
            path.write_bytes(self.raw)
            with self.assertRaisesRegex(ValueError, 'max_file_bytes'):
                load_attention_dataset(self.case.dataset, root, self.case.spec, max_file_bytes=len(self.raw) - 1)
            with self.assertRaisesRegex(ValueError, 'spec identity'):
                load_attention_dataset(self.case.dataset, root, replace(self.case.spec, scale=1.0))
            path.write_bytes(self.raw + b' ')
            with self.assertRaisesRegex(ValueError, 'SHA256'):
                load_attention_dataset(self.case.dataset, root, self.case.spec)

    # Correct hashes cannot excuse duplicate JSON keys, nonfinite/int tensors or malformed shapes/schemas.
    def test_strict_file_payload(self):
        base = parse_json(self.raw.decode('utf-8'))
        altered = [
            {**base, 'extra': 1}, {**base, 'schema_version': 'future'},
            {**base, 'inputs': {**base['inputs'], 'q': [0.0]}},
            {**base, 'inputs': {**base['inputs'], 'q': [0] * 8}},
            {**base, 'inputs': {**base['inputs'], 'other': []}},
        ]
        payloads = [canonical_json(v).encode('utf-8') for v in altered]
        payloads += [b'{"inputs":{},"inputs":{}}', self.raw.replace(b'0.0', b'NaN', 1), b'\xff']
        with TemporaryDirectory() as root:
            path = Path(root) / self.case.dataset.relative_path
            for raw in payloads:
                with self.subTest(raw=raw[:50]):
                    path.write_bytes(raw)
                    manifest = replace(self.case.dataset, sha256=sha256(raw).hexdigest())
                    with self.assertRaises((ValueError, TypeError)):
                        load_attention_dataset(manifest, root, self.case.spec)

    # Portable paths exclude traversal/absolute/ambiguous syntax; resolved external targets are also refused.
    def test_path_and_provenance_guards(self):
        for value in ('../data.json', '/data.json', 'C:/data.json', 'a\\data.json', './data.json', 'a//b', 'a/../b', 'a/'):
            with self.subTest(path=value), self.assertRaises(ValueError):
                replace(self.case.dataset, relative_path=value)
        for changes in ({'sha256': 'A' * 64}, {'source': ''}, {'usage_terms': ''}, {'kind': 'real'}, {'split': 'all'}):
            with self.assertRaises(ValueError):
                replace(self.case.dataset, **changes)
        with TemporaryDirectory() as root:
            base = Path(root).resolve()
            # Exercise containment after path resolution, independently of OS symlink creation privileges.
            with patch.object(Path, 'resolve', side_effect=(base, base.parent / 'outside.json')):
                with self.assertRaisesRegex(ValueError, 'outside'):
                    load_attention_dataset(self.case.dataset, base, self.case.spec)

    # Source choice is exclusive; roster lists are copied and case identities are unique.
    def test_profile_invariants(self):
        cases = list(self.suite.cases)
        frozen = replace(self.suite, cases=cases)
        cases.clear()
        self.assertEqual(len(frozen.cases), 10)
        for changes in ({'seed': 1}, {'dataset': None}, {'name': ''}, {'expected_status': 'pass'}):
            with self.assertRaises(ValueError):
                replace(self.case, **changes)
        for changes in ({'cases': ()}, {'cases': (self.case, self.case)}, {'precision_digits': 31}, {'max_elements': True}):
            with self.assertRaises((TypeError, ValueError)):
                replace(self.suite, **changes)
        unknown = parse_json(canonical_json(self.suite))
        unknown['formula'] = 'eval()'
        with self.assertRaises(ValueError):
            resolve_dataclass(AttentionSuite, unknown)

    # Generated inputs are deterministic and neither generated nor file-backed inputs bypass the same budget.
    def test_preparation_determinism_and_limits(self):
        first = self.suite.cases[0]
        a = prepare_attention(first, self.suite, data_root='not-used')
        self.assertEqual(a, prepare_attention(first, self.suite, data_root='also-not-used'))
        limited = replace(self.suite, max_elements=1)
        for case in (first, self.case):
            with self.assertRaisesRegex(ValueError, 'max_elements'):
                prepare_attention(case, limited, data_root='not-used')
        with self.assertRaisesRegex(ValueError, 'belong'):
            prepare_attention(replace(first, name='foreign'), self.suite, data_root='not-used')
        for seed in (-1, True, 1 << 64):
            with self.assertRaises(ValueError):
                AttentionCase(name='bad', spec=first.spec, purpose='guard', seed=seed)


if __name__ == '__main__':
    unittest.main()

"""统一验收入口的完整名单、原始字节防篡改及只读语义。"""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import validate_chipmodel as acceptance


# 仅用于验收器反例的合成名单，不代表生产模型验证已通过。
def rows_for(name):
    count, failures = acceptance.STUDIES[name]
    rows = [{'case': case, 'status': 'failed', 'diagnostic': 'declared boundary'}
            for case, number in failures.items() for _ in range(number)]
    rows += [{'case': f'ok-{i}', 'status': 'succeeded', 'diagnostic': None} for i in range(count - len(rows))]
    if name == 'digital_tile':
        for row in rows:
            row['candidate'] = row.pop('case')
        return [{'case': 'synthetic', 'rows': rows}]
    return rows


# 验收程序应捕获假成功、遗漏和损坏，回读不能重新跑研究模型。
class AcceptanceTests(unittest.TestCase):
    # 已知反例意外成功同样失败；不能仅以进程退出0作为验收。
    def test_expected_failure_is_required(self):
        rows = rows_for('physical')
        self.assertEqual(acceptance.check_rows('physical', rows)['succeeded'], 17)
        rows[0]['status'] = 'succeeded'
        with self.assertRaisesRegex(ValueError, 'unexpected'):
            acceptance.check_rows('physical', rows)

    # 缺失运行和未完成状态不能进入最终验收。
    def test_incomplete_and_pending(self):
        rows = rows_for('cim')
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            acceptance.check_rows('cim', rows[:-1])
        rows[-1]['status'] = 'running'
        with self.assertRaisesRegex(ValueError, 'unfinished'):
            acceptance.check_rows('cim', rows)

    # 完整读回只发--read；篡改任一摘要的原始字节时，在子进程之前拒绝。
    def test_read_only_and_byte_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            all_rows = {name: rows_for(name) for name in acceptance.STUDIES}
            acceptance.write_json(target / 'source.json', {'source_revision': 'saved-revision'})
            for name, rows in all_rows.items():
                acceptance.write_json(target / f'{name}_summary.json', rows)
            report = {'schema': 'chipmodel-acceptance/v1', 'source_revision': 'saved-revision',
                      'studies': {name: acceptance.check_rows(name, rows) for name, rows in all_rows.items()},
                      'artifacts': acceptance.artifact_hashes(target)}
            acceptance.write_json(target / 'acceptance.json', report)
            with patch.object(acceptance, 'invoke', side_effect=lambda name, args: (all_rows[name], {})) as invoke:
                with patch.object(acceptance, 'source_snapshot', side_effect=AssertionError('read must not recapture source')):
                    self.assertEqual(acceptance.verify_saved(target), report)
                self.assertEqual(invoke.call_count, 6)
                self.assertTrue(all(call.args[1][0] == '--read' for call in invoke.call_args_list))
                invoke.reset_mock()
                path = target / 'physical_summary.json'
                path.write_text(json.dumps(all_rows['physical']) + ' ', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'hash'):
                    acceptance.verify_saved(target)
                invoke.assert_not_called()

    # 新运行拒绝覆盖已有证据，即使该目录只含不完整产物。
    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / 'keep.txt').write_text('evidence', encoding='utf-8')
            with self.assertRaises(FileExistsError):
                acceptance.run_acceptance(target)
            self.assertEqual((target / 'keep.txt').read_text(encoding='utf-8'), 'evidence')


if __name__ == '__main__':
    unittest.main()

"""Acceptance must bind the complete reviewed roster and every saved run to one source manifest."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from contracts.results.experiment import ExperimentSpec, RunRecord
from evaluation.experiments.runner.bundle import write_records
from tools import validate_systemmodel as acceptance


# Minimal source snapshots test provenance mechanics; they do not claim real model validation.
def source_for(version: str = 'one') -> dict:
    files={'model.py':sha256(version.encode()).hexdigest()}
    digest=sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {'files':files,'source_revision':'saved-head+python-config-sha256:'+digest}


# Synthetic outcomes exercise acceptance accounting; semantic model checks are covered by the study tests.
def rows_for(name: str) -> list:
    failures=acceptance.STUDIES[name][1]
    return [{'case':case,'status':'failed' if case in failures else 'succeeded',
             'diagnostic':'declared boundary' if case in failures else None,'expectation_met':True}
            for case in (*acceptance.SUCCESSES[name],*failures)]


# Save real immutable indexes/manifests with small synthetic records, including both successful and failed runs.
def make_bundle(target: Path, mixed_study: str | None = None) -> tuple[dict, dict]:
    source=source_for()
    acceptance.write_json(target/'source.json',source)
    all_rows={name:rows_for(name) for name in acceptance.STUDIES}
    for name,rows in all_rows.items():
        revision=source_for('other')['source_revision'] if name==mixed_study else source['source_revision']
        records=tuple(RunRecord(run_id=name+'-'+row['case'],
                      spec=ExperimentSpec(experiment_id=row['case'],implementation_id='acceptance-test/v1',
                                          mode='analytical',source_revision=revision,assumptions=('Synthetic metadata only',)),
                      configuration_json='{}',inputs_json='{}',output_json='{}' if row['status']=='succeeded' else None,
                      metrics=(),status=row['status'],host_elapsed_s=0,diagnostic=row['diagnostic']) for row in rows)
        write_records(records,target/name,acceptance.INDEX_SCHEMAS[name],
                      lambda items: acceptance.check_record_sources(items,revision))
        acceptance.write_json(target/(name+'_summary.json'),rows)
    report={'schema':'systemmodel-acceptance/v1','source_revision':source['source_revision'],
            'studies':{name:acceptance.check_rows(name,rows) for name,rows in all_rows.items()},
            'artifacts':acceptance.artifact_hashes(target)}
    acceptance.write_json(target/'acceptance.json',report)
    return all_rows,report


# Corruption tests intentionally rehash outer metadata so semantic source checks cannot rely only on file integrity.
def rehash_report(target: Path, report: dict) -> None:
    report['artifacts']=acceptance.artifact_hashes(target)
    (target/'acceptance.json').write_text(json.dumps(report),encoding='utf-8')


# Source identity, positive/negative controls and read-only evidence preservation are independent acceptance obligations.
class SystemAcceptanceTests(unittest.TestCase):
    # Missing/duplicated/replaced positives and unexpected negative outcomes must all fail despite plausible totals.
    def test_exact_candidate_roster_and_outcomes(self):
        for name in acceptance.STUDIES:
            rows=rows_for(name)
            self.assertEqual(acceptance.check_rows(name,rows)['cases'],len(rows))
            mutations=[rows[:-1],[*rows[:-1],rows[0]]]
            for key,value in (('case','unreviewed_replacement'),('status','failed'),('status','running'),('expectation_met',False)):
                altered=deepcopy(rows); altered[0][key]=value; mutations.append(altered)
            altered=deepcopy(rows); altered[-1]['status']='succeeded'; mutations.append(altered)
            altered=deepcopy(rows); altered[-1]['diagnostic']=None; mutations.append(altered)
            for changed in mutations:
                with self.subTest(study=name,changed=changed[0]),self.assertRaises(ValueError):
                    acceptance.check_rows(name,changed)

    # The declared aggregate must match the saved file hashes, without inspecting today's checkout.
    def test_source_manifest_consistency(self):
        source=source_for(); revision=source['source_revision']
        acceptance.check_source(source,revision)
        changed=deepcopy(source); changed['files']['model.py']='0'*64
        for value in (changed,[],{},dict(source,files={}),dict(source,files={'model.py':'invalid'})):
            with self.subTest(source=value),self.assertRaises(ValueError): acceptance.check_source(value,revision)
        with self.assertRaises(ValueError): acceptance.check_source(source,'another-revision')

    # Verified manifests and every successful/failed run are checked; only --read CLI calls are allowed during replay.
    def test_read_only_and_complete_manifest(self):
        with TemporaryDirectory() as directory:
            target=Path(directory); rows,report=make_bundle(target)
            original=acceptance.artifact_hashes(target)
            with patch.object(acceptance,'invoke',side_effect=lambda name,args:(rows[name],{})) as invoke, \
                 patch.object(acceptance,'source_snapshot',side_effect=AssertionError('must not recapture current source')):
                self.assertEqual(acceptance.verify_saved(target),report)
                self.assertEqual(invoke.call_count,6)
                self.assertTrue(all(call.args[1]==['--read',str(target/call.args[0])] for call in invoke.call_args_list))
            self.assertEqual(acceptance.artifact_hashes(target),original)

    # A whole internally consistent study from another revision cannot be spliced into a claimed common-source bundle.
    def test_mixed_study_source_rejected(self):
        with TemporaryDirectory() as directory:
            target=Path(directory); rows,_=make_bundle(target,mixed_study='system_ai')
            with patch.object(acceptance,'invoke',side_effect=lambda name,args:(rows[name],{})),self.assertRaisesRegex(ValueError,'run source'):
                acceptance.verify_saved(target)

    # Relabeling both outer source fields and recomputing their valid hashes still disagrees with saved RunRecord sources.
    def test_relabelled_top_source_rejected(self):
        with TemporaryDirectory() as directory:
            target=Path(directory); _,report=make_bundle(target)
            replacement=source_for('replacement')
            (target/'source.json').write_text(json.dumps(replacement),encoding='utf-8')
            report['source_revision']=replacement['source_revision']; rehash_report(target,report)
            with patch.object(acceptance,'invoke') as invoke,self.assertRaisesRegex(ValueError,'run source'):
                acceptance.verify_saved(target)
            invoke.assert_not_called()

    # Raw-byte edits or an unlisted file fail before CLI checks, even when JSON values would be unchanged.
    def test_raw_bytes_and_extra_artifact_rejected(self):
        for mode in ('bytes','extra','missing'):
            with self.subTest(mode=mode),TemporaryDirectory() as directory:
                target=Path(directory); make_bundle(target)
                path=target/'system_summary.json'
                if mode=='bytes': path.write_bytes(path.read_bytes()+b' ')
                elif mode=='extra': (target/'extra.json').write_text('{}',encoding='utf-8')
                else: path.unlink()
                with patch.object(acceptance,'invoke') as invoke,self.assertRaisesRegex(ValueError,'artifact hash'):
                    acceptance.verify_saved(target)
                invoke.assert_not_called()

    # Outer rehashing cannot hide a changed raw run whose inner immutable manifest was not updated.
    def test_inner_run_manifest_is_checked(self):
        with TemporaryDirectory() as directory:
            target=Path(directory); _,report=make_bundle(target)
            path=target/'system/run-0000/run.json'; path.write_bytes(path.read_bytes()+b' ')
            rehash_report(target,report)
            with patch.object(acceptance,'invoke') as invoke,self.assertRaises(ValueError): acceptance.verify_saved(target)
            invoke.assert_not_called()

    # Even an incomplete previous run is preserved and cannot be overwritten by a new acceptance run.
    def test_existing_output_is_preserved(self):
        with TemporaryDirectory() as directory:
            target=Path(directory); (target/'keep.txt').write_text('evidence',encoding='utf-8')
            with self.assertRaises(FileExistsError): acceptance.run_acceptance(target)
            self.assertEqual((target/'keep.txt').read_text(encoding='utf-8'),'evidence')


if __name__=='__main__':
    unittest.main()

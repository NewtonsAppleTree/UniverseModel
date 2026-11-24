"""Real-data RBF Attention quality, held-out splits, numeric ablations and optional NumPy evidence."""

import argparse
from pathlib import Path

from configuration.resolution.dataclass_config import load_config
from contracts.versions.json_codec import canonical_json
from evaluation.experiments.runner.retrieval import read_study,run_study,summarize_records,write_study
from workloads.profiles.retrieval import RetrievalProfile


# A successful experiment must satisfy its numeric/quality expectations; expected negative controls remain visible.
def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=root/'config/experiments/retrieval_quality.json')
    parser.add_argument('--data-root',type=Path,default=root/'config/workloads')
    parser.add_argument('--source-revision',default='unrecorded')
    parser.add_argument('--numpy-reference',action='store_true')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--read',type=Path)
    args = parser.parse_args()
    if args.read and (args.output or args.numpy_reference):
        parser.error('--read cannot be combined with --output or --numpy-reference')
    records = read_study(args.read) if args.read else run_study(load_config(RetrievalProfile,args.config),data_root=args.data_root,
                                                             source_revision=args.source_revision,numpy_reference=args.numpy_reference)
    if args.output:
        write_study(records,args.output)
    rows = summarize_records(records)
    print(canonical_json(rows))
    return 0 if rows and all(r['expectation_met'] for r in rows) else 1


if __name__=='__main__':
    raise SystemExit(main())

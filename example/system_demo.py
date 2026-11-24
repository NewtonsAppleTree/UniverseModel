"""Static host/two-card connectivity, explicit P2P permission and shared-resource references."""

import argparse
from pathlib import Path

from configuration.resolution.dataclass_config import load_config
from contracts.versions.json_codec import canonical_json
from evaluation.experiments.runner.system import NodeStudy, read_study, run_study, summarize_records, write_study


# CLI preserves every requested case, including expected failures; source revision is explicit and replay does not search.
def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=root/'config/experiments/system_connectivity.json')
    parser.add_argument('--source-revision',default='unrecorded')
    paths = parser.add_mutually_exclusive_group()
    paths.add_argument('--output',type=Path)
    paths.add_argument('--read',type=Path)
    args = parser.parse_args()
    records = read_study(args.read) if args.read else run_study(load_config(NodeStudy,args.config),source_revision=args.source_revision)
    if args.output:
        write_study(records,args.output)
    rows = summarize_records(records)
    print(canonical_json(rows))
    return 0 if all(row['expectation_met'] for row in rows) else 1


if __name__=='__main__':
    raise SystemExit(main())

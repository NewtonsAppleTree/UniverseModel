"""Attention workloads, logical accounting and independent references with full source/failed-case records."""

import argparse
from pathlib import Path

from configuration.resolution.dataclass_config import load_config
from contracts.versions.json_codec import canonical_json
from evaluation.experiments.runner.workload import read_study, run_study, summarize_records, write_study
from workloads.profiles.attention import AttentionSuite


# Expected errors must remain errors; no self-comparison of a reference is reported as a quality pass.
def comparison_exit_status(rows: tuple[dict, ...]) -> int:
    return 0 if rows and all(row['expectation_met'] for row in rows) else 1


# Explicit data root is independent of config location; replay never accesses datasets or invokes a reference.
def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=root / 'config/experiments/attention_workloads.json')
    parser.add_argument('--data-root', type=Path, default=root / 'config/workloads')
    parser.add_argument('--source-revision', default='unrecorded')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--read', type=Path)
    args = parser.parse_args()
    if args.read is not None:
        if args.output is not None:
            parser.error('--read cannot be combined with --output')
        records = read_study(args.read)
    else:
        suite = load_config(AttentionSuite, args.config)
        records = run_study(suite, data_root=args.data_root, source_revision=args.source_revision)
        if args.output is not None:
            write_study(records, args.output)
    rows = summarize_records(records)
    print(canonical_json(rows))
    return comparison_exit_status(rows)


if __name__ == '__main__':
    raise SystemExit(main())

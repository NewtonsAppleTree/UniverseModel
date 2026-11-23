"""python -m example.linear_demo: reproducible finite mapping comparison and optional immutable bundles."""

import argparse
from pathlib import Path

from artifacts.storage.local import read_run, write_run
from configuration.resolution.dataclass_config import load_config
from contracts.results.experiment import RunRecord
from contracts.versions.json_codec import canonical_json, parse_json
from evaluation.experiments.runner.linear import LinearStudy, run_study, summarize_records


# Feasibility failures remain visible; require a valid candidate and reject every completed quality failure.
def comparison_exit_status(summary: tuple[dict[str, object], ...]) -> int:
    passed = any(row["validation_passed"] is True for row in summary)
    mismatch = any(row["validation_passed"] is False for row in summary)
    return 0 if passed and not mismatch else 1


# Run JSON-defined candidates or regenerate a saved summary; all paths are local and writes refuse replacement.
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "config/experiments/linear_mapping.json")
    parser.add_argument("--set", action="append", default=[], metavar="FIELD=JSON")
    parser.add_argument("--source-revision", default="unrecorded")
    parser.add_argument("--output", type=Path, help="new directory for run bundles and summary")
    parser.add_argument("--read", type=Path, help="rebuild a comparison from an existing bundle directory")
    args = parser.parse_args()
    if args.read is not None:
        if args.output is not None or args.set:
            parser.error("--read cannot be combined with --output/--set")
        records = tuple(RunRecord.from_dict(read_run(path.parent)) for path in sorted(args.read.glob("*/manifest.json")))
        if not records:
            parser.error("no committed run bundles found")
        summary = summarize_records(records)
        print(canonical_json(summary))
        return comparison_exit_status(summary)
    overrides = {}
    for assignment in args.set:
        key, separator, value = assignment.partition("=")
        if not separator or key in overrides:
            parser.error("overrides must be unique FIELD=JSON assignments")
        overrides[key] = parse_json(value)
    study = load_config(LinearStudy, args.config, overrides=overrides)
    records = run_study(study, source_revision=args.source_revision)
    summary = summarize_records(records)
    if args.output is not None:
        args.output.mkdir(parents=True, exist_ok=False)
        for record in records:
            write_run(record, args.output / record.run_id)
        (args.output / "summary.json").write_text(canonical_json(summary) + "\n", encoding="utf-8")
    print(canonical_json(summary))
    return comparison_exit_status(summary)


if __name__ == "__main__":
    raise SystemExit(main())

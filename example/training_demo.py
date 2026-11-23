"""python -m example.training_demo: finite training comparison, optional PyTorch reference and saved run replay."""

import argparse
from pathlib import Path

from artifacts.storage.local import read_run, write_run
from configuration.resolution.dataclass_config import load_config
from contracts.results.experiment import RunRecord
from contracts.versions.json_codec import canonical_json, parse_json
from evaluation.experiments.runner.training import TrainingStudy, run_training_study, summarize_training
from example.linear_demo import comparison_exit_status


# Run one immutable old-state study or rebuild its saved comparison; every output directory must be new.
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "config/experiments/training_step.json")
    parser.add_argument("--set", action="append", default=[], metavar="FIELD=JSON")
    parser.add_argument("--source-revision", default="unrecorded")
    parser.add_argument("--torch-reference", action="store_true", help="optional CPU PyTorch autograd/SGD reference")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--read", type=Path)
    args = parser.parse_args()
    if args.read is not None:
        if args.output is not None or args.set or args.torch_reference:
            parser.error("--read cannot combine with --output, --set or --torch-reference")
        records = tuple(RunRecord.from_dict(read_run(path.parent)) for path in sorted(args.read.glob("*/manifest.json")))
        if not records:
            parser.error("no committed training run bundles")
    else:
        overrides = {}
        for assignment in args.set:
            key, separator, value = assignment.partition("=")
            if not separator or key in overrides:
                parser.error("overrides must be unique FIELD=JSON assignments")
            overrides[key] = parse_json(value)
        study = load_config(TrainingStudy, args.config, overrides=overrides)
        records = run_training_study(study, source_revision=args.source_revision,
                                     reference_backend="pytorch" if args.torch_reference else "exact")
    summary = summarize_training(records)
    if args.output is not None:
        args.output.mkdir(parents=True, exist_ok=False)
        for record in records:
            write_run(record, args.output / record.run_id)
        (args.output / "summary.json").write_text(canonical_json(summary) + "\n", encoding="utf-8")
    print(canonical_json(summary))
    return comparison_exit_status(summary)


if __name__ == "__main__":
    raise SystemExit(main())

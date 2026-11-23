"""Run, save or read the four-node placement study; reported times are analytical bounds."""

import argparse
import json
from pathlib import Path

from configuration.resolution.dataclass_config import load_config
from contracts.versions.json_codec import parse_json
from evaluation.experiments.runner.cluster import ClusterStudy, read_study, run_study, summarize_records, write_study


# Resolve strict structured configuration or rebuild saved observations, rejecting ambiguous read-time overrides.
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="ClusterStudy JSON; default config/experiments/cluster_placement.json")
    parser.add_argument("--set", action="append", default=[], metavar="FIELD=JSON")
    parser.add_argument("--source-revision", help="explicit source snapshot identity; default unrecorded")
    parser.add_argument("--overview", action="store_true", help="show saved inventory, reachability and logical traffic tables")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--output", type=Path, help="new immutable study directory")
    mode.add_argument("--read", type=Path, help="verify/rebuild saved comparison without model execution")
    args = parser.parse_args()
    if args.read and (args.config is not None or args.set or args.source_revision is not None):
        parser.error("--read cannot be combined with configuration, input or source overrides")
    try:
        if args.read:
            records = read_study(args.read)
        else:
            overrides = {}
            for assignment in args.set:
                key, separator, value = assignment.partition("=")
                if not separator or key in overrides:
                    raise ValueError("overrides must be unique FIELD=JSON assignments")
                overrides[key] = parse_json(value)
            config = args.config or Path(__file__).resolve().parents[1] / "config/experiments/cluster_placement.json"
            study = load_config(ClusterStudy, config, overrides=overrides)
            records = run_study(study, source_revision=args.source_revision or "unrecorded")
            if args.output:
                write_study(records, args.output)
        print(json.dumps(summarize_records(records, include_overview=args.overview), ensure_ascii=False, indent=2))
        return 0 if all(record.status == "succeeded" for record in records) else 1
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())

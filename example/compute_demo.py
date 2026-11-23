"""CPU/GPU/NPU能力、单因素限制与边界反例；完整保存/回读，不作跨架构排名。"""

import argparse
from pathlib import Path

from configuration.resolution.dataclass_config import load_config
from contracts.versions.json_codec import canonical_json
from evaluation.experiments.runner.compute import ComputeStudy, read_study, run_study, summarize_records, write_study


# 常规案例必须完成分析且GPU无已知不可行；显式boundary案例保留失败并展示。
def comparison_exit_status(rows: tuple[dict[str, object], ...]) -> int:
    required = [row for row in rows if row["role"] != "boundary"]
    return 0 if required and all(row["status"] == "succeeded" and
        (row["family"] != "gpu" or row["analysis"]["launch_feasible"] is not False) for row in required) else 1


# 配置仅含数据；回读直接展示已有分析，来源默认unrecorded表示未完整记录。
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "config/experiments/compute_capacity.json")
    parser.add_argument("--source-revision", default="unrecorded")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--read", type=Path)
    args = parser.parse_args()
    if args.read is not None:
        if args.output is not None:
            parser.error("--read cannot be combined with --output")
        records = read_study(args.read)
    else:
        records = run_study(load_config(ComputeStudy, args.config), source_revision=args.source_revision)
        if args.output is not None:
            write_study(records, args.output)
    rows = summarize_records(records)
    print(canonical_json(rows))
    return comparison_exit_status(rows)


if __name__ == "__main__":
    raise SystemExit(main())

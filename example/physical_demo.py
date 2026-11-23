"""CH9物理条件、来源查询与未知成本的独立保存/回读入口。"""

import argparse
from pathlib import Path

from configuration.resolution.dataclass_config import load_config
from contracts.versions.json_codec import canonical_json
from evaluation.experiments.runner.physical import PhysicalStudy, read_study, run_study, summarize_records, write_study


# 普通比较须分析成功；预期边界失败保留记录，未知物理成本不视为执行失败。
def comparison_exit_status(rows: tuple[dict, ...]) -> int:
    return int(any(row["status"] != "succeeded" and row["role"] != "boundary" for row in rows))


# 配置只读参数；回读不重新执行模型或访问来源网站。
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "config/experiments/physical_evidence.json")
    parser.add_argument("--source-revision", default="unrecorded")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--read", type=Path)
    args = parser.parse_args()
    if args.read is not None:
        if args.output is not None:
            parser.error("--read cannot be combined with --output")
        records = read_study(args.read)
    else:
        records = run_study(load_config(PhysicalStudy, args.config), source_revision=args.source_revision)
        if args.output is not None:
            write_study(records, args.output)
    rows = summarize_records(records)
    print(canonical_json(rows))
    return comparison_exit_status(rows)


if __name__ == "__main__":
    raise SystemExit(main())

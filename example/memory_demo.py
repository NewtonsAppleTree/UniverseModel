"""外存与缓存对照；保留profile、实际访问、条件界、失败与未知成本。"""

import argparse
from pathlib import Path

from configuration.resolution.dataclass_config import load_config
from contracts.versions.json_codec import canonical_json
from evaluation.experiments.runner.memory import MemoryStudy, read_study, run_study, summarize_records, write_study


# 基线和消融必须完成分析；boundary失败仍完整保留，不冒充目标执行验证。
def comparison_exit_status(rows: tuple[dict[str, object], ...]) -> int:
    required = [row for row in rows if row["role"] != "boundary"]
    return 0 if required and all(row["status"] == "succeeded" for row in required) else 1


# 配置只含数据，read只展示保存结果；未记录源码身份时显式标为unrecorded。
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "config/experiments/memory_access.json")
    parser.add_argument("--source-revision", default="unrecorded")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--read", type=Path)
    args = parser.parse_args()
    if args.read is not None:
        if args.output is not None:
            parser.error("--read cannot be combined with --output")
        records = read_study(args.read)
    else:
        records = run_study(load_config(MemoryStudy, args.config), source_revision=args.source_revision)
        if args.output is not None:
            write_study(records, args.output)
    rows = summarize_records(records)
    print(canonical_json(rows))
    return comparison_exit_status(rows)


if __name__ == "__main__":
    raise SystemExit(main())

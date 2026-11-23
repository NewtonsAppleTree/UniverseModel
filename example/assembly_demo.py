"""CH8共享资源与跨Die边界对照；保存/回读完整案例，不将条件界称为执行时间。"""

import argparse
from pathlib import Path

from configuration.resolution.dataclass_config import load_config
from contracts.versions.json_codec import canonical_json
from evaluation.experiments.runner.assembly import AssemblyStudy, read_study, run_study, summarize_records, write_study


# 常规案例必须完成分析；boundary失败保留原诊断，不假装已验证物理可行性。
def comparison_exit_status(rows: tuple[dict[str, object], ...]) -> int:
    required = [row for row in rows if row["role"] != "boundary"]
    return 0 if required and all(row["status"] == "succeeded" for row in required) else 1


# 配置仅包含数据，read仅读取已有产物；没有默认未记录的硬件性能结论。
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "config/experiments/chip_assembly.json")
    parser.add_argument("--source-revision", default="unrecorded")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--read", type=Path)
    args = parser.parse_args()
    if args.read is not None:
        if args.output is not None:
            parser.error("--read cannot be combined with --output")
        records = read_study(args.read)
    else:
        records = run_study(load_config(AssemblyStudy, args.config), source_revision=args.source_revision)
        if args.output is not None:
            write_study(records, args.output)
    rows = summarize_records(records)
    print(canonical_json(rows))
    return comparison_exit_status(rows)


if __name__ == "__main__":
    raise SystemExit(main())

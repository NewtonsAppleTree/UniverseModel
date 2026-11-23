"""python -m example.cim_demo: CIM局部数值/资源/质量对照与完整记录回读。"""

import argparse
from pathlib import Path

from configuration.resolution.dataclass_config import load_config
from contracts.versions.json_codec import canonical_json
from evaluation.experiments.runner.cim import CimStudy, read_study, run_study, summarize_records, write_study


# 主比较与资源消融必须通过质量；显式精度/边界实验保留其损失与失败，不过滤样本。
def comparison_exit_status(rows: tuple[dict[str, object], ...]) -> int:
    required = [row for row in rows if row["category"] in ("baseline", "mapping", "resource_ablation")]
    return 0 if required and all(row["status"] == "succeeded" and row["validation_passed"] for row in required) else 1


# 参数、记录和路径均为显式本地输入；回读不调用模型。
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "config/experiments/cim_matvec.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--read", type=Path)
    parser.add_argument("--source-revision", default="unrecorded")
    args = parser.parse_args()
    if args.read is not None:
        if args.output is not None:
            parser.error("--read cannot be combined with --output")
        records = read_study(args.read)
    else:
        records = run_study(load_config(CimStudy, args.config), source_revision=args.source_revision)
        if args.output is not None:
            write_study(records, args.output)
    rows = summarize_records(records)
    print(canonical_json(rows))
    return comparison_exit_status(rows)


if __name__ == "__main__":
    raise SystemExit(main())

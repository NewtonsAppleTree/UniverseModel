"""数字 Tile 同预算映射与单因素资源敏感性；支持完整候选清单的保存/回读。"""

import argparse
from dataclasses import replace
from pathlib import Path

from artifacts.storage.local import read_run, write_run
from configuration.resolution.dataclass_config import load_config
from contracts.results.experiment import RunRecord
from contracts.versions.json_codec import canonical_json, parse_json
from evaluation.experiments.runner.linear import LinearStudy, run_study, summarize_records
from example.linear_demo import comparison_exit_status


# 每次只改变一类资源；bank 消融固定总字数/容量，其余时钟扫描保持工作与数据不变。
def sensitivity_studies(study: LinearStudy) -> tuple[tuple[str, LinearStudy], ...]:
    backend = study.hardware.tile_backend
    if backend is None:
        raise ValueError("digital tile sensitivity requires tile_backend")
    result = [("baseline", study)]
    for case in ("mac_lanes_x2", "mac_clock_div100", "dma_clock_div4", "sram_clock_div10", "one_bank_same_capacity"):
        hardware, tile = study.hardware, backend.tile
        if case == "mac_lanes_x2":
            tile = replace(tile, mac=replace(tile.mac, lane_count=tile.mac.lane_count * 2))
        elif case == "mac_clock_div100":
            tile = replace(tile, compute_clock=replace(tile.compute_clock, frequency_hz=tile.compute_clock.frequency_hz / 100))
        elif case == "dma_clock_div4":
            channels = tuple(replace(c, clock=replace(c.clock, frequency_hz=c.clock.frequency_hz / 4))
                             if c.resource_id == backend.channel_id else c for c in tile.resources.channels)
            tile = replace(tile, resources=replace(tile.resources, channels=channels))
        else:
            memory = next(m for m in tile.resources.memories if m.resource_id == tile.scratch_id)
            if case == "sram_clock_div10":
                memory = replace(memory, clock=replace(memory.clock, frequency_hz=memory.clock.frequency_hz / 10))
            else:
                memory = replace(memory, sram=replace(memory.sram, bank_count=1,
                                  words_per_bank=memory.sram.bank_count * memory.sram.words_per_bank))
            tile = replace(tile, resources=replace(tile.resources, memories=tuple(
                memory if m.resource_id == tile.scratch_id else m for m in tile.resources.memories)))
        channel = next(c for c in tile.resources.channels if c.resource_id == backend.channel_id)
        hardware = replace(hardware, mac=tile.mac, compute_clock=tile.compute_clock, dma=channel.params,
                           dma_clock=channel.clock, tile_backend=replace(backend, tile=tile))
        result.append((case, replace(study, hardware=hardware)))
    return tuple(result)


# 保存所有成功/失败运行的显式名单；回读缺少任一 bundle 时失败，避免静默缩小比较集。
def write_comparison(directory: Path, panels: tuple[tuple[str, tuple[RunRecord, ...]], ...]) -> None:
    directory.mkdir(parents=True, exist_ok=False)
    entries = []
    for case, records in panels:
        for record in records:
            write_run(record, directory / record.run_id)
            entries.append({"case": case, "candidate": record.spec.experiment_id, "run_id": record.run_id})
    (directory / "comparison.json").write_text(canonical_json({"schema": "digital-tile-comparison/v1", "entries": entries}) + "\n",
                                               encoding="utf-8")


# 只读取有校验的不可变记录，验证候选/运行身份和各资源消融的同输入条件。
def read_comparison(directory: Path) -> tuple[tuple[str, tuple[RunRecord, ...]], ...]:
    manifest = parse_json((directory / "comparison.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or set(manifest) != {"schema", "entries"} or manifest["schema"] != "digital-tile-comparison/v1":
        raise ValueError("invalid digital tile comparison manifest")
    if not isinstance(manifest["entries"], list) or not manifest["entries"]:
        raise ValueError("comparison needs a complete run roster")
    groups, ids, identities, inputs = {}, set(), set(), set()
    for entry in manifest["entries"]:
        if not isinstance(entry, dict) or set(entry) != {"case", "candidate", "run_id"}:
            raise ValueError("invalid comparison entry")
        case, candidate, run_id = entry["case"], entry["candidate"], entry["run_id"]
        if any(type(value) is not str or not value.strip() for value in (case, candidate, run_id)):
            raise ValueError("invalid comparison identity")
        if len(run_id) != 32 or any(c not in "0123456789abcdef" for c in run_id):
            raise ValueError("invalid run_id path")
        if run_id in ids or (case, candidate) in identities:
            raise ValueError("duplicate comparison entry")
        record = RunRecord.from_dict(read_run(directory / run_id))
        if (record.run_id, record.spec.experiment_id, record.spec.implementation_id) != (run_id, candidate, "linear-tile-analysis/v1"):
            raise ValueError("comparison record identity mismatch")
        ids.add(run_id)
        identities.add((case, candidate))
        inputs.add(record.inputs_json)
        groups.setdefault(case, []).append(record)
    rosters = {tuple(r.spec.experiment_id for r in records) for records in groups.values()}
    if len(rosters) != 1 or len(inputs) != 1:
        raise ValueError("sensitivity panels must preserve candidates and inputs")
    return tuple((case, tuple(records)) for case, records in groups.items())


# 默认输出全部六组实验；主比较与资源改变分组展示，宿主时间仅留在 RunRecord。
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "config/experiments/digital_tile.json")
    parser.add_argument("--source-revision", default="unrecorded")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--read", type=Path)
    args = parser.parse_args()
    if args.read is not None:
        if args.output is not None:
            parser.error("--read cannot be combined with --output")
        panels = read_comparison(args.read)
    else:
        panels = tuple((case, run_study(study, source_revision=args.source_revision))
                       for case, study in sensitivity_studies(load_config(LinearStudy, args.config)))
        if args.output is not None:
            write_comparison(args.output, panels)
    summaries = tuple({"case": case, "rows": summarize_records(records)} for case, records in panels)
    print(canonical_json(summaries))
    return max(comparison_exit_status(panel["rows"]) for panel in summaries)


if __name__ == "__main__":
    raise SystemExit(main())

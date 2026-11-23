"""Offline extraction of two pinned Nangate45 cells; not a general Liberty/LEF parser."""

import argparse
from dataclasses import replace
from decimal import Decimal
import hashlib
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]  # Repository imports; tool never executes source expressions.
sys.path.insert(0, str(ROOT))

from contracts.versions.json_codec import canonical_json
from costmodel.interfaces.costs import CostKey, CostPoint, CostSource, OperatingPoint
from costmodel.providers.tabulated.lookup import CostTable

REVISION = "82ac25be57125cc724388ef89f01ce65f9ba3dcc"  # Fixed OpenROAD-flow-scripts source commit.
LIB_SHA256 = "8d540a4d4cf6d09d27c87ad067857a9c0c2eeb023ab7a56e058cd3113db4e9b1"  # Raw Liberty bytes.
LEF_SHA256 = "a43aea339f12a57a63497783e508ba16f3da2dc056d3247dec7d99707c2dedef"  # Raw macro LEF bytes.


# Accept only the audited byte-identical artifacts; future libraries need a reviewed extraction update.
def extract_table(lib_path: Path, lef_path: Path) -> CostTable:
    lib_data, lef_data = lib_path.read_bytes(), lef_path.read_bytes()
    if hashlib.sha256(lib_data).hexdigest() != LIB_SHA256 or hashlib.sha256(lef_data).hexdigest() != LEF_SHA256:
        raise ValueError("source artifact hash mismatch")
    lib, lef = lib_data.decode("utf-8"), lef_data.decode("utf-8")
    if not re.search(r'leakage_power_unit\s*:\s*"1nW"', lib):
        raise ValueError("unsupported leakage unit")
    for field, expected in (("nom_voltage", Decimal("1.1")), ("nom_temperature", Decimal("25")), ("nom_process", Decimal("1"))):
        match = re.search(field + r"\s*:\s*([\d.]+)", lib)
        if match is None or Decimal(match.group(1)) != expected:
            raise ValueError("source operating point mismatch")
    base = f"https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/blob/{REVISION}/flow/platforms/nangate45/"
    limits = ("Library characterization, not fabricated-device measurement or independent calibration",
              "Only named standard cells at typical/TypTyp 1.1 V, 25 C; no MAC/SRAM or process scaling",
              "No dynamic energy, routing/clock/power-network area, activity-state leakage weighting or error bound")
    area_source = CostSource(source_id="nangate45-lef-typical", kind="characterization", reference=base + "lef/NangateOpenCellLibrary.macro.mod.lef",
        revision=REVISION, artifact_sha256=LEF_SHA256, extraction="LEF SIZE in micrometers: W*H/1e6 gives mm2; verified against Liberty area", limitations=limits)
    leakage_source = replace(area_source, source_id="nangate45-lib-typical", reference=base + "lib/NangateOpenCellLibrary_typical.lib",
        artifact_sha256=LIB_SHA256, extraction="Explicit cell_leakage_power * 1e-9 W; library scalar, not workload-state weighted leakage")
    condition = OperatingPoint(process="NangateOpenCellLibrary/FreePDK45/TypTyp", voltage_v=1.1, temperature_k=298.15)
    points = []
    for name in ("INV_X1", "NAND2_X1"):
        cell = re.search(r"cell\s*\(" + name + r"\)\s*\{(.*?)(?=\n  cell\s*\(|\Z)", lib, re.S).group(1)
        macro = re.search(r"MACRO " + name + r"\s+(.*?)\nEND " + name, lef, re.S).group(1)
        width, height = re.search(r"SIZE\s+([\d.]+)\s+BY\s+([\d.]+)", macro).groups()
        area = Decimal(width) * Decimal(height)
        if area != Decimal(re.search(r"\barea\s*:\s*([\d.]+)", cell).group(1)):
            raise ValueError("Liberty/LEF area disagreement")
        leakage = Decimal(re.search(r"\bcell_leakage_power\s*:\s*([\d.]+)", cell).group(1))
        key = CostKey(structure_id="Nangate45/" + name + "/revision1.0", operating_point=condition, metric="area")
        points.append(CostPoint(key=key, value=float(area / Decimal(10**6)), source=area_source,
                               coverage=f"One {name} cell footprint only; excludes placed-design whitespace and infrastructure"))
        points.append(CostPoint(key=replace(key, metric="leakage"), value=float(leakage / Decimal(10**9)), source=leakage_source,
                               coverage=f"One {name} library scalar cell_leakage_power; excludes dynamic/internal/switching energy"))
    return CostTable(table_id="nangate45-two-cells-typical/v1", points=tuple(points))


# Read local pinned files and write a new data-only table; no network or external simulator runs here.
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lib", type=Path, required=True)
    parser.add_argument("--lef", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    table = extract_table(args.lib, args.lef)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(canonical_json(table) + "\n")
    print(f"Verified 2 cells, 4 conditional cost points: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

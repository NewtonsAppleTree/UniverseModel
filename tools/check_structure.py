"""Check scaffold consistency; this is not a hardware or simulation validator."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zipfile import BadZipFile, ZipFile


ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []


def require(condition: bool, message: str) -> None:
    if not condition:
        ERRORS.append(message)


def read_json(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def check_dag(graph: dict[str, list[str]], label: str) -> None:
    active, done = set(), set()

    def visit(node):
        if node in active:
            ERRORS.append(f"{label}: cycle through {node}")
            return
        if node in done:
            return
        active.add(node)
        for child in graph.get(node, []):
            if child not in graph:
                ERRORS.append(f"{label}: {node} references unknown {child}")
            else:
                visit(child)
        active.remove(node)
        done.add(node)

    for node in graph:
        visit(node)


def index_unique(items, label):
    index = {}
    for item in items:
        key = item["id"]
        require(key not in index, f"{label}: duplicate ID {key}")
        index[key] = item
    return index


def check_modules() -> int:
    manifest = read_json("docs/architecture/modules.json")
    require(manifest["schema_version"] == 1, "Unsupported modules manifest version")
    modules = index_unique(manifest["modules"], "modules")
    for name, module in modules.items():
        require(module["path"] == name, f"{name}: module path does not match ID")
        base = ROOT / module["path"]
        for directory in module["subdirectories"]:
            require((base / directory).is_dir(), f"{name}: missing directory {directory}")
        for path in (base / "README.md", ROOT / module["design"]):
            require(path.is_file(), f"{name}: missing {path.relative_to(ROOT)}")
        require(len(module["allowed_dependencies"]) == len(set(module["allowed_dependencies"])),
                f"{name}: duplicate dependency")
    check_dag({key: value["allowed_dependencies"] for key, value in modules.items()}, "module dependencies")
    return len(modules)


def check_markdown() -> int:
    count = 0
    excluded = {".git", ".build", ".venv", "__pycache__", "node_modules"}
    for path in ROOT.rglob("*.md"):
        if excluded.intersection(path.relative_to(ROOT).parts):
            continue
        count += 1
        text = path.read_text(encoding="utf-8")
        require("\ufffd" not in text, f"{path.relative_to(ROOT)}: replacement character")
        # Only local inline file targets are checked; headings and remote sites are not.
        for target in re.findall(r"\[[^\]\n]+\]\(([^)\n]+)\)", text):
            target = target.strip().strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            destination = (path.parent / unquote(parsed.path)).resolve()
            require(destination.exists(), f"{path.relative_to(ROOT)}: missing link {target}")
    return count


def check_example() -> None:
    spec = read_json("example/specs/heterogeneous_topology.json")
    require(spec["schema_version"] == "illustrative-topology/v1", "example: unsupported version")
    require(spec["executable"] is False, "example: must be marked non-executable")
    items = index_unique(spec["instances"], "example instances")
    roots = [key for key, item in items.items() if item["parent"] is None]
    require(len(roots) == 1, "example: expected one containment root")
    check_dag({key: [item["parent"]] if item["parent"] is not None else []
               for key, item in items.items()}, "example containment")
    ports = index_unique(spec["ports"], "example ports")
    for key, port in ports.items():
        require(port["owner"] in items, f"example port {key}: missing owner")
    links = index_unique(spec["connections"], "example links")
    for key, link in links.items():
        require(len(link["endpoints"]) == 2 and len(set(link["endpoints"])) == 2,
                f"example link {key}: expected two different endpoints")
        for endpoint in link["endpoints"]:
            require(endpoint in ports, f"example link {key}: missing port {endpoint}")
    views = index_unique(spec["device_views"], "example device views")
    for key, view in views.items():
        require(bool(view["members"]) and len(view["members"]) == len(set(view["members"])),
                f"example view {key}: empty or duplicate members")
        for member in view["members"]:
            require(member in items, f"example view {key}: missing member {member}")
    stacks = index_unique(spec["stacks"], "example stacks")
    stacked_dies = set()
    for key, stack in stacks.items():
        package = items.get(stack["package"], {})
        require(package.get("kind") == "package", f"example stack {key}: invalid package")
        dies = stack["dies_bottom_to_top"]
        require(len(dies) >= 2, f"example stack {key}: expected at least two dies")
        for die in dies:
            item = items.get(die, {})
            require(item.get("kind") == "die" and item.get("parent") == stack["package"],
                    f"example stack {key}: die {die} is outside its package")
            require(die not in stacked_dies, f"example stack {key}: die {die} used twice")
            stacked_dies.add(die)
    ranks = index_unique(spec["ranks"], "example ranks")
    for key, rank in ranks.items():
        require(rank["device_view"] in views, f"example rank {key}: missing device view")
    groups = index_unique(spec["groups"], "example groups")
    for key, group in groups.items():
        require(bool(group["ranks"]) and len(group["ranks"]) == len(set(group["ranks"])),
                f"example group {key}: empty or duplicate ranks")
        for rank in group["ranks"]:
            require(rank in ranks, f"example group {key}: missing rank {rank}")


def check_docx_sources() -> int:
    profiles = read_json("docs/tools/documents.json")
    for name, profile in profiles.items():
        source = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in profile["sources"])
        expected = "Markdown source SHA256: " + hashlib.sha256(source.encode("utf-8")).hexdigest()
        document = ROOT / "docs" / profile["filename"]
        if not document.is_file():
            ERRORS.append(f"{name}: missing Word output")
            continue
        with ZipFile(document) as archive:
            props = ET.fromstring(archive.read("docProps/core.xml"))
            actual = props.findtext("{http://purl.org/dc/elements/1.1/}description")
        require(actual == expected, f"{name}: stale Word output; rebuild with docs/tools/build_docx.py --document {name}")
    return len(profiles)


def main() -> int:
    try:
        module_count = check_modules()
        markdown_count = check_markdown()
        check_example()
        document_count = check_docx_sources()
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError, BadZipFile) as exc:
        ERRORS.append(f"Malformed or unreadable input: {exc}")
    if ERRORS:
        for error in ERRORS:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: {module_count} modules, dependency DAG, {markdown_count} Markdown files, "
          f"structural example, {document_count} DOCX source hashes.")
    print("Scope: scaffold consistency only; no functional or performance claims.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

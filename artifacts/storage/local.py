"""Small immutable local run bundle; manifest is the final commit marker, not a resume checkpoint."""

from hashlib import sha256
from pathlib import Path

from contracts.results.experiment import RunRecord
from contracts.versions.json_codec import canonical_json, parse_json


# Create a new directory, write one self-contained run, then commit its byte hash; existing runs are immutable.
def write_run(record: RunRecord, directory: str | Path) -> Path:
    if not isinstance(record, RunRecord):
        raise TypeError("record must be RunRecord")
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=False)
    data = (canonical_json(record.to_dict()) + "\n").encode("utf-8")
    with (target / "run.json").open("xb") as handle:
        handle.write(data)
    manifest = {"schema_version": "universal-manifest/v1", "run_id": record.run_id,
                "identity_hash": record.identity_hash, "status": record.status,
                "artifact": {"path": "run.json", "byte_length": len(data), "sha256": sha256(data).hexdigest()}}
    with (target / "manifest.json").open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(canonical_json(manifest) + "\n")
    return target


# Verify committed bytes and experiment identity before returning a fresh view; incomplete bundles fail.
def read_run(directory: str | Path) -> dict[str, object]:
    target = Path(directory)
    manifest = parse_json((target / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "universal-manifest/v1":
        raise ValueError("unsupported manifest schema_version")
    artifact = manifest.get("artifact")
    if not isinstance(artifact, dict) or artifact.get("path") != "run.json":
        raise ValueError("manifest must reference the local run.json artifact")
    data = (target / "run.json").read_bytes()
    if artifact.get("byte_length") != len(data) or artifact.get("sha256") != sha256(data).hexdigest():
        raise ValueError("run artifact size or SHA256 mismatch")
    result = parse_json(data.decode("utf-8"))
    if not isinstance(result, dict) or result.get("schema_version") != "universal-run/v1":
        raise ValueError("unsupported run schema_version")
    for key in ("run_id", "identity_hash", "status"):
        if result.get(key) != manifest.get(key):
            raise ValueError(f"manifest and run disagree on {key}")
    return RunRecord.from_dict(result).to_dict()

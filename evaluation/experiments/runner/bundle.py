"""Small shared immutable study index; callers supply explicit semantic validation."""

from pathlib import Path
from typing import Callable

from artifacts.storage.local import read_run, write_run
from contracts.results.experiment import RunRecord
from contracts.versions.json_codec import canonical_json, parse_json


# Validate a complete study, then write immutable runs before committing its index.
def write_records(records: tuple[RunRecord, ...], directory: str | Path, schema: str, validate: Callable) -> Path:
    validate(records)
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=False)
    entries = []
    for i, record in enumerate(sorted(records, key=lambda r: r.spec.experiment_id)):
        name = f'run-{i:04d}'
        write_run(record, target/name)
        entries.append({'directory': name, 'run_id': record.run_id, 'identity_hash': record.identity_hash})
    with (target/'index.json').open('x', encoding='utf-8') as handle:
        handle.write(canonical_json({'schema_version': schema, 'runs': entries})+'\n')
    return target


# Read only fixed local run names and verify complete semantics without executing producers.
def read_records(directory: str | Path, schema: str, validate: Callable) -> tuple[RunRecord, ...]:
    target = Path(directory)
    index = parse_json((target/'index.json').read_text(encoding='utf-8'))
    if not isinstance(index, dict) or set(index) != {'schema_version', 'runs'} or index['schema_version'] != schema:
        raise ValueError('invalid study index schema')
    if not isinstance(index['runs'], list) or not index['runs']:
        raise ValueError('study index requires nonempty runs')
    records = []
    for i, entry in enumerate(index['runs']):
        if not isinstance(entry, dict) or set(entry) != {'directory', 'run_id', 'identity_hash'} or entry['directory'] != f'run-{i:04d}':
            raise ValueError('invalid study run path/order')
        record = RunRecord.from_dict(read_run(target/entry['directory']))
        if (record.run_id, record.identity_hash) != (entry['run_id'], entry['identity_hash']):
            raise ValueError('study index/run identity mismatch')
        records.append(record)
    validate(tuple(records))
    return tuple(records)

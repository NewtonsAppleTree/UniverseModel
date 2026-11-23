"""CH1–CH10默认研究夹具的完整保存/回读验收；不替代单元测试或物理校准。"""

import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]  # 当前checkout；所有子进程使用同一解释器和显式模块入口。
SOURCE_ROOTS = ('chipmodel', 'contracts', 'configuration', 'evaluation', 'compiler', 'workloads',
                'artifacts', 'clustermodel', 'systemmodel', 'runtime', 'simulator', 'costmodel',
                'ui', 'example', 'tests', 'tools')  # 源码身份覆盖生产、实验、测试和工具，不含第三方树。
STUDIES = {
    'digital_tile': (24, {'infeasible_full': 6}),
    'cim': (7, {'hold_expires': 1, 'hold_too_small': 1}),
    'compute': (16, {'cpu_wrong_uop': 1, 'npu_undeclared_format': 1, 'npu_wrong_accumulator': 1}),
    'memory': (21, {'cache_out_of_backing': 1, 'dram_cross_rejected': 1, 'dram_write_rejected': 1, 'nand_oob_rejected': 1}),
    'assembly': (16, {'d2d_capacity_rejected': 1, 'd2d_path_rejected': 1, 'shared_overlap_rejected': 1, 'unknown_dependency_rejected': 1}),
    'physical': (20, {'stdcell_outside_rejected': 1, 'stdcell_overlap_rejected': 1, 'thermal_scope_rejected': 1}),
}  # 固定默认配置的案例数与预期失败次数；变更夹具时需同步审查，不能自动接受当前失败。


# 对原始字节计算SHA256，避免换行规范化隐藏源码或产物变化。
def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# 保存当前实际Python/config字节身份，未提交文件也覆盖；host环境不作为目标性能。
def source_snapshot() -> dict:
    files = {}
    for directory in SOURCE_ROOTS:
        for path in (ROOT / directory).rglob('*.py'):
            relative = path.relative_to(ROOT)
            if any(p.startswith('.') or p == '__pycache__' for p in relative.parts) or 'compiler/3rdparty/' in relative.as_posix():
                continue
            files[relative.as_posix()] = digest(path)
    for path in (*sorted((ROOT / 'config').rglob('*.json')), ROOT / 'pyproject.toml'):
        files[path.relative_to(ROOT).as_posix()] = digest(path)
    combined = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    return {'source_revision': f'{head}+python-config-sha256:{combined}', 'files': files,
            'python': sys.version, 'executable': sys.executable, 'platform': platform.platform(),
            'scope': 'project Python + config JSON + pyproject; excludes docs/build/compiler third-party'}


# 检查默认夹具的完整名单/失败数；预期失败变成成功同样需要审查。
def check_rows(name: str, rows: list) -> dict:
    flat = [r for panel in rows for r in panel['rows']] if name == 'digital_tile' else rows
    expected_count, expected_failures = STUDIES[name]
    failures = {}
    if len(flat) != expected_count:
        raise ValueError(f'{name}: incomplete default fixture roster')
    for row in flat:
        if row['status'] not in ('succeeded', 'failed'):
            raise ValueError(f'{name}: unfinished case')
        if row['status'] == 'failed':
            key = row.get('candidate', row.get('case'))
            failures[key] = failures.get(key, 0) + 1
            if not row['diagnostic']:
                raise ValueError(f'{name}: failure requires diagnostic')
    if failures != expected_failures:
        raise ValueError(f'{name}: unexpected success/failure roster: {failures}')
    return {'cases': len(flat), 'succeeded': len(flat) - sum(failures.values()), 'expected_failures': failures}


# 以排他的文件创建保存JSON；失败产物保留，不覆盖既有证据。
def write_json(path: Path, value: object) -> None:
    with path.open('x', encoding='utf-8') as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n')


# 调用固定CLI；退出状态包含主比较数值质量检查，stderr保留用于诊断。
def invoke(name: str, arguments: list[str]) -> tuple[list, dict]:
    command = [sys.executable, '-m', f'example.{name}_demo', *arguments]
    started = time.perf_counter()
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    if result.returncode:
        raise ValueError(f'{name} exited {result.returncode}: {result.stderr}\n{result.stdout}')
    return json.loads(result.stdout), {'command': command, 'exit_code': result.returncode,
                                      'host_elapsed_s': time.perf_counter() - started, 'stderr': result.stderr}


# 所有证据文件形成完整原始字节清单；拒绝逃出证据目录的链接。
def artifact_hashes(target: Path) -> dict:
    result = {}
    for path in sorted(target.rglob('*')):
        if path.is_file() and path != target / 'acceptance.json':
            if not path.resolve().is_relative_to(target.resolve()):
                raise ValueError('artifact escapes evidence directory')
            result[path.relative_to(target).as_posix()] = digest(path)
    return result


# 回读哈希和每组bundle，不调用run_study；保存的源码身份保持原值，不冒称当前版本。
def verify_saved(target: Path) -> dict:
    report = json.loads((target / 'acceptance.json').read_text(encoding='utf-8'))
    if report['schema'] != 'chipmodel-acceptance/v1' or set(report['studies']) != set(STUDIES):
        raise ValueError('invalid chipmodel acceptance report')
    if artifact_hashes(target) != report['artifacts']:
        raise ValueError('artifact hash or complete file roster mismatch')
    source = json.loads((target / 'source.json').read_text(encoding='utf-8'))
    if source['source_revision'] != report['source_revision']:
        raise ValueError('source identity mismatch')
    for name in STUDIES:
        saved = json.loads((target / f'{name}_summary.json').read_text(encoding='utf-8'))
        rows, _ = invoke(name, ['--read', str(target / name)])
        if rows != saved or check_rows(name, rows) != report['studies'][name]:
            raise ValueError(f'{name}: saved summary differs from complete bundles')
    return report


# 一次默认验收生成完整来源/六组案例/回读证明，最后写报告作为完成标记。
def run_acceptance(target: Path) -> dict:
    target.mkdir(parents=True, exist_ok=False)
    source = source_snapshot()
    write_json(target / 'source.json', source)
    studies, commands = {}, []
    for name in STUDIES:
        rows, run = invoke(name, ['--source-revision', source['source_revision'], '--output', str(target / name)])
        write_json(target / f'{name}_summary.json', rows)
        restored, read = invoke(name, ['--read', str(target / name)])
        if rows != restored:
            raise ValueError(f'{name}: run/read mismatch')
        studies[name] = check_rows(name, rows)
        commands.extend((run, read))
    if source_snapshot()['files'] != source['files']:
        raise ValueError('source changed during acceptance')
    write_json(target / 'commands.json', commands)
    report = {'schema': 'chipmodel-acceptance/v1', 'source_revision': source['source_revision'],
              'studies': studies, 'artifacts': artifact_hashes(target),
              'evidence': 'functional/analytical/static-policy fixture regression; no hardware calibration'}
    write_json(target / 'acceptance.json', report)
    return report


# 只选运行或回读；目录相对当前调用位置解析，脚本不删除文件或修改Git索引。
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--output', type=Path)
    choice.add_argument('--read', type=Path)
    args = parser.parse_args()
    try:
        report = verify_saved(args.read.resolve()) if args.read else run_acceptance(args.output.resolve())
    except (ValueError, TypeError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        print(f'chipmodel acceptance failed: {exc}', file=sys.stderr)
        return 1
    print(json.dumps({key: value for key, value in report.items() if key != 'artifacts'}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

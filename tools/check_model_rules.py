"""检查 chipmodel 注释与目录文档；由代码生成 UNITS.md 参数/接口表。"""

import argparse
import ast
from io import StringIO
from pathlib import Path
import re
import tokenize


ROOT = Path(__file__).resolve().parents[1]  # 仓库根目录。
MODEL_ROOT = ROOT / "chipmodel"  # 当前纳入强制检查的模块。
START = "<!-- model-fields:start -->"  # 自动维护区起始标记。
END = "<!-- model-fields:end -->"  # 自动维护区结束标记。


# 找定义/装饰器前连续的 # 注释；docstring 不替代用户要求的前置说明。
def preceding_note(node: ast.AST, lines: list[str]) -> str:
    start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])]) - 2
    notes = []
    while start >= 0 and lines[start].lstrip().startswith("#"):
        notes.append(lines[start].lstrip()[1:].strip())
        start -= 1
    return " ".join(reversed(notes))


# Markdown 表格中的竖线和换行需要转义，保留专业名称和公式原文。
def cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


# 区分只读 property 与普通方法，文档不能把属性展示成需要调用的函数。
def is_property(node: ast.AST) -> bool:
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
        isinstance(decorator, ast.Name) and decorator.id == "property" for decorator in node.decorator_list)


# 读取一个 Python 文件的定义、字段行尾说明和公开接口，不导入模型或执行代码。
def inspect_source(path: Path) -> tuple[list[str], list[str], list[str]]:
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source, filename=str(path))
    comments = {t.start[0]: t.string[1:].strip() for t in tokenize.generate_tokens(StringIO(source).readline)
                if t.type == tokenize.COMMENT}
    errors, fields, interfaces = [], [], []
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if not preceding_note(node, lines):
                errors.append(f"{path.relative_to(ROOT)}:{node.lineno}: {node.name} lacks a preceding # note")
        if isinstance(node, ast.ClassDef):
            for declaration in node.body:
                if isinstance(declaration, ast.AnnAssign) and isinstance(declaration.target, ast.Name):
                    name = declaration.target.id
                    note = comments.get(declaration.lineno, "")
                    annotation = ast.unparse(declaration.annotation)
                    if not note:
                        errors.append(f"{path.relative_to(ROOT)}:{declaration.lineno}: {node.name}.{name} lacks field note")
                elif is_property(declaration):
                    name = declaration.name
                    note = "只读派生属性；" + preceding_note(declaration, lines)
                    annotation = ast.unparse(declaration.returns) if declaration.returns else "未声明"
                else:
                    continue
                units = re.findall(r"\[([^\[\]]+)\]", note)
                unit = (units[-1] if units else "1（布尔）" if annotation == "bool"
                        else "1（标识/枚举）" if "str" in annotation else "—（结构/对象）")
                fields.append(f"| `{node.name}` | `{name}` | `{cell(annotation)}` | "
                              f"{cell(unit)} | {cell(note)} |")
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            interfaces.append(f"| `{node.name}` | {cell(preceding_note(node, lines))} |")
            for method in node.body:
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and not method.name.startswith("_"):
                    signature = method.name if is_property(method) else f"{method.name}({cell(ast.unparse(method.args))})"
                    interfaces.append(f"| `{node.name}.{signature}` | "
                                      f"{cell(preceding_note(method, lines))} |")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            interfaces.append(f"| `{node.name}({cell(ast.unparse(node.args))})` | {cell(preceding_note(node, lines))} |")
    return errors, fields, interfaces


# 仅生成当前目录的字段/接口索引；父目录用手写导航解释系统关系。
def generated_section(directory: Path) -> tuple[str, list[str]]:
    sections, errors = [], []
    for path in sorted(directory.glob("*.py")):
        file_errors, fields, interfaces = inspect_source(path)
        errors.extend(file_errors)
        sections.append(f"### [{path.name}]({path.name})\n")
        if fields:
            sections.extend(["| Unit / 数据对象 | 参数 / 属性 | Python 类型 | 单位 | 专业含义 / 关系 |",
                             "| --- | --- | --- | --- | --- |", *fields, ""])
        if interfaces:
            sections.extend(["| 类型 / 接口 | 用途、公式与边界 |", "| --- | --- |", *interfaces, ""])
    return "\n".join(sections).rstrip(), errors


# 遍历 chipmodel 的每个模块目录，检查手写说明存在并核对自动字段表是否与源码一致。
def check(*, write_docs: bool = False) -> list[str]:
    errors = []
    directories = [MODEL_ROOT] + sorted(p for p in MODEL_ROOT.rglob("*") if p.is_dir()
                                       and not any(part.startswith(".") or part == "__pycache__"
                                                   for part in p.relative_to(MODEL_ROOT).parts))
    for directory in directories:
        document = directory / "UNITS.md"
        if not document.exists():
            errors.append(f"{document.relative_to(ROOT)}: missing module unit document")
            continue
        text = document.read_text(encoding="utf-8")
        if text.count(START) != 1 or text.count(END) != 1 or text.index(START) > text.index(END):
            errors.append(f"{document.relative_to(ROOT)}: invalid model-fields markers")
            continue
        generated, source_errors = generated_section(directory)
        errors.extend(source_errors)
        prefix, rest = text.split(START, 1)
        _, suffix = rest.split(END, 1)
        expected = prefix + START + "\n\n" + generated + "\n\n" + END + suffix
        if text != expected:
            if write_docs:
                document.write_text(expected, encoding="utf-8", newline="\n")
            else:
                errors.append(f"{document.relative_to(ROOT)}: stale field table; run with --write-docs")
    return errors


# CLI 只在 --write-docs 时更新字段表；默认模式用于 CI，缺注释/文档时返回非零状态。
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-docs", action="store_true", help="refresh generated field/interface tables")
    args = parser.parse_args()
    errors = check(write_docs=args.write_docs)
    for error in errors:
        print(f"ERROR: {error}")
    if not errors:
        print("OK: chipmodel definition notes, field notes, per-directory UNITS.md and source-derived tables.")
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())

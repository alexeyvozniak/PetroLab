from pathlib import Path
import ast

path = Path("petrolab/sources.py")
text = path.read_text(encoding="utf-8")
tree = ast.parse(text)

edits = []
for node in ast.walk(tree):
    if not isinstance(node, ast.Call):
        continue
    func = node.func
    if not (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "openpyxl"
        and func.attr == "load_workbook"
    ):
        continue
    if any(keyword.arg == "keep_vba" for keyword in node.keywords):
        continue
    if not node.args:
        raise SystemExit("openpyxl.load_workbook call without positional path")
    arg = ast.get_source_segment(text, node.args[0])
    if not arg:
        raise SystemExit("could not recover load_workbook path expression")
    segment = ast.get_source_segment(text, node)
    if not segment or not segment.endswith(")"):
        raise SystemExit("could not recover load_workbook call")
    replacement = segment[:-1] + f', keep_vba=Path({arg}).suffix.lower() == ".xlsm")'
    edits.append((node.lineno, node.col_offset, node.end_lineno, node.end_col_offset, segment, replacement))

if not edits:
    if "keep_vba=" in text:
        print("all load_workbook calls already preserve VBA")
        raise SystemExit(0)
    raise SystemExit("no openpyxl.load_workbook calls found")

# Convert AST locations to character offsets and apply backwards.
lines = text.splitlines(keepends=True)
offsets = [0]
for line in lines:
    offsets.append(offsets[-1] + len(line))

def absolute(line, col):
    return offsets[line - 1] + col

for lineno, col, end_lineno, end_col, segment, replacement in sorted(edits, key=lambda x: (x[0], x[1]), reverse=True):
    start = absolute(lineno, col)
    end = absolute(end_lineno, end_col)
    if text[start:end] != segment:
        raise SystemExit("AST/source mismatch while patching load_workbook")
    text = text[:start] + replacement + text[end:]

if "from pathlib import Path" not in text:
    marker = "from __future__ import annotations\n\n"
    text = text.replace(marker, marker + "from pathlib import Path\n", 1)

path.write_text(text, encoding="utf-8")
print(f"patched {len(edits)} load_workbook call(s) for XLSM VBA preservation")

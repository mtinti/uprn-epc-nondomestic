"""Probe for the response to docs/reviews/2026-11-14-nondomestic-implementation-review.md.

It runs the real build on synthetic input and the notebook's own length helper, and asserts
that text is now measured in UTF-16 code units, the unit of an nvarchar(n) and of DATALENGTH / 2.
It writes only inside a temporary folder and does not connect to SQL Server: the two container
probes do that part (docs/sql/SQLSERVER_PROBE_2026-11-14.md, NOTEBOOK_PROBE_2026-11-14.md).

    python3 -B docs/reviews/2026-11-14-nondomestic-implementation-review-response-probe.py
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

import nbformat
import pandas as pd

from synthetic import default_rows, make_release
from epc_nd_ingest import pipeline
from epc_nd_ingest.core.checks import BuildStopped

BUILDING = "\U0001F3E2"   # outside the Basic Multilingual Plane: one character, two UTF-16 code units
units = lambda v: len(v.encode("utf-16-le")) // 2


def build(rows):
    root = Path(tempfile.mkdtemp())
    registry = make_release(root, rows=rows)
    return pipeline.build(results=root / "results", registry_path=registry, source_root=root / "sources", log=lambda *a: None)


def with_cell(column, value):
    rows = default_rows()
    rows[0][column] = value
    return rows


print("== 1. A bounded column, ADDRESS1, nvarchar(100)")
for letters in (98, 99):
    value = "A" * letters + BUILDING
    try:
        m = build(with_cell("ADDRESS1", value))
        outcome = f"builds, longest recorded {m['observations']['table']['longest_text_per_column']['ADDRESS1']}"
    except BuildStopped as stop:
        outcome = "stopped: " + str(stop).split("first: ")[1]
    print(f"  {letters} letters and one supplementary character: {len(value)} characters, {units(value)} units: {outcome}")
    assert (units(value) <= 100) == outcome.startswith("builds") and ("extract.text_within_width" in outcome) == (units(value) > 100)

print("== 2. The nvarchar(max) column, IMPROVEMENT_RECOMMENDATIONS, width 8,000")
value = "x" * 4450 + BUILDING
obs = build(with_cell("IMPROVEMENT_RECOMMENDATIONS", value))["observations"]["table"]
print(f"  4,450 letters and one supplementary character: {len(value)} characters, {units(value)} units, longest recorded "
      f"{obs['longest_text_per_column']['IMPROVEMENT_RECOMMENDATIONS']}, cells with such a character {obs['cells_with_supplementary_character']}")
assert obs["longest_text_per_column"]["IMPROVEMENT_RECOMMENDATIONS"] == units(value) == 4452
for letters in (7998, 7999):
    value = "x" * letters + BUILDING
    try:
        build(with_cell("IMPROVEMENT_RECOMMENDATIONS", value)); outcome = "builds"
    except BuildStopped as stop:
        outcome = "stopped: " + str(stop).split("first: ")[1]
    print(f"  {letters} letters and one: {units(value)} units: {outcome}")
    assert (units(value) <= 8000) == (outcome == "builds")

print("== 3. The notebook's own helper, taken from the generated notebook")
nb = nbformat.read(ROOT / "loader" / "upload_epc_nondomestic.ipynb", as_version=4)
step4 = next(c.source for c in nb.cells if c.cell_type == "code" and c.source.startswith("# Step 4 "))
start = step4.index('SUPPLEMENTARY = "')
helper = {}
exec(step4[start:step4.index("\n\n", start)], helper)
values = ["abc", "A" * 99 + BUILDING, "x" * 4450 + BUILDING, BUILDING * 3, "Steòrnabhagh", "caf�"]
got = helper["sql_length"](pd.Series(values)).tolist()
print("  characters", [len(v) for v in values])
print("  notebook   ", got)
print("  UTF-16     ", [units(v) for v in values])
assert got == [units(v) for v in values]
# What step 4 now does with them: the limit check and the length it will compare with DATALENGTH / 2.
assert "lengths = sql_length(chunk[col])" in step4 and "int(sql_length(chunk[col]).max())" in step4
assert ".str.len() > limit" not in step4 and "chunk[col].str.len().max()" not in step4
print("  step 4 uses the helper for the limit of a bounded column and for the longest value sent")

print("== 4. The real release")
m = json.loads((ROOT / "results" / "manifest.json").read_text())
o = m["observations"]["table"]
print(f"  cells with a supplementary character: {o['cells_with_supplementary_character'] or 'none'}; CSV SHA256 {m['csv']['sha256'][:16]}, digest {m['csv']['digest']['total']}")
assert o["cells_with_supplementary_character"] == {} and m["csv"]["sha256"].startswith("d43cd944e613c67e")
print("all assertions passed")

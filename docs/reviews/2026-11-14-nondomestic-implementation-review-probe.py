"""Reproduce the Unicode length mismatch without connecting to SQL Server.

Run with the project's Python environment. Only temporary synthetic data is written.
The SQL storage lengths are UTF-16 byte-pair counts, as documented for nvarchar.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from synthetic import make_release, make_row
from epc_nd_ingest.core.output import read_table
from epc_nd_ingest.pipeline import build


def utf16_units(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="epc-nd-unicode-review-") as folder:
        root = Path(folder)
        row = make_row(
            1,
            ADDRESS1="A" * 99 + "\U0001F3E2",
            IMPROVEMENT_RECOMMENDATIONS="x" * 4450 + "\U0001F3E2",
        )
        registry = make_release(root, rows=[row])
        manifest = build(
            results=root / "results",
            registry_path=registry,
            source_root=root / "sources",
            log=lambda *args: None,
        )
        table = read_table(root / "results" / "epc_nondomestic.parquet")
        bounded = table.at[0, "ADDRESS1"]
        long_text = table.at[0, "IMPROVEMENT_RECOMMENDATIONS"]
        assert manifest["summary"]["blocking_failed"] == 0
        assert bounded == row["ADDRESS1"] and long_text == row["IMPROVEMENT_RECOMMENDATIONS"]
        assert len(bounded) == 100 and utf16_units(bounded) == 101
        assert len(long_text) == 4451 and utf16_units(long_text) == 4452
        print(json.dumps({
            "build_checks": manifest["summary"],
            "bounded_column": {
                "name": "ADDRESS1",
                "declared_sql_type": "nvarchar(100)",
                "python_characters": len(bounded),
                "sql_storage_units_required": utf16_units(bounded),
                "fits_sql_column": utf16_units(bounded) <= 100,
            },
            "max_column": {
                "name": "IMPROVEMENT_RECOMMENDATIONS",
                "notebook_longest_sent": len(long_text),
                "datalength_divided_by_two_if_preserved": utf16_units(long_text),
                "notebook_length_comparison_would_pass": len(long_text) == utf16_units(long_text),
            },
            "sql_server_executed": False,
        }, indent=2))


if __name__ == "__main__":
    main()

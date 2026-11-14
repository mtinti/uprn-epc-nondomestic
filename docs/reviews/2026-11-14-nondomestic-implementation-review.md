# Scottish non-domestic EPC implementation review

14 November 2026. Reviewed the implementation against the revised plan: ingestion and validation, schema and export rendering, generated SQL, both loaders, the three join queries, tests, and the recorded SQL Server probes. There is no Git repository in this directory, so this reviews the current files rather than a commit diff.

**One P2 finding. The pinned 2026Q3 build passes validation and is reproducible; the finding affects accepted Unicode inputs that are absent from this release.**

1. **[P2] Measure SQL text capacity and read-back lengths in consistent units.**

   [reader.py:210](../../epc_nd_ingest/reader.py#L210) accepts strings by Python character count, while the generated bounded `nvarchar(n)` columns have capacity in UTF-16 byte pairs. A valid synthetic `ADDRESS1` consisting of 99 ASCII characters followed by U+1F3E2 passes all 44 ordinary build checks, but requires 101 units in `nvarchar(100)`. The notebook repeats the same insufficient capacity check at [make_notebook.py:364](../../loader/make_notebook.py#L364).

   The same unit mismatch also affects `nvarchar(max)`: [make_notebook.py:367](../../loader/make_notebook.py#L367) records Python character counts, then [line 394](../../loader/make_notebook.py#L394) compares them with `DATALENGTH(...)/2`. For 4,450 ASCII characters followed by U+1F3E2, those numbers are 4,451 and 4,452. Even a completely faithful load therefore fails the assertion after the rows have committed. Microsoft documents that `nvarchar(n)` measures byte pairs, with supplementary characters occupying two pairs. [Microsoft SQL Server documentation](https://learn.microsoft.com/en-us/sql/t-sql/data-types/nchar-and-nvarchar-transact-sql?view=sql-server-ver17).

   Use UTF-16 units consistently for bounded SQL capacity checks and the notebook's stored-length comparison, for example `len(value.encode("utf-16-le")) // 2`. Keep any separate character-count admission limit explicit. Regenerate the notebook and cover a supplementary character at a bounded-column boundary and inside the longest MAX value. The [saved reproducer](../../docs/reviews/2026-11-14-nondomestic-implementation-review-probe.py) runs the real build on synthetic input; it does not execute SQL Server. Its [output](../../docs/reviews/2026-11-14-nondomestic-implementation-review-probe.out) records both length discrepancies. All 45 string columns of the current Parquet were scanned: none contains a supplementary character.

Validation performed during this review:

- `python -B -m pytest -q`: **100 passed in 24.21 seconds**, including the real-release postcode query test.
- A fresh build into a temporary directory with `verify_archive=True`: **95,719 rows, 57 columns, all 46 checks passed**. The compressed CSV SHA256, Parquet SHA256 and row digest exactly match the existing manifest. The original results were not replaced.
- Regenerated the notebook into a temporary file: all **15 cell sources and cell types match** the delivered notebook.
- Reviewed the existing full-data SQL import probe and 13-scenario notebook probe records. These SQL Server probes were **not rerun** during this review. Windows `CODEPAGE = '65001'`, HIC authentication and the production load remain unverified here.

No other actionable correctness findings were identified in the reviewed scope. Implementation files and the plan were not changed.

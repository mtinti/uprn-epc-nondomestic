# Scottish non-domestic EPC implementation follow-up review

14 November 2026. Reviewed the implementation-review response, the revised length checks and observations, the regenerated notebook, and the expanded SQL Server fixtures against the earlier P2 finding.

**Verdict: no new findings. The Unicode length finding is closed.**

| Part of the finding | Verified resolution |
| --- | --- |
| A value could pass the build while exceeding a bounded SQL column | [reader.sql_length](../../epc_nd_ingest/reader.py#L49) counts UTF-16 units, and the width check uses it. The 100-unit boundary builds; 101 units fail even when the Python character count is 100. |
| The notebook could falsely reject a faithfully stored MAX value | [Step 4](../../loader/make_notebook.py#L370) uses the same units for bounded limits and the longest value sent. Its comparison with `DATALENGTH / 2` now compares like units. The delivered notebook matches the generator. |
| Build observations needed to use the same unit | [checks._sql_length](../../epc_nd_ingest/checks.py#L26) measures UTF-16 units for maximum lengths and the 4,000-unit threshold. The tests compare its results and the reader's helper with Python's UTF-16 encoding, including supplementary characters, combining marks and NULL. The report and decision log state the unit. |

Validation performed during this follow-up:

- `python -B -m pytest -q`: **103 passed in 26.02 seconds**.
- Reran [the response probe](../../docs/reviews/2026-11-14-nondomestic-implementation-review-response-probe.py): **all assertions passed**. It exercises accepted and rejected bounded values, a 4,452-unit MAX value, the accepted 8,000-unit limit, rejection at 8,001 units, and the generated notebook's own helper.
- Regenerated the notebook in a temporary directory: all cell sources and cell types match the delivered notebook.
- Recomputed the delivered CSV and Parquet SHA256 values: both match the updated manifest. The decision-log hash also matches. The manifest's row digest remains `176041734596302563122`, and it reports no supplementary characters in the real release.
- Inspected the expanded SQL Server probe code and records: the bulk-import fixture checks exact bounded lengths and trailing surrogate bytes; the notebook fixture checks 512 cells and rejects a 33-unit value before insertion into `nvarchar(32)`. The records report five bulk-load checks passing and all 13 notebook scenarios passing.

The container probes were reviewed, not rerun in this follow-up. Windows `CODEPAGE = '65001'` and the HIC production connection remain outside this validation, as the probe records state.

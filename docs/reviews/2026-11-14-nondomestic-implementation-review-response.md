# Response to the implementation review of 14 November 2026

Review: `2026-11-14-nondomestic-implementation-review.md`. Its one finding holds. I reran the
reviewer's reproducer before changing anything and got its two discrepancies. The fix was then
probed without SQL Server (`2026-11-14-nondomestic-implementation-review-response-probe.py`, with
its `.out` beside it) and with SQL Server, by both container probes.

| # | Finding | Holds | Change |
| --- | --- | --- | --- |
| 1 | Text capacity and read-back lengths were measured in Python characters, while SQL Server counts an `nvarchar` in UTF-16 code units | yes. 99 letters and U+1F3E2 in `ADDRESS1` passed all 44 checks of a synthetic build and need 101 units in `nvarchar(100)`. The notebook recorded 4,451 for a value SQL Server stores as 4,452 units | Every length is now in UTF-16 code units: the characters, plus one for each character outside the Basic Multilingual Plane. The build's width check uses `reader.sql_length`. The build report's longest value per column and its count of cells over 4,000 use the same unit, and a new count reports cells with such a character. The notebook's step 4 uses its own copy of the helper for the limit of a bounded column and for the longest value it compares with `DATALENGTH / 2`. The decision `width-is-accepted-length`, the data dictionary, the provenance pages, the README and the plan state the unit. |

## What the fix was run against

- **The build, on synthetic input.** 98 letters and one supplementary character (100 units) build.
  99 and one (101 units, 100 characters) stop at `extract.text_within_width`. In the `max` column
  4,450 letters and one are recorded as 4,452, 7,998 and one (8,000 units) build, 7,999 and one
  stop.
- **The notebook's helper, taken from the generated notebook.** It returns the UTF-16 count for
  six values, among them the two of the review.
- **SQL Server through `BULK INSERT`.** `loader/sqlserver_probe.sh` now imports a 16-row fixture
  with the generated script. Row 15 fills `nvarchar(100)` and `nvarchar(32)` to the last unit
  with a supplementary character at the end. Row 16 ends a value over 4,000 units in the `max`
  column with one. The five checks pass, the stored lengths are 100, 32 and 4,452 units, and the
  last four bytes of each cell are the surrogate pair.
- **SQL Server through pyodbc.** `loader/notebook_probe.sh` runs the notebook on the same fixture:
  13 of 13 scenarios, 512 cells read back equal, the same lengths and bytes. Step 4's comparison
  of the longest value sent with the longest stored passes at 7,999. Scenario 09b now sends 31
  letters and one supplementary character to `nvarchar(32)`: 32 characters, 33 units, refused
  before any insert.
- **The real release.** It holds no supplementary character, as the review found. The build
  report now says so. The CSV hash and the digest are unchanged, so the earlier probe results
  stand for it.

## Found while fixing

- My first fixture row for the 32-unit column held 31 units, not 32. The probe's own comparison
  caught it.
- The notebook harness read four bytes back with `RIGHT`, which returns text for a binary value.
  It now uses `SUBSTRING`, and so does the SQL Server probe.

## What the added tests do not cover

- A value whose last UTF-16 unit would be half of a surrogate pair cannot be built from valid
  UTF-8, so no test sends one.
- Characters that render as one glyph from several code points, such as an accent written as a
  combining mark, are counted per code unit, which is what SQL Server does. One such value is in
  the helper's test. No fixture loads one.
- The fixture was imported from a UTF-16 file, the Linux route. A supplementary character through
  the Windows route with `CODEPAGE = '65001'` is not exercised. The digest check after a load is
  what would show it.
- Staging holds a bounded column as `varchar(8000)` in UTF-8. A column of the widest bounded
  bucket below the staged-as-max limit, 512 units, takes at most 2,048 bytes there, so it fits.
  No test fills such a column with four-byte characters.

My finding from this review is closed. Nothing else in the review was open.

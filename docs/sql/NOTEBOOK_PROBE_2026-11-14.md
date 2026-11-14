# Probe of the upload notebook through pyodbc, 14 November 2026

`sh loader/notebook_probe.sh` runs the notebook's own cells in a Jupyter kernel, from a client
container (Python 3.12, pyodbc 5.1.0, pandas 2.2.3, ODBC Driver 18 for SQL Server) against a
throwaway SQL Server 2022 container (16.0.4305.5), as a login that has only `CREATE TABLE` and
rights on the `dbo` schema. The fixture is 16 rows built by the real pipeline. The script
exited 0 with 13 of 13 scenarios as expected.

## The fixture

The seven default rows of the tests, which carry a tab in an address and around a postcode, the
replacement character, an empty UPRN, an empty RRN, `Data removed` in both rating pairs,
`Carbon Neu`, `-0`, a negative rating and a 4,451-character cell that ends with a space. Seven
more rows add non-ASCII text (Gaelic accents, a no-break space, curly quotes, the euro sign, a
superscript two), every wide column one short of its width with a 7,999-character cell, decimals
at the edge of decimal(19,4), a twelve-digit UPRN and a building assessed twice. Two rows, added
after the implementation review, hold characters that take two UTF-16 code units: one fills
`nvarchar(100)` and `nvarchar(32)` to the last unit, the other ends a 4,452-unit value in the
`nvarchar(max)` column.

## Scenarios

| Scenario | Expected | Result |
| --- | --- | --- |
| 01 The notebook as it is | every step passes | as expected |
| 02 The same folder again | every step passes | as expected |
| 03 One byte changed in the CSV | stops at step 2, table untouched | as expected |
| 04 A loaded value changed | step 5 fails on the digest | as expected |
| 05 A NULL `rrn` made the empty string | step 5 fails on the digest | as expected |
| 06 A trailing space removed | step 5 fails on the digest | as expected |
| 06b A tab replaced by a space | step 5 fails on the digest | as expected |
| 06c The last character of the 7,999-character cell changed | step 5 fails on the digest | as expected |
| 07 All restored | step 5 passes, table as before | as expected |
| 08 A batch the server rejects | stops at step 4 with the server's conversion error, the earlier chunk stays | as expected |
| 09 A decimal not in 4-decimal form | stops at step 4 before any insert | as expected |
| 09b A text of 32 characters and 33 UTF-16 code units for `nvarchar(32)` | stops at step 4 before any insert, the column named | as expected |
| 10 The notebook again after the failures | every step passes | as expected |

After scenarios 01, 02 and 10 every cell of 32 columns of the 16 rows (512 cells) is read back
through pyodbc and compared with the CSV text. All are equal. The three long cells are stored
with 4,451, 7,999 and 4,452 UTF-16 code units. The two bounded cells that a supplementary
character fills are stored with 100 and 32 units and end with its surrogate pair.

## What the probe found

- **The `nvarchar(max)` column binds with size 0.** Step 4 calls `setinputsizes` with
  `(SQL_WVARCHAR, 0, 0)` for that column and the declared width for the others, with
  `fast_executemany` on. The 4,451 and 7,999-character values arrive whole, and so does the
  4,452-unit value that ends with a supplementary character. The pyodbc
  documentation does not describe this binding (its wiki pages on the cursor, on binding
  parameters and on features beyond the DB API were read on 14 November 2026), so the notebook
  does not rely on it: step 4 reads the longest stored value back and stops unless it is as long
  as the longest value sent.
- **A defect, fixed.** The first run stopped at step 4: the check that every decimal has four
  decimals refused the empty cells of `potential_energy_performance_rating_num`, which are its
  NULLs. uprn-epc has no nullable decimal, so its notebook never met the case. The check now
  allows an empty cell in a nullable decimal column and still refuses one in a required column.
- **Lengths were counted in characters, fixed.** The implementation review found that step 4
  counted characters where SQL Server counts UTF-16 code units, so its read-back would have
  stopped a faithful load of a value with a supplementary character. Step 4 now counts as SQL
  Server does, and this run includes such values.
- **Two scenarios passed for the wrong reason in that first run**, because the defect stopped
  step 4 before their own fault was reached. Scenarios 08 and 09 now name the error they expect.

## The real table

The real notebook was also run once, every cell, against the same server on the full build:
95,719 rows loaded in 8 seconds, the three indexes built, the five checks of step 5 passed with
digest total `176041734596302563122`, and the longest stored value was 4,451 characters. The
server and the client were containers on one machine.

## What this probe does not cover

- Windows authentication, and a server reached over a network.
- A pyodbc or driver version other than the two above. The read-back in step 4 is what would
  show a version that binds the `max` column differently.
- A run interrupted in the middle of step 4, other than by a rejected batch.

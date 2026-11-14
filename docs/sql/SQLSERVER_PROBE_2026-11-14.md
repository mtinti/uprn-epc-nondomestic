# SQL Server probe of the import and check scripts, 14 November 2026

`sh loader/sqlserver_probe.sh` against a throwaway SQL Server 2022 container (16.0.4305.5,
Developer Edition, Linux on amd64), on the build of release 2026Q3: 95,719 rows by 57 columns, CSV
SHA256 `d43cd944e613c67e6d6f4ab2c5bc7fa6cf2eecea76ab7c4bffbb5c5d6d7ce686`, digest total
`176041734596302563122`. The script exited 0.

## What the container run differs in

SQL Server on Linux does not accept `CODEPAGE = '65001'`. The probe converts the CSV to UTF-16LE
with a byte order mark and imports it as `widechar`. Everything else is the generated
`import_csv.sql` as it is. The Windows load uses the script unchanged, and that route is not
exercised here.

## Results

| Step | Result |
| --- | --- |
| Import through `BULK INSERT` and the staging table | 5 seconds |
| `check_loaded_digest.sql`: structure, key, framing characters, row count, digest | 5 of 5 pass, 1 second |
| SQL Server's rendering of 65 chosen cells against the CSV text | equal |
| 23 counts of empty against NULL and of the awkward cells against the manifest | equal |
| The digest after each of four changes to one cell | fails, the other four checks pass |
| The five checks after the cell is restored | pass |
| A 16-row fixture with supplementary characters, imported with the same script | 5 of 5 pass, lengths and bytes as expected |
| The columns the three join queries return, in order | 22, 17 and 25, as the contract lists them |
| The dated join on seven cohort rows | each returned once with its status and age |
| The postcode join | see below |
| A NULL and a repeated cohort key | each stops the query |

The 65 cells are 13 columns of five rows: the first two, one with an empty UPRN and an empty RRN,
one with `Data removed`, and one with a negative rating and the band `Carbon Neu`. They cover a
bigint, a date, a timestamp, a bit, an integer, a decimal(19,4) and a NULL decimal.

## The cells this extract is awkward for

Each count is taken in SQL Server and compared with the build's own count in the manifest.
Characters are tested under a binary collation and by code point, and lengths with `DATALENGTH`,
because `=` and `LEN` ignore a trailing space.

| What | SQL Server |
| --- | ---: |
| Empty `ADDRESS2` cells that are empty strings, not NULL | 31,443 |
| Published cells that are NULL (four columns tested) | 0 |
| `uprn_osg` NULL, and `OSG_REFERENCE_NUMBER` empty | 33,906 and 33,906 |
| `rrn` NULL, and `REPORT_REFERENCE_NUMBER` empty | 126 and 126 |
| `potential_energy_performance_rating_num` NULL, and `Data removed` in its text | 1,712 and 1,712 |
| `Data removed` in `ASSET_RATING` | 12,484 |
| `Carbon Neu`, ten characters long | 188 |
| `-0` in `NEW_BUILD_ENERGY_PERFORMANCE_RATING` | 25 |
| Cells with a tab: `ADDRESS1`, `ADDRESS2`, `POST_TOWN`, `POSTCODE` | 208, 217, 92, 5 |
| `pc_norm` with a tab or a space | 0 |
| `ADDRESS1` cells with the replacement character U+FFFD | 1 |
| `IMPROVEMENT_RECOMMENDATIONS` cells that end with a space | 93,392 |
| `POSTCODE` cells that end with a space | 12 |
| `IMPROVEMENT_RECOMMENDATIONS` cells over 4,000 characters | 3 |
| The longest `IMPROVEMENT_RECOMMENDATIONS` cell, in characters | 4,451 |

So a tab, a trailing space, the replacement character and a cell longer than 4,000 characters
all arrive unchanged through `BULK INSERT` from a `widechar` file.

## The digest sees a changed cell

One cell is changed, the check script is run and must fail on the digest alone, and the cell is
put back from a saved copy.

| Change | Check script |
| --- | --- |
| The last character of the 4,451-character cell replaced | digest fails, four other checks pass |
| A trailing space removed from a recommendations cell | digest fails, four other checks pass |
| A tab replaced by a space in `ADDRESS2` | digest fails, four other checks pass |
| An empty `ADDRESS2` made a single space | digest fails, four other checks pass |
| All four restored | five checks pass |

## Characters that take two UTF-16 code units

The release holds no character outside the Basic Multilingual Plane, so the real table cannot
show what `BULK INSERT` does with one. The probe therefore imports the notebook probe's fixture
with the same generated script, under the name `epc_nd_fixture`, and runs the check script on it.
Lengths are `DATALENGTH / 2`, and the last four bytes of each cell must be the surrogate pair of
U+1F3E2 (`3C D8 E2 DF`).

| Cell | Expected | SQL Server |
| --- | --- | --- |
| `ADDRESS1`, `nvarchar(100)`: 98 letters and one such character | 100 units, ends with the pair | as expected |
| `PROPERTY_TYPE_SHORT`, `nvarchar(32)`: 30 letters and one | 32 units, ends with the pair | as expected |
| `IMPROVEMENT_RECOMMENDATIONS`, `nvarchar(max)`: 4,450 characters and one | 4,452 units, ends with the pair | as expected |
| `IMPROVEMENT_RECOMMENDATIONS`: the 7,999-character cell | 7,999 units | as expected |
| The five checks of the check script, digest included | pass | pass |

Added after the implementation review of 14 November 2026
(`docs/reviews/2026-11-14-nondomestic-implementation-review-response.md`).

## The joins on SQL Server

- Each query returns exactly the columns `tests/test_joins.py` lists for it, in order.
- `join_by_uprn.sql` on seven cohort rows: `matched` for a UPRN on its inspection date (age 0)
  and for the same UPRN padded to twelve digits, `no_certificate_by_date`, `uprn_not_in_epc`, and
  `no_uprn` for an empty, a NULL and a non-integer UPRN.
- `join_by_postcode.sql`: a postcode the release holds with a tab returns the same buildings
  when the cohort gives it with the tab, with a space in its place, and with neither. A cohort
  postcode of a tab and a space is `no_postcode`. A building with two certificates at two
  postcodes is returned at the later postcode and not at the earlier one.

SQL Server prints "Warning: Null value is eliminated by an aggregate" for the postcode query.
It is a message, not an error: `MAX(uprn_osg)` skips the certificates without a UPRN.

## What this probe does not cover

- A supplementary character, or any other cell, through the Windows route.
- The Windows route with `CODEPAGE = '65001'`. The first load at HIC is its test, and the digest
  check after it is what would show a cell read in the wrong code page.
- The undated and postcode joins are checked for their columns and for the cases above, not for
  every status. `tests/test_joins.py` covers the statuses in DuckDB.
- A database with a case-sensitive or a non-default collation.

# Plan: ingest the Scottish non-domestic EPC register extract

Status: implemented on 14 November 2026, except the load at HIC and the view over both registers
(order of work, below). Proposed and revised the same day after two reviews
in `docs/reviews/`:
`2026-11-14-nondomestic-ingestion-plan-review.md` and
`2026-11-14-nondomestic-ingestion-plan-follow-up-review.md`. Each has a response beside it, named
after it with `-response`.

## Aim

Bring the Scottish Government's extract of non-domestic Energy Performance Certificates (EPC) into
the safe haven as a pinned, checked table, `epc_nondomestic`, one row per certificate, joinable to a
cohort by UPRN and date. It answers for the buildings the domestic table cannot see: care homes,
hospitals, residential schools, student halls, and every shop, office and school.

The build is a copy of [uprn-epc](https://github.com/mtinti/uprn-epc), which
followed [postcode-simd](https://github.com/mtinti/postcode-simd) and
[datazone-ahah](https://github.com/mtinti/datazone-ahah): pinned sources, blocking checks, values as
published with typed copies beside them, a CSV with a row digest, generated import and check
scripts, a loader, a notebook, a column provenance site. This plan does not repeat that design. It
says what is the same, what the file forces to change, and what is new. Read it beside
`EPC/docs/EPC_Plan.md` and `EPC/docs/EPC_SQL_Plan.md`. The design is the same. The code is a port,
not a copy: most modules name the annual files or the domestic columns.

## Words

- **Non-domestic certificate.** The publisher's term, used everywhere here. "Commercial" is
  avoided, because the register also holds schools, health buildings, courts and care homes.
- **Building.** What one certificate assesses. The note says it is a building or a building unit,
  so a shop in a parade is a building in this sense.
- **Register number.** `BUILDING_REFERENCE_NUMBER`, the register's own 10-digit number. Not a UPRN.
- **UPRN.** `OSG_REFERENCE_NUMBER`, the One Scotland Gazetteer number, the one a cohort links on.
- **Current, superseded.** `HISTORIC` is `False` for the latest certificate of a building and
  `True` for one that a later certificate replaced. It says nothing about expiry.

## What the extract is

| | |
| --- | --- |
| Publisher | Scottish Government, EPCenquiries@gov.scot |
| Title | Non-domestic Energy Performance Certificates, extended historic dataset, January 2013 to Q3 2026 |
| Catalogue page | https://data.gov.scot/dataset/non_domestic_energy_performance_certificates___extended_historic_dataset_to_q1_2026 (the slug says Q1; the file is the Q3 2026 release) |
| Download | one 7z archive, 9,301,781 bytes, SHA256 `388d7d40438971c051515676827840df4f461fcc73b8fabe0d033b07cbc39c06`, downloaded 11 November 2026 |
| Contents | one CSV, `AltHistoricExtract2013to2026ND.csv`, 141 MB, and the publication note (PDF, 12 pages, with the data dictionary) |
| Rows | 95,719 certificates, lodged from 29 January 2013 to 30 September 2026 |
| Columns | 38. The note says 36 and its dictionary lists 38 |
| Licence | Open Government Licence v3.0 for every field except `ADDRESS1`, `ADDRESS2`, `POST_TOWN` and `POSTCODE`, which carry Royal Mail's notice (note, pages 2 to 4). The same split as the domestic extract |
| Updates | quarterly, at the same URL, which is overwritten |

The domestic table in the safe haven is release 2026Q2 (register extract of 1 September 2026). This
file is 2026Q3 (extract of 21 October 2026). The two tables will describe the register at two
different days until the domestic one is rebuilt (open question 2).

### Facts found in the file that the plan must handle

Every number is from `tools/profile_nondomestic.py`, run on 14 November 2026. Its output is
`docs/profile_2026-11-14.txt`.

Same as the domestic extract:

- **Two header rows**, machine names then the publisher's labels. UTF-8 with a byte order mark,
  CRLF line endings. One label holds U+FFFD where the publisher lost a superscript 2.
- **Same shapes for the join columns.** `INSPECTION_DATE` and `LODGEMENT_DATE` are `yyyy-mm-dd` in
  every row. `CREATED_AT` is `dd/mm/yyyy hh:mm:ss` in every row. `HISTORIC` is `True` or `False`
  in every row (79,874 current, 15,845 superseded).
- **Two property numbers, one to one where both exist.** 51,879 distinct UPRNs, each with one
  register number and the reverse. A register number never has a UPRN in one row and none in
  another. UPRNs have 8 to 12 digits and no leading zero. The 522 8-digit values start 350 or 352,
  the range the domestic check placed in Clackmannanshire.
- **`REPORT_REFERENCE_NUMBER` (RRN) is unique where present.** It is empty in 126 rows.
- **Data zones carry the name.** `DATA_ZONE` is the 2001 zone and `DATA_ZONE_2011` the 2011 zone.
  Every well formed code is in the list uprn-epc already pins for its vintage (92,872 and 93,747
  rows). `DATA_ZONE` holds 294 values such as `00QQMB ()`, and `DATA_ZONE_2011` holds `NA (NA)` in
  40 rows.

Different from the domestic extract:

- **One file, not one per year, and in no order.** The note says rows from 2014 are in lodgement
  order. They are not: the first three rows were lodged in 2014, 2016 and 2026. The row number
  identifies a row in this pinned file and nothing else.
- **The third address line is `POST_TOWN`**, not `ADDRESS3`.
- **A third of the certificates have no UPRN.** `OSG_REFERENCE_NUMBER` is empty in 33,906 rows
  (35.4%), between 27% and 41% in every year, with no improvement over time. The domestic figure
  is 4.7%.
- **One column is longer than SQL Server's bounded text type allows.**
  `IMPROVEMENT_RECOMMENDATIONS` reaches 4,451 characters, and 3 cells pass 4,000. The domestic
  table's rule, no `nvarchar(max)`, cannot hold here. 93,392 of its cells end with a space.
- **Tab characters inside cells.** 517 address cells and 5 postcodes contain a tab. No cell
  contains a newline or a double quote. uprn-epc's `pc_norm` rule removes spaces only, so it would
  leave the tab in.
- **One data cell holds U+FFFD**, in `ADDRESS1`. The domestic extract has none in its data rows.
- **The text `Data removed` stands in number and band columns.** 1,712 rows in
  `POTENTIAL_ENERGY_PERFORMANCE_RATING` and its band, 12,484 rows in `ASSET_RATING` and its band.
  The pairs always agree. The note ties this to lodgements before 20 March 2016, but `ASSET_RATING`
  carries it in every year to 2026.
- **The band text is cut at ten characters.** Carbon neutral is published as `Carbon Neu`.
- **Numbers have no published range.** `FLOOR_AREA` runs from 4 to 138,037 m².
  `CURRENT_ENERGY_PERFORMANCE_RATING` runs from -9,098 to 42,155, and 28% of rows are band G.
  `NEW_BUILD_ENERGY_PERFORMANCE_RATING` is `-0` in 25 rows. The current rating is
  `BUILDING_EMISSIONS` rounded, except in 473 rows where it differs by one.
  `POTENTIAL_ENERGY_PERFORMANCE_RATING` is published with two decimals, always `.00`.
- **Inspection and lodgement are further apart.** The median gap is 8 days, against 1 for
  dwellings. 18% of certificates were lodged 31 to 365 days after the inspection and 1,411 over a
  year after. 195 were lodged before the inspection. `INSPECTION_DATE` runs from 2002 to 2108.
- **`CREATED_AT` and `LODGEMENT_DATE` disagree on the day in 9,897 rows**, by up to 1,531 days.
- **Same-day pairs barely exist.** 11 register numbers have two certificates inspected on one day,
  and one of the 11 has a UPRN. The domestic extract has 103,862 such pairs by UPRN.
- **Every building has at most one current certificate.** 1,428 register numbers have none, 1,243
  of them with a UPRN. For 264 more UPRNs the current certificate is not the one inspected last.
- **Most UPRNs without a current non-domestic certificate are also in the domestic table.** Of
  the 1,243, 1,162 occur in the domestic table. 1,154 have a domestic certificate lodged after
  their last non-domestic one, and 1,156 have a current domestic certificate. This suggests a move
  from one register to the other. The extracts do not say why it happened, or which certificate
  replaced which, and the two tables are extracts of different days.
- **A building's postcode and type change between certificates.** 258 register numbers carry two
  or more postcodes over their certificates. 2,266 UPRNs carry two or more `PROPERTY_TYPE_SHORT`.
- **`PROPERTY_TYPE` mixes two vocabularies** (43 values, with and without a use-class prefix).
  `PROPERTY_TYPE_SHORT` folds them into 23. Neither column separates a hospital from a care home.
- **The geography columns are empty together.** `LOCAL_AUTHORITY`, `DATA_ZONE` and `CONSTITUENCY`
  are all empty in the same 2,553 rows. Ten rows carry an English local authority code. 18
  postcodes are outside the Scottish postcode areas, and 3 are not full postcodes.

## What is ported from uprn-epc and what changes

The starting point is uprn-epc commit `04bbbda`, in its own repository, `uprn-epc-nondomestic`,
package `epc_nd_ingest`. The reviews cite that commit as `d3d1ea4`, its hash before uprn-epc's
history was rewritten on 14 November 2026 (uprn-epc, `docs/HISTORY_REWRITE_2026-11-14.md`).

| Part | uprn-epc | Here |
| --- | --- | --- |
| Registry `sources.yaml` | archive, note, 19 members, each with a `year` | archive, note, one member with a `file` and no year. The two data zone lists are the same files and hashes |
| `published_columns.yaml` | 107 columns | 38 columns, from the profile |
| Key | `epc_release`, `source_year`, `source_row` | `epc_release`, `source_row` |
| Text widths | an integer `width`, declared `nvarchar(width)`, no `max` | an integer `width` still, declared `nvarchar(max)` when it is over 4,000 |
| `pc_norm` | upper case, spaces removed, in the build and in the query | upper case, spaces and tabs removed, the same in both |
| Missing-value text | none | `Data removed`, in four named columns |
| Digest definition, CSV dialect | | unchanged |
| Join rules and statuses | | unchanged for the UPRN routes. The postcode route chooses differently (section 7) |
| Join output | domestic measurement columns | its own measurement columns (section 7) |

Modules that change, and why. Each was checked in the code, and three were run
(`docs/reviews/2026-11-14-nondomestic-ingestion-plan-review-response-probe.py`):

- `core/sources.py` requires a `year` on every member and sorts by it. A member without one raises
  `KeyError`. It must identify a member by its file.
- `core/output.py` writes the members' years into the Parquet metadata and describes 107 columns.
- `columns.py` holds the key, the width buckets and the lists of typed columns.
- `reader.py` reads "a year" and checks the `CREATED_AT` year against it. It also holds `pc_norm`.
- `checks.py` and `pipeline.py` count and report per `source_year`. The manifest key
  `digest_per_year` becomes `digest_per_member`. Counts per year in the build report use the year
  of `created_at_parsed`.
- `sql_check.py` declares `nvarchar(width)` and compares the declared length in the structure check.
- `lineage.py`, `provenance_site.py` and `dictionary.py` name `source_year` and the annual files.
- `loader/make_notebook.py` parses the table definition with a pattern that knows `nvarchar(n)`
  only, so it drops an `nvarchar(max)` column. It also shows rows per `source_year` and joins back
  through it.
- `loader/sqlserver_probe.sh`, `loader/notebook_probe/` and `tests/synthetic.py` build and address
  rows by year.

`core/checks.py`, `core/text_output.py` and `core/dbf.py` are copied unchanged.

## The design, step by step

Each step names only what differs from the same step of `EPC_Plan.md`.

### 1. Pin the source

The registry pins the archive, the note and the one CSV member, with the row count. A member is
identified by its file. The release is `epc_release: 2026Q3`, with the extraction date from the
note. `SOURCES.md` records that the archive dates the CSV 8 October 2026, before the note's
21 October.

The two data zone lists are pinned as in uprn-epc, same URL and hash, so the four projects agree on
what a valid zone is.

### 2. Archive the source

As for the domestic extract: a restricted Zenodo draft, unpublished, holding the archive, the note
and the checksums, and a copy on the HIC OneDrive under `onedrive:dataset_healscot/EPC_nondomestic/`.
The reason is the same. The URL is overwritten every quarter and the address fields are not under
the Open Government Licence. Done on 14 November 2026 (order of work, step 4).

### 3. Read and check

Every published column is kept as text exactly as published, under its published name, in
published order. Typed copies are added only where a join, a check or the shared measures need one.

| Derived column | From | Rule |
| --- | --- | --- |
| `epc_release`, `source_row` | the pinned file | key. `source_row` is 1 for the first data row (file row 3) |
| `rrn` | `REPORT_REFERENCE_NUMBER` | as published. NULL where empty. Unique where not NULL |
| `uprn_sepcr` | `BUILDING_REFERENCE_NUMBER` | bigint, never NULL |
| `uprn_osg` | `OSG_REFERENCE_NUMBER` | bigint. NULL where empty. The only column a UPRN join compares |
| `pc_norm` | `POSTCODE` | upper case, then every space (U+0020) and tab (U+0009) removed. NULL where nothing is left. Nothing repaired |
| `datazone_2001`, `datazone_2011` and their `_status` | `DATA_ZONE`, `DATA_ZONE_2011` | uprn-epc's rule and statuses, unchanged |
| `inspection_date_parsed`, `lodgement_date_parsed`, `created_at_parsed` | the three date columns | uprn-epc's rule, unchanged |
| `historic_flag` | `HISTORIC` | bit. Any value other than `True` or `False` stops the build |
| `floor_area_int` | `FLOOR_AREA` | int, never NULL |
| `current_energy_performance_rating_int` | `CURRENT_ENERGY_PERFORMANCE_RATING` | int, never NULL, negative allowed |
| `potential_energy_performance_rating_num` | `POTENTIAL_ENERGY_PERFORMANCE_RATING` | decimal(19,4). NULL exactly where the text is `Data removed` |
| `building_emissions_num` | `BUILDING_EMISSIONS` | decimal(19,4), never NULL. kg CO2 per m² per year |
| `primary_energy_value_int` | `PRIMARY_ENERGY_VALUE` | int, never NULL. kWh per m² per year |

`floor_area_int`, `building_emissions_num` and `primary_energy_value_int` are the three quantities
that also exist for dwellings, in the same unit. Every other number stays text until a project asks
for it.

`Data removed` is the publisher's missing value in four columns and only there:
`POTENTIAL_ENERGY_PERFORMANCE_RATING` and its band, `ASSET_RATING` and its band. The potential
rating gets the one nullable typed copy, so the rule has a column to act on. `ASSET_RATING` stays
text. Two blocking checks cover all four columns, typed or not:

- every cell of the two rating columns is a number or exactly `Data removed`;
- a rating is `Data removed` exactly when its band is.

In any other typed column `Data removed` is a number that does not parse, and stops the build.

The build also fails when:

- the member's hash, its two header rows or its row count differ from the pin, a row has other
  than 38 fields, or a byte is not UTF-8;
- a date does not parse, `HISTORIC` is not `True` or `False`, or a typed number does not parse;
- a text value is longer than its `width`;
- the key repeats, or a non-empty RRN repeats;
- a UPRN maps to more than one register number, or the reverse;
- a data zone code is well formed but not in the pinned list of its vintage;
- a `CREATED_AT` is later than the last day of the release quarter. This replaces the domestic
  check that a row's `CREATED_AT` year is its file's year.

The build counts and reports, without failing: empty UPRN, register numbers with no current
certificate, register numbers with two, register numbers with two or more postcodes, empty RRN,
the zone statuses, rows with the geography columns empty, local authority codes outside Scotland,
postcodes that are not full or not Scottish, `pc_norm` values with a character other than a
letter or a digit (none today), cells with a tab, cells with U+FFFD, `Data removed` per column,
floor areas under 15 and over 1,500 m², ratings that differ from the rounded emissions, bands that
differ from the cut of the rating, `MEETS_2002_STANDARD` empty, lodgement before inspection,
inspection after the extraction date, inspection more than a year before lodgement, `CREATED_AT`
and `LODGEMENT_DATE` on different days, and same-day pairs by register number and by UPRN. Each
count goes in the build report and in the decision log as this release's evidence.

### 4. One table, keyed by certificate

`epc_nondomestic`, keyed by `(epc_release, source_row)`: the key, the 38 published columns as text,
then the derived columns. The naming rule, the empty-against-NULL rule and the type rules are
uprn-epc's, with one change.

`IMPROVEMENT_RECOMMENDATIONS` has 3 cells longer than the 4,000 characters a bounded `nvarchar`
holds, and the value must stay as published. The schema keeps the two things apart:

- **`width` is the longest value the build accepts**, an integer for every text column, from the
  measured longest value and the next bucket. It is counted in UTF-16 code units, as SQL Server
  counts an `nvarchar`: a character outside the Basic Multilingual Plane, such as an emoji,
  counts as two. The buckets gain 8,000. So
  `IMPROVEMENT_RECOMMENDATIONS` has width 8,000, and a longer value in a later release still stops
  the build at the schema check, as for every other column.
- **The SQL type follows from the width.** Up to 4,000 it is `nvarchar(width)`. Above it is
  `nvarchar(max)`.

Because `width` stays an integer, the schema loader, the reader's width check and the staging
rule work as they are. What changes is the declared type and the structure check in
`sql_check.py`, and in `make_notebook.py` the pattern that parses the table definition, the width
table built from it, and the input size bound for the `max` column. This replaces uprn-epc's
decision `bounded-widths-max-in-digest` for this table.

### 5. What leaves the build

Unchanged: the recipe is public, the built table is private, and every column goes into the CSV,
the address lines included, because the CSV travels only to the HIC OneDrive and the HIC SQL
Server. The address lines matter more here than for dwellings. They are the only key for the 35%
of certificates without a UPRN, and they carry the name of the building.

The information governance question in `EPC_Plan.md` (order of work, step 8) is still open and
covers this table too.

### 6. Load into SQL Server and check the load

Same two routes, `BULK INSERT` through the loader and pyodbc through the notebook, and the same
digest check. The table is 95,719 rows, so time is not a concern. Four things are new and each is
probed before the real load, because none occurs in the domestic table:

- the generated definition is parsed back by the notebook with every column present, the `max`
  column included;
- a 4,451-character cell arrives whole by both routes, and changing its last character changes the
  loaded digest;
- a cell with a tab, and a cell that ends with a space, arrive unchanged by both routes;
- the notebook binds the `max` column without truncating it.

How SQL Server and pyodbc treat each of these is checked in the container probes and against the
documentation, not assumed.

### 7. Example joins

Three queries, as in uprn-epc. Every one joins back to the table by `(epc_release, source_row)`.

**Output columns.** The queries do not return the domestic columns, and no non-domestic value is
given a domestic name. The domestic rating scores energy cost and the non-domestic rating is an
emissions rate, so the two must not share a column.

Each query has its own output. A column that does not apply to a query is not returned by it.

| Columns | Dated UPRN | Undated UPRN | Postcode |
| --- | --- | --- | --- |
| `cohort_row_id`, `pseudo_id`, `epc_status` | yes | yes | yes |
| `cohort_date` | yes | no | yes |
| `building` (the register number), `building_status`, `uprn_osg` | no | no | yes |
| `epc_inspection_date`, `epc_lodgement_date`, `epc_lodged_before_inspection` | yes | yes | yes |
| `epc_age_days` | yes | no | yes |
| Measurements, under their own names: `CURRENT_ENERGY_PERFORMANCE_BAND`, `current_energy_performance_rating_int`, `POTENTIAL_ENERGY_PERFORMANCE_BAND`, `potential_energy_performance_rating_num`, `PROPERTY_TYPE_SHORT`, `PROPERTY_TYPE`, `MAIN_HEATING_FUEL` | yes | yes | yes |
| The three quantities shared with dwellings: `floor_area_int`, `building_emissions_num`, `primary_energy_value_int` | yes | yes | yes |
| `historic_flag` | yes | no | yes |
| `rrn` | yes | yes | yes |
| `epc_tie_candidates`, `epc_tie_rule` | yes | no | yes |

The columns come in the order of the table, 22 for the dated query, 17 for the undated and 25 for
the postcode query. The names shared with uprn-epc keep its meaning.

Why the undated query returns fewer:

- It takes no date, so it has no `cohort_date` and no `epc_age_days`. No query reads the clock. An
  age counted from the day the query runs would change with every run.
- It returns the current certificate, so `historic_flag` would be 0 in every matched row.
- It has no tie rule. It counts the current certificates of the UPRN. Two or more give
  `ambiguous_latest` and no values, so there are no tie columns.

Which rows carry values:

- Every column from `epc_inspection_date` to `rrn` is NULL unless the row is `matched`. In the
  postcode query that means `building_status` is `matched`.
- `uprn_osg` in the postcode query is filled for every building listed, matched or not. The
  build stops unless a register number has one UPRN, so it belongs to the building, not to the
  chosen certificate. It is NULL for a building without a UPRN.
- `epc_age_days` is the days from the inspection date to `cohort_date`.
- `epc_tie_candidates` is the number of certificates inspected on the latest eligible day. It is
  filled whenever one is eligible, `ambiguous_as_of` included, and NULL otherwise. `epc_tie_rule`
  is NULL for one candidate, else `current`, `latest_lodged` or `unresolved`.

A test runs each query against a table created from the generated schema and checks the column
names, their order and these value rules. The container probe does the same on SQL Server. How
these columns map onto the domestic ones belongs to the plan for the view over both registers.

**By UPRN, dated.** The certificate with the latest inspection on or before the cohort date. The
tie rule stays, current first and then the latest `created_at_parsed`, although one UPRN has a
same-day pair in this release. The comments say that the gap from inspection to lodgement is
longer here, and both dates are returned.

**By UPRN, undated.** The current certificate. `no_current_certificate` applies to 1,243 UPRNs.
The status reports what the file holds. It does not say why the UPRN has no current certificate.

**By postcode, the fallback.** It answers "which buildings were at this postcode as of the cohort
date". uprn-epc's query filters certificates to the cohort postcode first and ranks after. A
building whose later certificate carries another postcode is then still returned at the old
postcode, with the older assessment. In this release, as of 30 September 2026, that returns 262
building and postcode pairs that the building's latest certificate contradicts. The query here
ranks first and compares after:

1. Candidate buildings are the register numbers with any certificate at the cohort's `pc_norm`.
2. For each, the latest eligible certificate is chosen over all its certificates, whatever their
   postcode, with the tie rule of the UPRN route.
3. The building is returned only if the chosen certificate carries the cohort's `pc_norm`. Where
   the tie rule leaves two or more, the building is returned as `ambiguous_as_of`, without
   values, if any of them carries it.

One status is added for the cohort row: `no_building_at_postcode_by_date`, when certificates at
the postcode exist on or before the date and every such building's latest certificate carries
another postcode. The other statuses are uprn-epc's.

The cohort postcode is normalised by the same rule as `pc_norm`, spaces and tabs removed, and an
empty result is `no_postcode`. With spaces only, a cohort value holding a tab would never match.

The fallback matters more here, because a third of the certificates have no UPRN, and it means
less: a postcode's non-domestic buildings can be a shop, an office and a care home. The query
returns `PROPERTY_TYPE_SHORT` with each building, and the README says the result is a list of
candidate buildings, not a property of the person's home.

uprn-epc's own postcode query has the same order of filter and rank, and 1,593 of its register
numbers carry two or more postcodes. That is a finding for uprn-epc, outside this plan.

Coverage must be stated differently from the domestic README. A non-domestic certificate is
required only on construction, sale or let, and for display in a public building over 250 m²
(note, page 5). Most non-domestic buildings have none, so `uprn_not_in_epc` is the usual result.

### 8. Record the decisions

`decisions.yaml` starts from uprn-epc's entries that still hold, each with this release's
evidence, and adds:

- one file, so the key has no year, a member is identified by its file, and the check on
  `CREATED_AT` is against the release quarter;
- `width` is the accepted length, and a width over 4,000 is stored as `nvarchar(max)`;
- `pc_norm` removes tabs as well as spaces, in the build and in the query;
- `Data removed` is the publisher's missing value in four named columns, with the two checks;
- which numbers get a typed copy, the three shared quantities and the potential rating among them;
- the band text is kept as published, `Carbon Neu` included;
- the join output has its own measurement columns, and none under a domestic name;
- the postcode route chooses the building's latest certificate first and compares its postcode
  after.

## A view over both registers, later

A local note of 14 November 2026, not in this repository, proposes one thin view over
`epc_domestic` and `epc_nondomestic`. It is not part of this build. It gets its own short plan once
the table is loaded and the matched count for a real cohort is known. That plan has to settle four
things this profile found:

- the two tables are different releases today;
- 2,005 UPRNs are in both registers. The type of a UPRN is taken from its current non-domestic
  certificate, so the count does not depend on the order of the rows. 1,162 have no current
  non-domestic certificate, and 1,154 of those have a later domestic lodgement. Whether that is a
  replacement is for that plan to establish. Of the other 843, 240 are retail,
  123 offices, 122 hotels, 89 restaurants, 83 residential spaces and 46 hospitals or care homes.
  84 of the 2,005 have had a hospital or care home certificate at some time;
- the file cannot tell a care home from a hospital. `property_class` can say "hospital or care
  home", not either one. Telling them apart needs another source, for example the Care Inspectorate
  list of registered care homes;
- there are 1,894 hospital or care home certificates, 1,484 of them current, and 955 of those have
  a UPRN.

## Tests

uprn-epc's tests, on a synthetic release of one file with 38 columns, each hostile file failing
with its own named check. New or changed cases:

- A registry with one member and no year loads. A file with the domestic header (`ADDRESS3` where
  `POST_TOWN` should be) fails the header check.
- A 4,451-character `IMPROVEMENT_RECOMMENDATIONS` builds, the generated definition declares
  `nvarchar(max)`, the notebook parses that definition with every column present, and the value
  loads and digests the same on both sides by both routes. An 8,001-character value fails the
  schema check. A value one character too long for a bounded column fails it too.
- A postcode matches when the tab is in the source, when it is in the cohort, and when it is in
  both. A cohort postcode of spaces and tabs only is `no_postcode`.
- `Data removed` in the potential rating gives NULL in `potential_energy_performance_rating_num`.
  `Data Removed` in other capitals, in the potential rating or in `ASSET_RATING`, stops the build.
  `Data removed` in a rating whose band is a letter stops the build, and so does the reverse.
  `Data removed` in `FLOOR_AREA` stops the build as a number that does not parse.
- `-0` stays `-0` and `Carbon Neu` stays `Carbon Neu` in the text columns.
- A negative rating and a two-decimal emission rate parse, and the typed copy equals the text.
- A `CREATED_AT` after the release quarter stops the build.
- A cell with a tab, a cell with a trailing space and a cell with U+FFFD read back from SQL Server
  as published.
- Each of the three queries runs against the generated schema and returns exactly its columns of
  section 7, in order. The undated query returns no `cohort_date`, `epc_age_days`, `historic_flag`
  or tie column. A row that is not `matched` has NULL in every certificate column. `epc_age_days`
  equals the days from the inspection to the cohort date. No query file names a clock function.
- UPRN joins: the cases of `EPC_Plan.md`, plus a building with no current certificate, and a
  building whose current certificate is not the one inspected last.
- Postcode join: a building with a certificate at postcode A and a later one at postcode B. A
  cohort date between the two returns it at A and not at B. A date after both returns it at B, and
  a cohort row at A gets `no_building_at_postcode_by_date`. Two certificates of a building without
  a UPRN inspected on one day follow the tie rule. Two tied certificates at different postcodes
  give `ambiguous_as_of` at both, with the building's `uprn_osg` and no certificate values.

## Order of work

1. Done 11 November 2026: archive downloaded.
2. Done 14 November 2026: archive, CSV and note copied to `data/sources/epc_nondomestic_2026Q3/`
   with a `SOURCES.md`, hashes checked against the archive members, file profiled.
3. Done 14 November 2026: plan reviewed twice and revised. Each finding was reproduced with a
   probe kept in `docs/reviews/`.
4. Done 14 November 2026: archive, note and checksums copied to
   `onedrive:dataset_healscot/EPC_nondomestic/`, sizes and hashes compared. Restricted Zenodo
   draft 24224180 created with the same three files, MD5-verified, not published. The files of
   the load (CSV, manifest, two SQL scripts, loader, upload notebook, data dictionary) copied to
   `onedrive:dataset_healscot/EPC_nondomestic/load_2026Q3/`, sizes and hashes compared.
5. Done 14 November 2026: the tree ported from uprn-epc `d3d1ea4` as package `epc_nd_ingest`, the
   registry, `published_columns.yaml` and the generated schema of 57 columns. The repository was
   created on GitHub the same day (`docs/plans/GitHub_and_Provenance_Site_Plan.md`).
6. Done 14 November 2026: the modules listed above ported for one file, the 8,000 bucket and the
   `max` type added, 103 tests on a synthetic release.
7. Done 14 November 2026: the real build, 95,719 rows, 46 checks passed (`results/manifest.json`,
   `results/BUILD_REPORT.md`), and the data dictionary.
8. Done 14 November 2026: the import and check scripts, the loader and the notebook. The two
   container probes passed (`docs/sql/SQLSERVER_PROBE_2026-11-14.md`,
   `docs/sql/NOTEBOOK_PROBE_2026-11-14.md`).
9. Done 14 November 2026: the three join queries, tested in DuckDB and in the probe. The README.
10. Done 14 November 2026: column descriptions from the note, reviewed against the PDF
    (`docs/reviews/2026-11-14-column-descriptions.md`). The provenance site is published at
    https://mtinti.github.io/uprn-epc-nondomestic/.
11. Done 14 November 2026: the implementation reviewed
    (`docs/reviews/2026-11-14-nondomestic-implementation-review.md`), one finding, fixed and
    probed again (`-response.md` beside it).
12. Not done: the load into the HIC server, for Michele to run.
13. Not done: the plan for the view over both registers.

### What the implementation settled or changed

- **`pc_norm` is `nvarchar(32)`, not 8.** It can never be longer than `POSTCODE`, whose own width
  already stops the build, so a second, narrower limit would only stop a build on one odd
  postcode. The build report counts values outside 5 to 7 characters. Today there are two.
- **Three join indexes, not two.** The postcode query first finds the buildings at a postcode and
  then reads each building's certificates over all its postcodes. It needs an index on `pc_norm`
  and one on `uprn_sepcr` with the inspection date.
- **The registry refuses anything but one member.** The key has no file component, so a second
  file would repeat `source_row`.
- **The `max` column binds through pyodbc with size 0.** The notebook probe showed the 4,451 and
  7,999-character values arrive whole. The pyodbc documentation does not describe the binding, so
  step 4 of the notebook reads the longest stored value back and stops if it is shorter than the
  longest sent.
- **The notebook had to allow an empty cell in a nullable decimal.** uprn-epc has no nullable
  decimal, and its pre-send check refused the NULLs of the potential rating. The notebook probe
  found it on its first run.
- **`BULK INSERT` keeps a tab, a trailing space and the replacement character.** The container
  probe counted each in SQL Server and compared with the manifest. It ran the Linux route, from a
  UTF-16 file. The Windows route with `CODEPAGE = '65001'` is first exercised by the load at HIC.
- **The postcode query prints a warning on SQL Server**, "Null value is eliminated by an
  aggregate", because `MAX(uprn_osg)` skips certificates without a UPRN. It is a message, not an
  error, and the query's header says so.
- **Text is measured in UTF-16 code units.** The first implementation counted characters, in the
  build's width check and in the notebook. The implementation review found that a value with a
  supplementary character at a column's limit would pass and not fit, and that the notebook's
  read-back of the `max` column would stop a faithful load. Both now count as SQL Server does.
  The release holds no such character. The probes carry them in a fixture.
- **The note extraction tool was rewritten.** The non-domestic note defines all 38 fields with
  one label each, so the tool cuts the text at the labels and has a `--check` mode that compares
  the committed descriptions with a fresh extraction.

## Open questions

1. **Own repository, or a second table inside uprn-epc.** This plan assumes its own repository,
   as `EPC_Plan.md` settled for the three earlier products. The cost is a fourth copy of `core/`
   and of the SQL generator. Three modules of `core/` already differ between uprn-epc and
   datazone-ahah, and `core/sources.py` and `core/output.py` change again here.
2. **Whether to rebuild the domestic table to 2026Q3**, so both tables describe the register at the
   same quarter. This needs the Q3 domestic archive, which was not checked for this plan, and is
   possible only while that archive is at its URL.
3. **Which other numbers get a typed copy.** The potential rating has one since the review.
   Candidates left: `ASSET_RATING`, `TARGET_EMISSIONS`, `APPROXIMATE_ENERGY_USE`.
4. **Whether a resident's UPRN is the building's UPRN.** A room or flat inside a care home or a
   hall can have its own UPRN under the building's. The file does not say which level a
   certificate's UPRN is at. If a cohort's UPRNs are at the lower level, the UPRN join will miss,
   and the answer needs the Gazetteer's parent UPRN, which OS Open UPRN does not carry.
5. **Whether every UPRN exists in OS Open UPRN.** uprn-epc's `tools/uprn_check_os_open_uprn.py`
   answers it for the 51,879 values.
6. **Whether one current certificate per building should stop the build or be counted.** Today no
   building has two. The domestic check counts, because 22 dwellings break it.
7. **Whether the postcode query of uprn-epc should take the same change.** It filters by postcode
   before it ranks, as this plan's first version did.

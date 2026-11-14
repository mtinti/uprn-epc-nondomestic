# uprn-epc-nondomestic

[![ci](https://github.com/mtinti/uprn-epc-nondomestic/actions/workflows/ci.yml/badge.svg)](https://github.com/mtinti/uprn-epc-nondomestic/actions/workflows/ci.yml)

**Column provenance site:** https://mtinti.github.io/uprn-epc-nondomestic/ , one page per column: what it is (the
publisher's own definition from the publication note), the pinned file it comes from, what was
done to it, which checks guard it and the decisions behind it. Generated from the repository's
metadata on every push. It holds no data value.

Scottish non-domestic Energy Performance Certificates (EPCs) for SQL Server, one row per
certificate, joinable to a cohort by UPRN and date. The recipe is public. The built table is not.

The Scottish Government publishes an extended historic extract of the non-domestic EPC register
every quarter: every certificate lodged since January 2013, superseded ones included, with the
address, the postcode, the One Scotland Gazetteer UPRN, the building type, the rating, the floor
area and 30 other fields. This project turns one release of it into one table, every value exactly
as published. It is built the way [uprn-epc](https://github.com/mtinti/uprn-epc) builds the
domestic register, and [postcode-simd](https://github.com/mtinti/postcode-simd) and
[datazone-ahah](https://github.com/mtinti/datazone-ahah) before it: pinned sources, blocking checks,
typed copies by documented rules, a CSV with a row digest, generated import and check scripts, and
a loader.

It answers for the buildings the domestic table cannot see: care homes, hospitals, residential
schools, student halls, and every shop, office and school.

## Words used here

- **Non-domestic certificate.** The publisher's term. "Commercial" is avoided, because the register
  also holds schools, health buildings, courts and care homes.
- **Building.** What one certificate assesses: a building or a building unit. A shop in a parade
  is a building in this sense.
- **Register number.** `BUILDING_REFERENCE_NUMBER`, the register's own 10-digit number, as the
  integer `uprn_sepcr`. Present in every row. Not a UPRN.
- **UPRN.** `OSG_REFERENCE_NUMBER`, the One Scotland Gazetteer number, as the integer `uprn_osg`.
  The one a cohort links on.
- **Current, superseded.** `HISTORIC` is `False` for the latest certificate of a building and
  `True` for one that a later certificate replaced. It says nothing about expiry.

## What is in the table

`epc_nondomestic`, release 2026Q3: 95,719 certificates from one file, 57 columns in the Parquet,
the CSV and the SQL table, keyed by `epc_release` and `source_row`. Three groups of columns, in
this order:

1. **Key and provenance**: the release and the row's position in the pinned file.
2. **The 38 published columns**, under the publisher's names, as text exactly as published. An
   empty cell is the empty string, never NULL.
3. **Derived columns**, each a typed copy of one published column by one rule: `rrn`,
   `uprn_sepcr`, `uprn_osg`, `pc_norm`, the two data zone codes with a status, the three dates,
   `historic_flag`, the floor area, the current and the potential rating, the building emission
   rate and the primary energy value. Their names carry a kind suffix (`_parsed`, `_flag`, `_int`,
   `_num`) so none equals a published name in another case.

The data dictionary, `docs/DATA_DICTIONARY.md`, lists every column. The build report,
`results/BUILD_REPORT.md`, gives this release's counts.

Six things to know before joining:

- **The rating is not the domestic rating.** A non-domestic rating is an emissions rate, in kg of
  CO2 per square metre per year, and lower is better. Its band runs from A+ to G. The domestic
  rating scores energy cost and higher is better. The same letter means different things in the
  two registers. Compare them only on the three quantities both publish in the same unit:
  `floor_area_int`, `building_emissions_num` and `primary_energy_value_int`.
- **Join by `uprn_osg` as an integer, never as text.** UPRNs run from 8 to 12 digits because each
  council has its own number range. A cohort UPRN padded with zeros matches once both sides are
  bigint.
- **A third of the certificates have no UPRN.** `OSG_REFERENCE_NUMBER` is empty in 33,906 rows
  (35.4%), between 27% and 41% in every year. The address lines and the postcode are the only
  key for those.
- **Most buildings have no certificate.** One is required only on construction, sale or let, and
  for display in a public building over 250 square metres. A cohort row with no match is
  `uprn_not_in_epc`, not an error, and the README of any project using this must say what share
  matched.
- **`HISTORIC = True` means superseded, not expired.** A certificate is valid for ten years. The
  dated join returns the certificate with the latest inspection on or before the cohort date, its
  inspection and lodgement dates and its age in days. The project decides about expiry. 1,243
  UPRNs have no current certificate at all.
- **`Data removed` is the publisher's missing value.** It stands in the potential rating and its
  band (1,712 rows) and in `ASSET_RATING` and its band (12,484 rows). The typed copy of the
  potential rating is NULL there.

The address lines are loaded. `ADDRESS1`, `ADDRESS2`, `POST_TOWN` and `POSTCODE` carry a Royal
Mail notice rather than the Open Government Licence, and nothing built leaves the safe haven: the
CSV goes to the HIC OneDrive and into the HIC SQL Server only. An analyst-facing view without the
three address columns is suggested. Who may see them is a question for information governance.

## Build

```
pip install -r requirements.txt
python -m epc_nd_ingest.pipeline --verify-archive   # results/epc_nondomestic.parquet, .csv.gz, manifest.json, BUILD_REPORT.md
python -m epc_nd_ingest.sql_check                   # docs/sql/import_csv.sql, check_loaded_digest.sql
python -m epc_nd_ingest.dictionary                  # docs/DATA_DICTIONARY.md
python loader/make_notebook.py                      # loader/upload_epc_nondomestic.ipynb
python -m pytest
```

The build reads the pinned files under `data/sources/`. Their hashes are in each folder's
`SOURCES.md` and in `epc_nd_ingest/sources.yaml`. It stops on any of these:

- a changed byte, a header that differs from the pin, or a row count that differs;
- a date, flag, integer or decimal that does not parse;
- a certificate lodged after the last day of the release quarter;
- a rating that is neither a number nor exactly `Data removed`, or that disagrees with its band;
- a text longer than its column accepts;
- a data zone code that is well formed but in neither pinned list;
- a repeated report reference number, or two property numbers that are not one to one.

It never goes through a float. Everything else it finds is counted in the build report and never
repaired. The source files are not in this repository:
`data/sources/epc_nondomestic_2026Q3/SOURCES.md` says where they came from and how to get them
again.

## Load into SQL Server

Carry `results/epc_nondomestic.csv.gz`, `results/manifest.json`, the two scripts in `docs/sql/`
and `loader/load_epc_nondomestic_to_sqlserver.py` to the server. Fill in the EDIT block and run
the loader. It verifies the file hash, imports with `BULK INSERT` through a staging table,
restores the empty strings on published columns and NULL on derived ones, builds the three join
indexes, and runs the check script. The expected row count and digest come from the manifest,
never from the loaded table.

The import names `CODEPAGE = '65001'` so the file is read as UTF-8. SQL Server for Linux rejects
that option. There, convert the CSV to UTF-16 and import it as `widechar`, as the probe does.

When the server cannot read the client's files, which rules out `BULK INSERT`, use
`loader/upload_epc_nondomestic.ipynb` instead. It sends the rows through pyodbc in chunks, keeps
the same rule for empty and NULL, builds the three indexes, runs the same digest check and shows
the table in use. Regenerate it after a rebuild with `python loader/make_notebook.py`.
The notebook is committed with an empty connection string, `CONN`, which the analyst fills in at step 1. A copy for one site is written with `python loader/make_notebook.py results local/upload_epc_nondomestic.ipynb --site local/site_connection.txt`, where the file holds that site's ODBC connection string on one line. `local/` is ignored by git, and the generator refuses to write such a copy anywhere else inside the repository.

One column, `IMPROVEMENT_RECOMMENDATIONS`, is `nvarchar(max)`: three of its values are longer than
the 4,000 characters a bounded `nvarchar` holds. Every text column still has a width, the longest
value the build accepts, and a longer value in a later release stops the build. Widths are counted
as SQL Server counts them, in UTF-16 code units: an emoji or another character outside the Basic
Multilingual Plane counts as two. This release holds no such character.

Two container probes exercise both routes against a throwaway SQL Server 2022.
`loader/sqlserver_probe.sh` runs the import and check scripts on the full build and asserts SQL
Server's rendering of chosen cells, the counts of empty against NULL, the cells this extract is
awkward for (a tab, a trailing space, the replacement character, a cell over 4,000 characters),
that the digest fails when one of them is changed, and the join queries. It also imports a small
fixture that holds what the release does not, characters that take two UTF-16 code units.
`loader/notebook_probe.sh` runs the notebook's own cells on that 16-row fixture under thirteen
scenarios. Records:
`docs/sql/SQLSERVER_PROBE_2026-11-14.md` and `docs/sql/NOTEBOOK_PROBE_2026-11-14.md`.

## Join

Three queries in `docs/sql/`, each a left join so no cohort row disappears, each returning one
status per cohort row, each choosing the certificate explicitly. The cohort table carries a unique
`cohort_row_id` beside the person identifier, because a person appears many times in a
longitudinal cohort and each observation must get the certificate for its own date and address.
The queries stop if the row identifier is NULL or repeats. No query reads the clock.

- `join_by_uprn.sql`: the certificate with the latest inspection on or before the cohort date.
  Statuses `matched`, `no_uprn`, `uprn_not_in_epc`, `no_certificate_by_date`, `ambiguous_as_of`.
  A tie on the latest eligible day is broken by the current certificate, then the latest lodged.
- `join_latest_by_uprn.sql`: without a date, the current certificate. Statuses `matched`,
  `no_uprn`, `uprn_not_in_epc`, `no_current_certificate`, `ambiguous_latest`. It returns no cohort
  date, age, superseded flag or tie column, because none applies to it.
- `join_by_postcode.sql`: the fallback for a cohort row without a UPRN, one row per building that
  was at the postcode as of the cohort date. A building whose later certificate carries another
  postcode is not returned at the old one. Extra status `no_building_at_postcode_by_date`. The
  result is a list of candidate buildings, not a property of the person's home: the buildings of
  one postcode can be a shop, an office and a care home. The cohort postcode is normalised like
  `pc_norm`: upper case, spaces and tabs removed.
- `onward_to_simd_and_ahah.sql`: a sketch from a matched certificate to postcode-simd's SIMD of
  the lodgement date and to datazone-ahah version 4.

Each query returns the non-domestic measurements under their own names
(`CURRENT_ENERGY_PERFORMANCE_BAND`, `current_energy_performance_rating_int` and the rest), never
under a domestic name. The queries are tested in DuckDB against a table created from the generated
schema (`tests/test_joins.py`) and on SQL Server by the container probe.

## Limits

- **Hospitals and care homes are one building type.** Neither `PROPERTY_TYPE` nor
  `PROPERTY_TYPE_SHORT` separates them. Telling them apart needs another source.
- **A resident's UPRN may not be the building's UPRN.** A room or flat inside a care home or a
  hall can have its own UPRN under the building's. The file does not say which level a
  certificate's UPRN is at.
- **No view over both registers.** A view that puts this table beside `epc_domestic` is not part of
  this build (`docs/EPC_NonDomestic_Plan.md`). The two tables are different releases today.
- **`source_row` means nothing outside this release.** The file is in no order, and a later
  release will order its rows differently. `rrn` identifies a certificate across releases where
  it is present. It is empty in 126 rows.

## Sources, licence and archive

Scottish Government, *Non-domestic Energy Performance Certificates, extended historic dataset,
January 2013 to Q3 2026*,
https://data.gov.scot/dataset/non_domestic_energy_performance_certificates___extended_historic_dataset_to_q1_2026
(the slug says Q1, the file is Q3, and the URL is overwritten every quarter). The publication note
gives 21 October 2026 as the extraction date. Downloaded 11 November 2026, archive SHA256
`388d7d40438971c051515676827840df4f461fcc73b8fabe0d033b07cbc39c06`. Open Government Licence v3.0
for every field except the three address lines and the postcode, which carry a Royal Mail
copyright notice (publication note, page 2). Two data zone reference lists are pinned from the
sibling projects (`data/sources/datazones/SOURCES.md`).

Because the download URL does not last and the address fields are not under the Open
Government Licence, the archive is held as an unpublished restricted Zenodo draft rather than an
open record (deposition 24224180, reserved DOI 10.5281/zenodo.24224180, which resolves only once
the record is published), and a copy sits on the HIC OneDrive. The built table is private.

If a source is no longer at its publisher's address, `python tools/restore_sources.py --token-file <file>`
restores every pinned file from Zenodo: the archive from that draft, the note and the extract
from the archive, and the two data zone lists from the public records of postcode-simd and
datazone-ahah. Each file is checked against its pinned SHA256, a file already in place is never
overwritten, and `--check` shows what would be restored and writes nothing there. While the
record is an unpublished draft only its owner's token can read it. A build from the restored
files gave the CSV hash the manifest records (run of 14 November 2026).

## Documents

- `docs/EPC_NonDomestic_Plan.md`: the plan, the facts found in the file, the design, the decisions.
- `docs/DATA_DICTIONARY.md`: every column.
- `docs/profile_2026-11-14.txt`: the profile of the file, written by `tools/profile_nondomestic.py`.
- `docs/UPDATING.md`: taking a new quarterly release.
- `docs/sql/`: the generated scripts, the join queries and the two probe records.
- `docs/reviews/`: the plan reviews, the responses and their probes.
- `epc_nd_ingest/decisions.yaml`: the decision log.

## Notes for developers

- The code is a port of uprn-epc at commit `04bbbda`, which the reviews of 14 November 2026 cite by
  its hash before uprn-epc's history rewrite, `d3d1ea4`. `docs/EPC_NonDomestic_Plan.md` lists every
  module that changed and why.
- The column provenance site is generated from committed metadata:
  `python -m epc_nd_ingest.provenance_site && mkdocs build`. It holds no data value.
- The column descriptions quote the publication note.
  `python3 -P tools/extract_note_dictionary.py <note.pdf> --check` compares the committed file
  with a fresh extraction.
- Save every review to a dated file in `docs/reviews/` (`AGENTS.md`).

Code: MIT (`LICENSE`). Michele Tinti, Health Informatics Centre, University of Dundee.

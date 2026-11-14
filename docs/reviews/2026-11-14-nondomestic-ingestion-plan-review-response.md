# Response to the non-domestic ingestion plan review of 14 November 2026

Review: `2026-11-14-nondomestic-ingestion-plan-review.md`. Each finding was reproduced before the
plan was changed, by calling the code of uprn-epc at commit `d3d1ea4` or by reading the pinned
extract. The probe is `2026-11-14-nondomestic-ingestion-plan-review-response-probe.py` and its
output is the `.out` file beside it. All six findings hold. `docs/EPC_NonDomestic_Plan.md` was
revised the same day. What changed:

| # | Finding | Holds | Change |
| --- | --- | --- | --- |
| 1 | The plan promised the domestic output columns, which do not exist in the new table, and the queries join back through `source_year` | yes. The queries select `CURRENT_ENERGY_RATING`, `current_energy_efficiency_int`, `total_floor_area_int`, `BUILT_FORM`, `CONSTRUCTION_AGE_BAND`, `TENURE` and join on `source_year` | Section 7 now lists the output columns in four groups: the columns shared with uprn-epc, the non-domestic measurements under their own names, the three quantities shared with dwellings, and the columns of the postcode query. No non-domestic value takes a domestic name. The queries join back by `(epc_release, source_row)`. A test and the container probe run each query against the generated schema and compare the column names with the list. |
| 2 | The three listed edits for `nvarchar(max)` do not cover the copied code, and `core/` is not unchanged | yes. `load_schema` refuses width `max` and a missing width. `load_registry` raises `KeyError: 'year'` for a member without a year. The notebook's pattern parses a three-column definition with an `nvarchar(max)` column as two columns | The schema keeps two things apart. `width` stays an integer for every text column and is the longest value the build accepts. The SQL type follows from it: `nvarchar(width)` up to 4,000, `nvarchar(max)` above. The buckets gain 8,000, so `IMPROVEMENT_RECOMMENDATIONS` is still stopped by the schema check if it grows past that. A member is identified by its file. The plan no longer says `core/` is copied unchanged. It lists every module that names a year, a width or the domestic columns, with the reason. Two tests and one probe case were added: a one-member registry loads, the notebook parses the generated definition with every column present, and the 4,451-character value passes through both routes. |
| 3 | The postcode fallback returns a building at an old postcode with its older certificate | yes. 258 register numbers carry two or more `pc_norm`. As of 30 September 2026 the inherited selection returns 262 building and postcode pairs that the building's latest certificate contradicts | The fallback is defined as "buildings at the postcode as of the cohort date". The query chooses each candidate building's latest eligible certificate over all its postcodes, then keeps the building only if that certificate carries the cohort's postcode. A cohort row whose postcode has certificates by the date, all on buildings since recorded elsewhere, gets the new status `no_building_at_postcode_by_date`. Fixtures added: a postcode change with cohort dates on both sides, a tie between two certificates without a UPRN, and a tie across two postcodes. |
| 4 | The cohort postcode was normalised by a different rule from the source | yes. With spaces only on the cohort side, one of three cohort spellings of one postcode matches. With spaces and tabs, all three match | One rule on both sides: upper case, every space and tab removed, an empty result is no postcode. Tests cover a tab in the source, in the cohort and in both. The build report counts `pc_norm` values with a character other than a letter or a digit. Today there is none. |
| 5 | No typed column could show `Data removed` becoming NULL | yes. The four typed numbers of the first plan hold no `Data removed`. It occurs in the potential rating (1,712) and in `ASSET_RATING` (12,484) | `POTENTIAL_ENERGY_PERFORMANCE_RATING` gets a nullable typed copy, `potential_energy_performance_rating_num`. `ASSET_RATING` stays text. Two blocking checks cover the four columns that can hold the text, typed or not: a rating cell is a number or exactly `Data removed`, and a rating is `Data removed` exactly when its band is. The tests name the column each case acts on. |
| 6 | The overlap by property type depended on the order of the rows | yes. The profile kept the type of the last row read for each UPRN. Hospital or care home counts 82 by that rule, 84 by any certificate and 46 by the current certificate. 2,266 UPRNs carry two or more types | `tools/profile_nondomestic.py` now takes the type of a UPRN's current non-domestic certificate and counts UPRNs without one apart. The profile was regenerated and the plan quotes the new figures. The total of 2,005 is stated apart from the breakdown. The probe shuffles the rows and gets the same breakdown. |

## Found while reproducing

- **Most UPRNs without a current non-domestic certificate are also in the domestic table.** 1,162
  of the 2,005 shared UPRNs have no current non-domestic certificate. 1,154 of those have a
  domestic certificate lodged after their last non-domestic one, and 1,156 have a current domestic
  certificate. This suggests a move from one register to the other. The extracts do not establish
  why. The first version of this response called these buildings "converted to dwellings". The
  follow-up review found that stronger than the evidence, and the wording was corrected the same
  day.
- **uprn-epc's postcode query has the defect of finding 3.** It has the same order of filter and
  rank, and 1,593 register numbers in `epc_domestic` 2026Q2 carry two or more `pc_norm`. Nothing in
  uprn-epc was changed. The plan lists it as open question 7.
- **Same-day pairs by register number.** The review counted 11, one with a UPRN. The profile now
  prints both counts, the plan quotes them, and a postcode fixture has a tie without a UPRN.

## What the added tests do not cover

- How SQL Server stores a trailing space and a tab through `BULK INSERT`, and how pyodbc binds an
  `nvarchar(max)` parameter, are not yet checked. They are the probe cases of section 6 and stay
  open until the probes run.
- The postcode rule removes two characters, space and tab. Another whitespace character in a
  later release is not removed. The build report's count of `pc_norm` values with a character
  other than a letter or a digit is what would show it.
- The postcode fixtures use one building per postcode change. A building that returns to an
  earlier postcode is not a fixture.
- No fixture has a UPRN whose register number changes, because the build stops on that.

My findings from this review are closed in the plan. Nothing is implemented, so none is closed in
code.

## Not changed

The choice of `nvarchar(max)` for the long column, the source pinning, the values kept as
published, the statuses of the UPRN joins and the tie rule stand as the review found them.

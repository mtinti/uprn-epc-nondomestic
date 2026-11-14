# Scottish non-domestic EPC ingestion plan review

14 November 2026. Reviewed `docs/EPC_NonDomestic_Plan.md` against the pinned extract, its profile and publication note, and the domestic implementation at `d3d1ea40a4269e9a6d3dbd63bd2b54e677fdfac4`.

**Verdict: revise before implementation.** Source pinning, preservation of published text, explicit linkage statuses and the proposed load probes are sound. Six findings below need changes to the implementation contract or its supporting evidence. P1 denotes a blocking contract problem; P2 denotes a correctness gap to resolve during revision.

1. **[P1] Define the non-domestic query output instead of promising the domestic columns.**

   Location: [plan line 239](../../docs/EPC_NonDomestic_Plan.md#L239), alongside the derived-column table at line 156.

   The plan promises the same output columns as the three domestic queries. Those queries select `CURRENT_ENERGY_RATING`, `current_energy_efficiency_int`, `total_floor_area_int`, `BUILT_FORM`, `CONSTRUCTION_AGE_BAND` and `TENURE`; none exists under those names in the proposed table. They also join back through `source_year`, which the new key removes. A literal copy will not execute, and the plan supplies no replacement output contract.

   Renaming non-domestic ratings to fill the domestic rating columns would create a second problem: the domestic energy-efficiency score measures energy cost, while the non-domestic score measures emissions. They are not interchangeable measurements. The distinction is explicit in the [Scottish Government's description of the existing EPC systems](https://www.gov.scot/publications/energy-performance-buildings-scotland-regulations-2025-amended-energy-performance-buildings-scotland-amendment-regulations-2026-equality-impact-assessment-eqia-results/pages/3/).

   Specify the common identity, date, status and tie-diagnostic columns, then list the non-domestic measurement columns with their own names. Return the three shared quantities if those are intended for downstream use. Leave the combined view's mapping to its separate plan. Acceptance should execute all three queries against the actual generated schema and check their column names and meanings.

   Code evidence: [dated UPRN query](https://github.com/mtinti/uprn-epc/blob/04bbbda/docs/sql/join_by_uprn.sql#L90), [postcode query](https://github.com/mtinti/uprn-epc/blob/04bbbda/docs/sql/join_by_postcode.sql#L72).

2. **[P1] Expand the migration contract beyond the three listed MAX edits.**

   Location: [plan line 117](../../docs/EPC_NonDomestic_Plan.md#L117) and [line 209](../../docs/EPC_NonDomestic_Plan.md#L209).

   The proposed MAX column is necessary for the pinned release, but the listed changes do not cover the assumptions in the copied code:

   - `core/output.py:44` requires every string width to be an integer. Passing `width: max` to the existing schema loader raises `ValueError`; an omitted or null width also fails. `reader.py:179` and staging generation in `sql_check.py:214` compare widths numerically.
   - `loader/make_notebook.py:223` recognises only `nvarchar(\d+)`. It silently omits an `nvarchar(max)` column while parsing the generated DDL, before input binding is reached. Changing only `setinputsizes` cannot fix this.
   - `core/sources.py:55` and `core/output.py:57` require a `year` for every source member. A single member without that artificial annual-file attribute raises `KeyError('year')`. The unchanged output metadata also describes 107 published columns.

   Define the schema representation first: either explicitly support an unbounded width throughout the consumers, or distinguish a numeric ingestion limit from the SQL storage type. Define file-based source provenance for the single extract. Then name the required changes to schema validation, reader widths, staging, notebook DDL parsing and metadata, instead of saying all of `core/` is unchanged. The choice of `nvarchar(max)` itself agrees with [Microsoft's type documentation](https://learn.microsoft.com/en-us/sql/t-sql/data-types/nchar-and-nvarchar-transact-sql?view=sql-server-ver17).

   Acceptance should build a single-member fixture, generate and parse the complete schema, and carry the 4,451-character value through both loading routes with every expected column present. Temporary probes against the pinned domestic code reproduced the schema rejection, missing-year rejection and notebook parser omission.

3. **[P2] Prevent the postcode fallback from selecting an obsolete certificate after a postcode change.**

   Location: [plan line 247](../../docs/EPC_NonDomestic_Plan.md#L247).

   The inherited query filters certificates to the cohort postcode before choosing the latest inspection for each building. Consequently, a building with a 2020 certificate at postcode A and a 2025 certificate at postcode B still appears as a match at A for a 2026 cohort, carrying its older assessment. This differs from choosing the building's latest eligible certificate and returning it when its postcode matches.

   This case occurs in the pinned data: 258 register numbers have more than one postcode after the proposed space/tab normalisation. At a cohort date of 30 September 2026, each has an unambiguous latest certificate; together they have 262 other historical building/postcode combinations. A reduced DuckDB reproduction of the inherited selection returned the old certificate in the example above.

   Specify whether the fallback means buildings at the postcode as of the cohort date or buildings ever recorded there. For the stated dated fallback, rank eligible certificates across all postcodes for each register number before comparing the selected postcode, while retaining the existing ambiguity handling. Add a fixture with a postcode change and cohort dates on both sides of it. If historical candidates are intentional, label that behaviour explicitly rather than reporting them as ordinary matches.

   Code evidence: [postcode filter before ranking](https://github.com/mtinti/uprn-epc/blob/04bbbda/docs/sql/join_by_postcode.sql#L35).

4. **[P2] Apply the same postcode normalisation to the cohort and the source.**

   Location: [plan line 251](../../docs/EPC_NonDomestic_Plan.md#L251), compared with line 162 and the test at line 295.

   The source removes spaces and tabs, but the cohort removes spaces only. A source and cohort both containing the synthetic value `EH1\t1AA` therefore produce different keys and fail to match. Documenting this limitation does not prevent the false negative, and testing a tab only on the source side would miss it.

   Use the same normalisation on both sides, including the treatment of an empty normalised result. Require matches with a tab in the source, in the cohort, and in both. A reduced SQL/Python reproduction confirmed the mismatch under the proposed rules and a match when both remove tabs.

5. **[P2] Reconcile the Data removed acceptance test with the selected typed columns.**

   Location: [plan line 171](../../docs/EPC_NonDomestic_Plan.md#L171) and [line 297](../../docs/EPC_NonDomestic_Plan.md#L297).

   The four numeric typed copies currently specified are floor area, current rating, building emissions and primary energy. None has `Data removed` in this release. The sentinel occurs in potential rating and asset rating, which the plan leaves as text; adding potential rating remains an open question. There is therefore no declared numeric output column in which the required sentinel-to-NULL test can observe its result.

   Decide whether potential and/or asset rating gets a nullable typed copy now, with its name, type and missing-value rule. Alternatively, defer that conversion and its end-to-end acceptance test, retaining the raw sentinel and the rating/band agreement check. Also scope the rejection of `Data Removed` to named parsed columns or an explicit source-vocabulary check: a text-only rating/band pair does not acquire numeric validation from the current rules.

6. **[P2] Recalculate overlap by property type using an explicit certificate selection.**

   Location: [plan line 279](../../docs/EPC_NonDomestic_Plan.md#L279); underlying calculation at [profile script line 160](../../tools/profile_nondomestic.py#L160).

   The total of 2,005 UPRNs shared with the domestic table is reproducible. The type breakdown is not a defined current or historical classification: `nd_u = {int(o): s ...}` overwrites each UPRN's type with the last certificate encountered in the unordered source file. Across the non-domestic extract, 2,266 UPRNs have more than one `PROPERTY_TYPE_SHORT`, so this is a material assumption.

   For the same 2,005 UPRNs, compared with all UPRNs in the domestic 2026Q2 table, the hospital/care-home count changes with the rule:

   | Non-domestic classification rule | Distinct overlapping UPRNs |
   | --- | ---: |
   | Last row encountered in the CSV, as currently profiled | 82 |
   | Any certificate classified Hospitals/Care Home | 84 |
   | Current certificate classified Hospitals/Care Home | 46 |

   Choose and state the relevant rule, regenerate the breakdown, and keep the total overlap separate from the type-specific claim. Verify that shuffling the source rows leaves the selected breakdown unchanged.

**Validation and limits.** The archive, CSV and publication-note SHA256 hashes and sizes match `SOURCES.md`. The inspected domestic implementation files match the plan's pinned commit. Targeted scans covered all 95,719 non-domestic rows and checked overlap against the local domestic Parquet. Additional profiling found 11 register-number/inspection-day pairs with two certificates, of which only one pair has a UPRN; postcode fixtures should include ties without a UPRN. Python probes exercised the inherited schema and registry loaders, and reduced SQL examples ran in DuckDB. No non-domestic implementation or SQL Server load was run. The plan, profile, source data and domestic project were not changed.

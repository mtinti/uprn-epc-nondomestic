# Build report: epc_nondomestic, release 2026Q3, 2026-11-14T16:51:27Z

Schema `epc_nondomestic_v1`. 95,719 rows by 57 columns in the Parquet, 57 in the CSV.
CSV `epc_nondomestic.csv.gz` SHA256 `d43cd944e613c67e6d6f4ab2c5bc7fa6cf2eecea76ab7c4bffbb5c5d6d7ce686`, digest total `176041734596302563122`.
Parquet SHA256 `d78f22782427744fc013c9ea15833179ec2b95ee422e6b9fc8dd2fde61088928`.

## Rows by the year of lodgement on the register

The extract is one file. The year is that of `created_at_parsed`.

| Year | Rows | HISTORIC True | HISTORIC False | Empty UPRN | Empty RRN |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2013 | 7,124 | 2,617 | 4,507 | 2,169 | 20 |
| 2014 | 7,500 | 2,580 | 4,920 | 2,003 | 13 |
| 2015 | 6,689 | 2,096 | 4,593 | 2,153 | 19 |
| 2016 | 7,139 | 1,532 | 5,607 | 2,427 | 10 |
| 2017 | 7,066 | 1,329 | 5,737 | 2,375 | 8 |
| 2018 | 6,353 | 1,196 | 5,157 | 2,158 | 8 |
| 2019 | 6,695 | 957 | 5,738 | 2,596 | 5 |
| 2020 | 5,009 | 663 | 4,346 | 1,860 | 3 |
| 2021 | 6,454 | 760 | 5,694 | 2,617 | 5 |
| 2022 | 6,998 | 807 | 6,191 | 2,457 | 7 |
| 2023 | 8,096 | 577 | 7,519 | 3,077 | 9 |
| 2024 | 7,924 | 372 | 7,552 | 3,052 | 7 |
| 2025 | 7,273 | 247 | 7,026 | 2,909 | 5 |
| 2026 | 5,399 | 112 | 5,287 | 2,053 | 7 |

## What the release holds

Counted and reported. None of these stops the build and nothing is repaired.

| Fact | Value |
| --- | --- |
| Distinct Gazetteer UPRNs (`uprn_osg`) | 51,879 |
| Distinct register numbers (`uprn_sepcr`) | 81,302 |
| Rows with no Gazetteer UPRN | 33,906 |
| UPRNs by digit count | 8: 453, 9: 39,577, 10: 4,345, 11: 372, 12: 7,132 |
| Register numbers with a UPRN in some rows and none in others | 0 |
| UPRNs with exactly one `HISTORIC = False` certificate | 50,636 |
| UPRNs with two or more `HISTORIC = False` certificates (`ambiguous_latest`) | 0 |
| UPRNs whose certificates are all `HISTORIC = True` (`no_current_certificate`) | 1,243 |
| Register numbers with two or more `HISTORIC = False` certificates | 0 |
| Register numbers whose certificates are all `HISTORIC = True` | 1,428 |
| Register numbers with two or more `pc_norm` over their certificates | 258 |
| Register number and inspection day with two or more certificates | 11 |
| UPRN and inspection day with two or more certificates | 1 |
| Rows with an empty RRN | 126 |
| `datazone_2001_status` | code: 92,872, empty: 2,553, not_a_datazone: 294 |
| `datazone_2011_status` | code: 93,747, empty: 1,932, not_a_datazone: 40 |
| Distinct 2001 and 2011 data zone codes | 5,107 and 5,382 |
| Rows with `LOCAL_AUTHORITY`, `DATA_ZONE` and `CONSTITUENCY` all empty | 2,553 |
| Rows with a local authority code outside Scotland | 10 |
| Rows with an empty postcode | 0 |
| Distinct `pc_norm` | 26,559 |
| `pc_norm` not 5 to 7 characters | 2 |
| `pc_norm` with a character other than a letter or a digit | 0 |
| Rows with a postcode area outside Scotland | 18 |
| Rows where `pc_norm` removed a tab | 5 |
| Cells with a tab | ADDRESS1: 208, ADDRESS2: 217, POST_TOWN: 92, POSTCODE: 5 |
| Cells with an embedded newline | none |
| Cells with the replacement character U+FFFD | ADDRESS1: 1 |
| Cells that end with a space | ADDRESS2: 129, POST_TOWN: 141, POSTCODE: 12, IMPROVEMENT_RECOMMENDATIONS: 93,392 |
| Cells with a supplementary character, which takes two UTF-16 code units | none |
| Cells longer than 4,000 UTF-16 code units, stored as `nvarchar(max)` | IMPROVEMENT_RECOMMENDATIONS: 3 |
| Cells holding `Data removed` | POTENTIAL_ENERGY_PERFORMANCE_RATING: 1,712, POTENTIAL_ENERGY_PERFORMANCE_BAND: 1,712, ASSET_RATING: 12,484, ASSET_RATING_BAND: 12,484 |
| Rows with `potential_energy_performance_rating_num` NULL | 1,712 |
| `floor_area_int` range | 4 to 138,037; 186 rows under 15, 12,594 over 1,500 |
| `current_energy_performance_rating_int` range | -9,098 to 42,155; 184 rows negative |
| `building_emissions_num` range | -9097.9600 to 42154.6000 |
| `primary_energy_value_int` range | -17,831 to 238,089 |
| Rows where the rating is not the emissions rounded | 473 |
| Rows where the band is not the cut of the rating | 4 |
| `CURRENT_ENERGY_PERFORMANCE_BAND` values | A: 5,048, A+: 2,154, B: 6,207, B+: 5,141, C: 6,882, C+: 5,703, Carbon Neu: 188, D: 7,208, D+: 5,872, E: 7,252, E+: 7,130, F: 5,013, F+: 5,310, G: 26,611 |
| Rows with empty `MEETS_2002_STANDARD` | 22,776 |
| Rows lodged before inspection | 195 |
| Rows inspected after the extraction date | 1 |
| Rows inspected more than a year before lodgement | 1,411 |
| Median days from inspection to lodgement | 8 |
| Rows where `CREATED_AT` and `LODGEMENT_DATE` are different days | 9,897 |
| Inspection date range | 2002-07-27 to 2108-02-01 |
| Lodgement date range | 2013-01-29 to 2026-09-30 |
| `CREATED_AT` range | 2013-01-29 10:48:59 to 2026-09-30 22:24:34 |

## Certificates by `PROPERTY_TYPE_SHORT`

| Value | Rows |
| --- | ---: |
| Retail/Financial | 31,328 |
| Office/Workshop | 24,253 |
| Restaurant/Cafes/takeaway | 9,182 |
| General Industrial | 6,349 |
| Storage/Distribution | 5,808 |
| Education | 3,646 |
| Hotel | 3,501 |
| General Assembly/Leisure | 2,526 |
| Community/Day Centre | 2,300 |
| Hospitals/Care Home | 1,894 |
| Primary Healthcare Building | 1,478 |
| Universities/college | 890 |
| Residential space | 792 |
| Library/Museum/Gallery | 662 |
| Emergency service | 433 |
| Residential school | 255 |
| Passenger terminal | 116 |
| Crown/County Court | 90 |
| Stand alone utility block | 82 |
| Secure Residential Institution | 74 |
| Miscellaneous 24 hr activity | 40 |
| Misc. 24 hr activity | 17 |
| Car Park 24 hrs | 3 |

## Longest text per column against the width it accepts

Both in UTF-16 code units, as SQL Server counts an `nvarchar`: a character outside the Basic Multilingual Plane takes two.

| Column | Longest | Width | SQL type |
| --- | ---: | ---: | --- |
| `epc_release` | 6 | 8 | nvarchar(8) |
| `HISTORIC` | 5 | 8 | nvarchar(8) |
| `BUILDING_REFERENCE_NUMBER` | 10 | 32 | nvarchar(32) |
| `OSG_REFERENCE_NUMBER` | 12 | 32 | nvarchar(32) |
| `ADDRESS1` | 85 | 100 | nvarchar(100) |
| `ADDRESS2` | 50 | 100 | nvarchar(100) |
| `POST_TOWN` | 37 | 100 | nvarchar(100) |
| `POSTCODE` | 10 | 32 | nvarchar(32) |
| `INSPECTION_DATE` | 10 | 32 | nvarchar(32) |
| `LODGEMENT_DATE` | 10 | 32 | nvarchar(32) |
| `PROPERTY_TYPE_SHORT` | 30 | 32 | nvarchar(32) |
| `PROPERTY_TYPE` | 76 | 100 | nvarchar(100) |
| `FLOOR_AREA` | 6 | 8 | nvarchar(8) |
| `CURRENT_ENERGY_PERFORMANCE_RATING` | 5 | 8 | nvarchar(8) |
| `CURRENT_ENERGY_PERFORMANCE_BAND` | 10 | 32 | nvarchar(32) |
| `POTENTIAL_ENERGY_PERFORMANCE_RATING` | 12 | 32 | nvarchar(32) |
| `POTENTIAL_ENERGY_PERFORMANCE_BAND` | 12 | 32 | nvarchar(32) |
| `NEW_BUILD_ENERGY_PERFORMANCE_RATING` | 4 | 8 | nvarchar(8) |
| `NEW_BUILD_ENERGY_PERFORMANCE_BAND` | 2 | 8 | nvarchar(8) |
| `MEETS_2002_STANDARD` | 1 | 8 | nvarchar(8) |
| `ASSET_RATING` | 12 | 32 | nvarchar(32) |
| `ASSET_RATING_BAND` | 12 | 32 | nvarchar(32) |
| `BUILDING_EMISSIONS` | 8 | 32 | nvarchar(32) |
| `RENEWABLE_SOURCES` | 20 | 32 | nvarchar(32) |
| `ELECTRICITY_SOURCE` | 13 | 32 | nvarchar(32) |
| `MAIN_HEATING_FUEL` | 37 | 100 | nvarchar(100) |
| `BUILDING_ENVIRONMENT` | 38 | 100 | nvarchar(100) |
| `PRIMARY_ENERGY_VALUE` | 6 | 8 | nvarchar(8) |
| `APPROXIMATE_ENERGY_USE` | 6 | 8 | nvarchar(8) |
| `IMPROVEMENT_RECOMMENDATIONS` | 4451 | 8000 | nvarchar(max) |
| `LOCAL_AUTHORITY` | 4 | 8 | nvarchar(8) |
| `DATA_ZONE` | 64 | 100 | nvarchar(100) |
| `CONSTITUENCY` | 6 | 8 | nvarchar(8) |
| `CONSTITUENCY_LABEL` | 53 | 100 | nvarchar(100) |
| `TRANSACTION_TYPE` | 50 | 100 | nvarchar(100) |
| `TARGET_EMISSIONS` | 7 | 8 | nvarchar(8) |
| `DATA_ZONE_2011` | 75 | 100 | nvarchar(100) |
| `CREATED_AT` | 19 | 32 | nvarchar(32) |
| `REPORT_REFERENCE_NUMBER` | 24 | 32 | nvarchar(32) |
| `rrn` | 24 | 24 | nvarchar(24) |
| `pc_norm` | 7 | 32 | nvarchar(32) |
| `datazone_2001` | 9 | 9 | nvarchar(9) |
| `datazone_2001_status` | 14 | 16 | nvarchar(16) |
| `datazone_2011` | 9 | 9 | nvarchar(9) |
| `datazone_2011_status` | 14 | 16 | nvarchar(16) |

## Checks

46 passed, 0 failed.

| Check | Result | Detail |
| --- | --- | --- |
| `source.epc_nondomestic_2026Q3/extracted/AltHistoricExtract2013to2026ND.csv` | pass | sha256 matches |
| `source.datazones/SG_SIMD_2012.dbf` | pass | sha256 matches |
| `source.datazones/DataZone2011_lookup.csv` | pass | sha256 matches |
| `source.epc_nondomestic_2026Q3/nondomestic_epc_extended_historic_Q3_2026.7z` | pass | sha256 matches |
| `source.epc_nondomestic_2026Q3/publication_note.pdf` | pass | sha256 matches |
| `schema.matches_generator` | pass | output_schema.yaml is what python -m epc_nd_ingest.columns writes |
| `datazones_2001.count` | pass | 6505 |
| `datazones_2001.distinct` | pass | 6505 |
| `datazones_2011.count` | pass | 6976 |
| `datazones_2011.distinct` | pass | 6976 |
| `extract.utf8` | pass | decoded as UTF-8 |
| `extract.header_names` | pass | 38 columns as pinned |
| `extract.header_labels` | pass | labels as pinned |
| `extract.row_width` | pass | 95719 rows of 38 fields |
| `extract.rows` | pass | 95719 |
| `extract.rrn_shape` | pass | 95593 present, all 9999-9999-9999-9999-9999 |
| `extract.rrn_unique_in_file` | pass | 0 |
| `extract.created_at_within_release` | pass | no CREATED_AT is later than 2026-09-30, the last day of the release quarter |
| `extract.data_removed_ratings` | pass | every POTENTIAL_ENERGY_PERFORMANCE_RATING and ASSET_RATING cell is a number or exactly 'Data removed' |
| `extract.data_removed_pairs` | pass | a rating is 'Data removed' exactly when its band is |
| `extract.derived_values_parse` | pass | every date, flag, integer and decimal the derived columns need parses |
| `extract.text_within_width` | pass | every text value fits the width its column accepts, in UTF-16 code units |
| `extract.decimal_round_trip` | pass | every decimal cell: file text, Decimal, 4-place text, Decimal |
| `readback.parquet.column_names` | pass | ['epc_release', 'source_row', 'HISTORIC', 'BUILDING_REFERENCE_NUMBER', 'OSG_REFERENCE_NUMBER', 'ADDRESS1', 'ADDRESS2', 'POST_TOWN', 'POSTCODE', 'INSPECTION_DATE |
| `readback.parquet.column_types` | pass | ['string', 'int32', 'string', 'string', 'string', 'string', 'string', 'string', 'string', 'string', 'string', 'string', 'string', 'string', 'string', 'string',  |
| `readback.parquet.nullability` | pass | [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False |
| `readback.parquet.metadata.grain` | pass | One row per published non-domestic certificate, superseded certificates included (HISTORIC = True). The 38 published columns are text exactly as published; the  |
| `readback.parquet.metadata.schema_version` | pass | epc_nondomestic_v1 |
| `readback.parquet.metadata.key` | pass | ["epc_release", "source_row"] |
| `readback.parquet.metadata.epc_release` | pass | 2026Q3 |
| `readback.parquet.metadata.decisions_sha256` | pass | 55c429d3f2f88b8712bf15d976063162de8b723ff55d6b5fbd64059f8e9ae8d1 |
| `readback.parquet.metadata.registry_sha256` | pass | 9f98bfbbe671093a3f4d85cbe0575c7579e694531a9d6443d4f96acb45b9f420 |
| `readback.parquet.metadata.sources` | pass | [{"file": "epc_nondomestic_2026Q3/extracted/AltHistoricExtract2013to2026ND.csv", "sha256": "304c03a6217d4d220c0595e00fa6c4c096e619dc14b6b26ac5af017fbb2f712d"}] |
| `readback.parquet.rows` | pass | 95719 |
| `readback.parquet.row_groups` | pass | 1 |
| `readback.parquet.extract.digest` | pass | the row group rendered again gives the digest recorded while writing |
| `readback.parquet.sampled_rows_equal_source` | pass | 3 rows (first, middle, last of the file), 114 published cells compared with the source text |
| `readback.csv.header` | pass | ['epc_release', 'source_row', 'HISTORIC', 'BUILDING_REFERENCE_NUMBER', 'OSG_REFERENCE_NUMBER', 'ADDRESS1', 'ADDRESS2', 'POST_TOWN', 'POSTCODE', 'INSPECTION_DATE |
| `readback.csv.rows` | pass | 95719 |
| `readback.csv.digest_total` | pass | the digest recomputed from the bytes on disk equals the one computed while writing |
| `table.rows` | pass | key unique |
| `table.rrn_unique` | pass | 95,593 present RRNs, none repeated across the release |
| `table.uprn_one_to_one` | pass | where both are present, each Gazetteer UPRN has one register number and the reverse |
| `table.datazone_2001_status.no_unknown_code` | pass | every well formed code is in the pinned list |
| `table.datazone_2011_status.no_unknown_code` | pass | every well formed code is in the pinned list |
| `table.required_nonnull` | pass | {} |

## One certificate cell for cell: row 95719

The source text of the pinned file, which the Parquet holds unchanged (checked for the first, middle and last row of the file). The address lines and the postcode are not printed here.

| Column | Source text |
| --- | --- |
| `HISTORIC` | `False` |
| `BUILDING_REFERENCE_NUMBER` | `1234623978` |
| `OSG_REFERENCE_NUMBER` | `9059088212` |
| `ADDRESS1` | `(withheld)` |
| `ADDRESS2` | `(withheld)` |
| `POST_TOWN` | `(withheld)` |
| `POSTCODE` | `(withheld)` |
| `INSPECTION_DATE` | `2016-12-21` |
| `LODGEMENT_DATE` | `2017-01-05` |
| `PROPERTY_TYPE_SHORT` | `Office/Workshop` |
| `PROPERTY_TYPE` | `Offices and Workshop businesses` |
| `FLOOR_AREA` | `63` |
| `CURRENT_ENERGY_PERFORMANCE_RATING` | `79` |
| `CURRENT_ENERGY_PERFORMANCE_BAND` | `E` |
| `POTENTIAL_ENERGY_PERFORMANCE_RATING` | `67.00` |
| `POTENTIAL_ENERGY_PERFORMANCE_BAND` | `E+` |
| `NEW_BUILD_ENERGY_PERFORMANCE_RATING` | `12` |
| `NEW_BUILD_ENERGY_PERFORMANCE_BAND` | `A` |
| `MEETS_2002_STANDARD` | `N` |
| `ASSET_RATING` | `121` |
| `ASSET_RATING_BAND` | `E` |
| `BUILDING_EMISSIONS` | `79.42` |
| `RENEWABLE_SOURCES` | `None` |
| `ELECTRICITY_SOURCE` | `Grid supplied` |
| `MAIN_HEATING_FUEL` | `Grid Supplied Electricity` |
| `BUILDING_ENVIRONMENT` | `Heating and Mechanical Ventilation` |
| `PRIMARY_ENERGY_VALUE` | `469` |
| `APPROXIMATE_ENERGY_USE` | `156` |
| `IMPROVEMENT_RECOMMENDATIONS` | `Code: EPC-H1; CO2 Impact: HIGH; PayBack Type: Long; Description: Consider replacing heating boiler plant with high efficiency type. \| Code: EPC-H4; CO2 Impact: HIGH; PayBack Type: Long; Description: The default heat generator efficiency is chosen. It is recommended that the heat generator system be investigated to gain an understanding of its efficiency and possible improvements. \| Code: EPC-R2; CO2 Impact: LOW; PayBack Type: Long; Description: Consider installing building mounted wind turbine(s). \| Code: EPC-R3; CO2 Impact: LOW; PayBack Type: Long; Description: Consider installing solar water heating. \| Code: EPC-W1; CO2 Impact: MEDIUM; PayBack Type: Long; Description: Install more efficient water heater. \| Code: EPC-L5; CO2 Impact: HIGH; PayBack Type: Short; Description: Consider replacing T8 lamps with retrofit T5 conversion kit.  \| Code: EPC-L7; CO2 Impact: LOW; PayBack Type: Short; Description: Introduce HF (high frequency) ballasts for fluorescent tubes: Reduced number of fittings required. \| Code: EPC-V1; CO2 Impact: MEDIUM; PayBack Type: Short; Description: In some spaces, the solar gain limit defined in the NCM is exceeded, which might cause overheating. Consider solar control measures such as the application of reflective coating or shading devices to windows. \| ` |
| `LOCAL_AUTHORITY` | `00QJ` |
| `DATA_ZONE` | `S01001106 (Western Edge)` |
| `CONSTITUENCY` | `00QJMC` |
| `CONSTITUENCY_LABEL` | `West End` |
| `TRANSACTION_TYPE` | `Mandatory issue (Non-marketed sale)` |
| `TARGET_EMISSIONS` | `12.19` |
| `DATA_ZONE_2011` | `S01007869 (Western Edge - 05)` |
| `CREATED_AT` | `05/01/2017 16:05:30` |
| `REPORT_REFERENCE_NUMBER` | `9999-2929-9930-9999-8603` |

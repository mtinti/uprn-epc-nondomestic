"""The checks on the whole table, run over the written Parquet with DuckDB, and the counts the
build report states. Blocking: the key is unique; a present RRN is unique across the release;
the two property numbers are one to one; no data zone code is well formed but unknown. Everything
else is an observation: counted, reported and never repaired."""

from __future__ import annotations

from pathlib import Path

import duckdb

from . import columns as col
from .core.checks import Report

SCOTTISH_POSTCODE_AREAS = ("AB", "DD", "DG", "EH", "FK", "G", "HS", "IV", "KA", "KW", "KY", "ML", "PA", "PH", "TD", "ZE")
# The non-domestic band is a fixed cut of the rating (kg of CO2 per square metre per year), read
# from the file: the largest rating of each band. Below zero is 'Carbon Neu', above 100 is G.
BAND_UPPER = ((7, "A+"), (15, "A"), (22, "B+"), (30, "B"), (37, "C+"), (45, "C"), (52, "D+"), (60, "D"),
              (70, "E+"), (80, "E"), (90, "F+"), (100, "F"))


# A character outside the Basic Multilingual Plane, as a DuckDB (RE2) character class.
SUPPLEMENTARY_SQL = r"[\x{10000}-\x{10FFFF}]"


def _sql_length(column: str) -> str:
    """The length SQL Server counts for nvarchar, as a DuckDB expression: the characters, plus one
    for each character outside the Basic Multilingual Plane, which takes two UTF-16 code units."""
    return f"(2 * LENGTH(\"{column}\") - LENGTH(regexp_replace(\"{column}\", '{SUPPLEMENTARY_SQL}', '', 'g')))"


def _one(con, sql: str):
    return con.execute(sql).fetchone()[0]


def _pairs(con, sql: str) -> dict:
    return {str(k): v for k, v in con.execute(sql).fetchall()}


def check_table(parquet: Path, schema: dict, report: Report, extracted: str) -> dict:
    con = duckdb.connect()
    con.execute(f"CREATE VIEW t AS SELECT * FROM read_parquet('{Path(parquet).as_posix()}')")
    key = ", ".join(schema["key"])
    report.equal("table.rows", _one(con, "SELECT COUNT(*) FROM t"), _one(con, f"SELECT COUNT(*) FROM (SELECT DISTINCT {key} FROM t)"),
                 detail="key unique")
    present = _one(con, "SELECT COUNT(*) FROM t WHERE rrn IS NOT NULL")
    report.equal("table.rrn_unique", present - _one(con, "SELECT COUNT(DISTINCT rrn) FROM t WHERE rrn IS NOT NULL"), 0,
                 detail=f"{present:,} present RRNs, none repeated across the release")
    many_sepcr = _one(con, "SELECT COUNT(*) FROM (SELECT uprn_osg FROM t WHERE uprn_osg IS NOT NULL GROUP BY uprn_osg HAVING COUNT(DISTINCT uprn_sepcr) > 1)")
    many_osg = _one(con, "SELECT COUNT(*) FROM (SELECT uprn_sepcr FROM t WHERE uprn_osg IS NOT NULL GROUP BY uprn_sepcr HAVING COUNT(DISTINCT uprn_osg) > 1)")
    mixed = _one(con, "SELECT COUNT(*) FROM (SELECT uprn_sepcr FROM t GROUP BY uprn_sepcr HAVING COUNT(uprn_osg) > 0 AND COUNT(uprn_osg) < COUNT(*))")
    report.equal("table.uprn_one_to_one", {"uprn_osg_with_many_sepcr": many_sepcr, "uprn_sepcr_with_many_osg": many_osg},
                 {"uprn_osg_with_many_sepcr": 0, "uprn_sepcr_with_many_osg": 0},
                 detail="where both are present, each Gazetteer UPRN has one register number and the reverse")
    for status_col in ("datazone_2001_status", "datazone_2011_status"):
        report.equal(f"table.{status_col}.no_unknown_code", _one(con, f"SELECT COUNT(*) FROM t WHERE {status_col} = 'unknown_code'"), 0,
                     detail="every well formed code is in the pinned list")
    nulls = {f["name"]: _one(con, f'SELECT COUNT(*) FROM t WHERE "{f["name"]}" IS NULL') for f in schema["fields"] if not f["nullable"]}
    report.equal("table.required_nonnull", {k: v for k, v in nulls.items() if v}, {})
    report.require()

    obs = {}
    # Rows by the year the certificate was lodged on the register. The file itself has no year.
    obs["rows_per_created_year"] = _pairs(con, "SELECT EXTRACT(year FROM created_at_parsed)::INT, COUNT(*) FROM t GROUP BY 1 ORDER BY 1")
    obs["historic_per_created_year"] = {str(y): {"True": t, "False": f} for y, t, f in con.execute(
        "SELECT EXTRACT(year FROM created_at_parsed)::INT, SUM(CASE WHEN historic_flag THEN 1 ELSE 0 END), SUM(CASE WHEN historic_flag THEN 0 ELSE 1 END) FROM t GROUP BY 1 ORDER BY 1").fetchall()}
    obs["uprn_osg_empty_rows_per_created_year"] = _pairs(con, "SELECT EXTRACT(year FROM created_at_parsed)::INT, COUNT(*) FROM t WHERE uprn_osg IS NULL GROUP BY 1 ORDER BY 1")
    obs["rrn_empty_rows_per_created_year"] = _pairs(con, "SELECT EXTRACT(year FROM created_at_parsed)::INT, COUNT(*) FROM t WHERE rrn IS NULL GROUP BY 1 ORDER BY 1")
    obs["created_at_range"] = [str(v) for v in con.execute("SELECT MIN(created_at_parsed), MAX(created_at_parsed) FROM t").fetchone()]

    # Identity.
    obs["uprn_osg_empty_rows"] = _one(con, "SELECT COUNT(*) FROM t WHERE uprn_osg IS NULL")
    obs["uprn_osg_distinct"] = _one(con, "SELECT COUNT(DISTINCT uprn_osg) FROM t")
    obs["uprn_sepcr_distinct"] = _one(con, "SELECT COUNT(DISTINCT uprn_sepcr) FROM t")
    obs["uprn_osg_digits"] = _pairs(con, "SELECT LENGTH(CAST(uprn_osg AS VARCHAR)), COUNT(DISTINCT uprn_osg) FROM t WHERE uprn_osg IS NOT NULL GROUP BY 1 ORDER BY 1")
    obs["uprn_sepcr_with_and_without_uprn_osg"] = mixed
    obs["uprn_osg_with_two_or_more_current"] = _one(con, "SELECT COUNT(*) FROM (SELECT uprn_osg FROM t WHERE uprn_osg IS NOT NULL AND NOT historic_flag GROUP BY 1 HAVING COUNT(*) > 1)")
    obs["uprn_osg_with_one_current"] = _one(con, "SELECT COUNT(*) FROM (SELECT uprn_osg FROM t WHERE uprn_osg IS NOT NULL AND NOT historic_flag GROUP BY 1 HAVING COUNT(*) = 1)")
    obs["uprn_osg_all_historic"] = _one(con, "SELECT COUNT(*) FROM (SELECT uprn_osg FROM t WHERE uprn_osg IS NOT NULL GROUP BY 1 HAVING SUM(CASE WHEN historic_flag THEN 0 ELSE 1 END) = 0)")
    obs["uprn_sepcr_with_two_or_more_current"] = _one(con, "SELECT COUNT(*) FROM (SELECT uprn_sepcr FROM t WHERE NOT historic_flag GROUP BY 1 HAVING COUNT(*) > 1)")
    obs["uprn_sepcr_all_historic"] = _one(con, "SELECT COUNT(*) FROM (SELECT uprn_sepcr FROM t GROUP BY 1 HAVING SUM(CASE WHEN historic_flag THEN 0 ELSE 1 END) = 0)")
    obs["uprn_sepcr_with_two_or_more_pc_norm"] = _one(con, "SELECT COUNT(*) FROM (SELECT uprn_sepcr FROM t WHERE pc_norm IS NOT NULL GROUP BY 1 HAVING COUNT(DISTINCT pc_norm) > 1)")
    obs["same_uprn_sepcr_same_inspection_day_pairs"] = _one(con, "SELECT COUNT(*) FROM (SELECT uprn_sepcr, inspection_date_parsed FROM t GROUP BY 1, 2 HAVING COUNT(*) > 1)")
    obs["same_uprn_osg_same_inspection_day_pairs"] = _one(con, "SELECT COUNT(*) FROM (SELECT uprn_osg, inspection_date_parsed FROM t WHERE uprn_osg IS NOT NULL GROUP BY 1, 2 HAVING COUNT(*) > 1)")
    obs["rrn_empty_rows"] = _one(con, "SELECT COUNT(*) FROM t WHERE rrn IS NULL")

    # Geography.
    for status_col in ("datazone_2001_status", "datazone_2011_status"):
        obs[status_col] = _pairs(con, f"SELECT {status_col}, COUNT(*) FROM t GROUP BY 1 ORDER BY 1")
    obs["datazone_2001_distinct"] = _one(con, "SELECT COUNT(DISTINCT datazone_2001) FROM t")
    obs["datazone_2011_distinct"] = _one(con, "SELECT COUNT(DISTINCT datazone_2011) FROM t")
    obs["geography_columns_all_empty_rows"] = _one(con, "SELECT COUNT(*) FROM t WHERE LOCAL_AUTHORITY = '' AND DATA_ZONE = '' AND CONSTITUENCY = ''")
    obs["local_authority_not_scottish_rows"] = _one(con, "SELECT COUNT(*) FROM t WHERE LOCAL_AUTHORITY <> '' AND NOT (LOCAL_AUTHORITY LIKE '00Q%' OR LOCAL_AUTHORITY LIKE '00R%')")
    obs["postcode_empty_rows"] = _one(con, "SELECT COUNT(*) FROM t WHERE pc_norm IS NULL")
    obs["pc_norm_distinct"] = _one(con, "SELECT COUNT(DISTINCT pc_norm) FROM t")
    obs["pc_norm_not_5_to_7_chars"] = _one(con, "SELECT COUNT(*) FROM t WHERE pc_norm IS NOT NULL AND LENGTH(pc_norm) NOT BETWEEN 5 AND 7")
    obs["pc_norm_with_other_than_letters_and_digits"] = _one(con, "SELECT COUNT(*) FROM t WHERE pc_norm IS NOT NULL AND NOT regexp_full_match(pc_norm, '[A-Z0-9]+')")
    areas = ", ".join(f"'{a}'" for a in SCOTTISH_POSTCODE_AREAS)
    obs["postcode_area_not_scottish_rows"] = _one(con, f"SELECT COUNT(*) FROM t WHERE pc_norm IS NOT NULL AND regexp_extract(pc_norm, '^[A-Z]*') NOT IN ({areas})")
    obs["postcode_with_tab_rows"] = _one(con, "SELECT COUNT(*) FROM t WHERE POSTCODE LIKE '%' || chr(9) || '%'")

    # Characters the load must carry unchanged.
    published = [f["name"] for f in schema["fields"] if f.get("group") == "published"]
    obs["cells_with_tab"] = {c: n for c, n in ((c, _one(con, f'SELECT COUNT(*) FROM t WHERE "{c}" LIKE \'%\' || chr(9) || \'%\'')) for c in published) if n}
    obs["cells_with_embedded_newline"] = {c: n for c, n in ((c, _one(con, f'SELECT COUNT(*) FROM t WHERE "{c}" LIKE \'%\' || chr(10) || \'%\'')) for c in published) if n}
    obs["cells_with_replacement_character"] = {c: n for c, n in ((c, _one(con, f'SELECT COUNT(*) FROM t WHERE "{c}" LIKE \'%\' || chr(65533) || \'%\'')) for c in published) if n}
    obs["cells_with_trailing_space"] = {c: n for c, n in ((c, _one(con, f'SELECT COUNT(*) FROM t WHERE "{c}" LIKE \'% \'')) for c in published) if n}
    # Lengths in UTF-16 code units, the unit of a column's width and of SQL Server's DATALENGTH / 2.
    obs["longest_text_per_column"] = {f["name"]: _one(con, f'SELECT MAX({_sql_length(f["name"])}) FROM t') for f in schema["fields"] if f["type"] == "string"}
    obs["cells_over_sql_bounded_width"] = {c: n for c, n in ((c, _one(con, f'SELECT COUNT(*) FROM t WHERE {_sql_length(c)} > {col.SQL_BOUNDED_MAX}')) for c in published) if n}
    obs["cells_with_supplementary_character"] = {c: n for c, n in ((c, _one(con, f'SELECT COUNT(*) FROM t WHERE {_sql_length(c)} > LENGTH("{c}")')) for c in published) if n}

    # The publisher's missing value and the numbers.
    obs["data_removed_cells"] = {c: n for c, n in ((c, _one(con, f'SELECT COUNT(*) FROM t WHERE "{c}" = \'{col.DATA_REMOVED}\'')) for c in published) if n}
    obs["potential_rating_null_rows"] = _one(con, "SELECT COUNT(*) FROM t WHERE potential_energy_performance_rating_num IS NULL")
    obs["floor_area_range"] = list(con.execute("SELECT MIN(floor_area_int), MAX(floor_area_int) FROM t").fetchone())
    obs["floor_area_under_15_rows"] = _one(con, "SELECT COUNT(*) FROM t WHERE floor_area_int < 15")
    obs["floor_area_over_1500_rows"] = _one(con, "SELECT COUNT(*) FROM t WHERE floor_area_int > 1500")
    obs["current_rating_range"] = list(con.execute("SELECT MIN(current_energy_performance_rating_int), MAX(current_energy_performance_rating_int) FROM t").fetchone())
    obs["current_rating_negative_rows"] = _one(con, "SELECT COUNT(*) FROM t WHERE current_energy_performance_rating_int < 0")
    obs["building_emissions_range"] = [str(v) for v in con.execute("SELECT MIN(building_emissions_num), MAX(building_emissions_num) FROM t").fetchone()]
    obs["primary_energy_value_range"] = list(con.execute("SELECT MIN(primary_energy_value_int), MAX(primary_energy_value_int) FROM t").fetchone())
    obs["rating_differs_from_rounded_emissions_rows"] = _one(con, "SELECT COUNT(*) FROM t WHERE current_energy_performance_rating_int <> CAST(round(building_emissions_num, 0) AS BIGINT)")
    cut = "CASE WHEN current_energy_performance_rating_int < 0 THEN 'Carbon Neu' " + \
          " ".join(f"WHEN current_energy_performance_rating_int <= {hi} THEN '{band}'" for hi, band in BAND_UPPER) + " ELSE 'G' END"
    obs["band_differs_from_cut_of_rating_rows"] = _one(con, f"SELECT COUNT(*) FROM t WHERE CURRENT_ENERGY_PERFORMANCE_BAND <> {cut}")
    obs["current_band_values"] = _pairs(con, "SELECT CURRENT_ENERGY_PERFORMANCE_BAND, COUNT(*) FROM t GROUP BY 1 ORDER BY 1")
    obs["property_type_short_values"] = _pairs(con, "SELECT PROPERTY_TYPE_SHORT, COUNT(*) FROM t GROUP BY 1 ORDER BY 2 DESC, 1")
    obs["meets_2002_standard_empty_rows"] = _one(con, "SELECT COUNT(*) FROM t WHERE MEETS_2002_STANDARD = ''")

    # Dates.
    obs["lodgement_before_inspection_rows"] = _one(con, "SELECT COUNT(*) FROM t WHERE lodgement_date_parsed < inspection_date_parsed")
    obs["inspection_after_extraction_rows"] = _one(con, f"SELECT COUNT(*) FROM t WHERE inspection_date_parsed > DATE '{extracted}'")
    obs["inspection_over_a_year_before_lodgement_rows"] = _one(con, "SELECT COUNT(*) FROM t WHERE lodgement_date_parsed - inspection_date_parsed > 365")
    obs["inspection_to_lodgement_median_days"] = _one(con, "SELECT CAST(median(lodgement_date_parsed - inspection_date_parsed) AS INT) FROM t")
    obs["created_at_day_differs_from_lodgement_date_rows"] = _one(con, "SELECT COUNT(*) FROM t WHERE CAST(created_at_parsed AS DATE) <> lodgement_date_parsed")
    obs["inspection_date_range"] = [str(v) for v in con.execute("SELECT MIN(inspection_date_parsed), MAX(inspection_date_parsed) FROM t").fetchone()]
    obs["lodgement_date_range"] = [str(v) for v in con.execute("SELECT MIN(lodgement_date_parsed), MAX(lodgement_date_parsed) FROM t").fetchone()]
    con.close()
    return obs

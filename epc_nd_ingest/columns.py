"""The table's columns: key and provenance, the 38 published columns, the derived columns.

`python -m epc_nd_ingest.columns` writes output_schema.yaml from published_columns.yaml and the
derived list below, so the schema is a reviewable file and the build reads only the file. The
tests check that the file matches what this module would write.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

PACKAGE = Path(__file__).resolve().parent
PUBLISHED = PACKAGE / "published_columns.yaml"
SCHEMA = PACKAGE / "output_schema.yaml"
SCHEMA_VERSION = "epc_nondomestic_v1"
TABLE = "epc_nondomestic"
KEY = ["epc_release", "source_row"]

# The width of a published text column is the longest value the build accepts: the smallest
# bucket strictly above the longest value measured, so a longer value in a later release fails
# the schema check, not the load. Widths and lengths are in UTF-16 code units, the unit SQL
# Server counts an nvarchar in: a character outside the Basic Multilingual Plane takes two
# (reader.sql_length). A column that is empty in every row gets the smallest bucket
# that still reads as a text column. The width is always an integer. How SQL Server stores the
# column follows from it: nvarchar(width) up to SQL_BOUNDED_MAX, nvarchar(max) above
# (sql_check.declared_type).
WIDTH_BUCKETS = (8, 32, 100, 128, 512, 1000, 4000, 8000)
SQL_BOUNDED_MAX = 4000
EMPTY_COLUMN_WIDTH = 128

# Published columns the derived columns are computed from, by rule name (reader.py).
DATE_COLUMNS = {"INSPECTION_DATE": "inspection_date_parsed", "LODGEMENT_DATE": "lodgement_date_parsed"}
DATETIME_COLUMN = ("CREATED_AT", "created_at_parsed")
INT_COLUMNS = {"FLOOR_AREA": "floor_area_int",
               "CURRENT_ENERGY_PERFORMANCE_RATING": "current_energy_performance_rating_int",
               "PRIMARY_ENERGY_VALUE": "primary_energy_value_int"}
DECIMAL_COLUMNS = {"BUILDING_EMISSIONS": "building_emissions_num"}
# The publisher's missing value. It stands in four columns and only there: a rating and its band,
# twice. A typed copy of one of them is NULL exactly where the text is this.
DATA_REMOVED = "Data removed"
DATA_REMOVED_PAIRS = {"POTENTIAL_ENERGY_PERFORMANCE_RATING": "POTENTIAL_ENERGY_PERFORMANCE_BAND",
                      "ASSET_RATING": "ASSET_RATING_BAND"}
NULLABLE_DECIMAL_COLUMNS = {"POTENTIAL_ENERGY_PERFORMANCE_RATING": "potential_energy_performance_rating_num"}
DATAZONE_COLUMNS = {"DATA_ZONE": ("datazone_2001", "datazone_2001_status", 2001),
                    "DATA_ZONE_2011": ("datazone_2011", "datazone_2011_status", 2011)}
DATAZONE_STATUSES = ("code", "empty", "not_a_datazone", "unknown_code")

KEY_FIELDS = [
    {"name": "epc_release", "type": "string", "width": 8, "nullable": False, "group": "key",
     "description": "The release of the extract this row came from, 2026Q3. A later release is a new build."},
    {"name": "source_row", "type": "int32", "nullable": False, "group": "key",
     "description": "The row's position in the pinned file: 1 for the first data row, which is file row 3 after the two header rows. The file is in no order, so the number identifies a row of this release and nothing else."},
]

DERIVED_FIELDS = [
    {"name": "rrn", "type": "string", "width": 24, "nullable": True, "source": "REPORT_REFERENCE_NUMBER",
     "description": "The report reference number as published where not empty, NULL where empty (126 rows). Unique where present."},
    {"name": "uprn_sepcr", "type": "int64", "nullable": False, "source": "BUILDING_REFERENCE_NUMBER",
     "description": "The register's own 10-digit number for the building, trimmed and as an integer. Not the Gazetteer UPRN. Present in every row."},
    {"name": "uprn_osg", "type": "int64", "nullable": True, "source": "OSG_REFERENCE_NUMBER",
     "description": "The One Scotland Gazetteer UPRN as an integer, NULL where the published cell is empty (35.4% of rows). The only column a UPRN join compares. A padded cohort UPRN matches once cast to bigint."},
    {"name": "pc_norm", "type": "string", "width": 32, "nullable": True, "source": "POSTCODE",
     "description": "POSTCODE in upper case with every space and tab removed. NULL where nothing is left. Nothing repaired. The postcode join normalises the cohort postcode by the same rule."},
    {"name": "datazone_2001", "type": "string", "width": 9, "nullable": True, "source": "DATA_ZONE",
     "description": "The 2001 data zone code when DATA_ZONE starts with S01 and six digits followed by a space or the end, otherwise NULL."},
    {"name": "datazone_2001_status", "type": "string", "width": 16, "nullable": False, "source": "DATA_ZONE",
     "description": "code, empty, not_a_datazone (for 00QQMB and the like) or unknown_code (well formed, not in the pinned list. The build fails if any)."},
    {"name": "datazone_2011", "type": "string", "width": 9, "nullable": True, "source": "DATA_ZONE_2011",
     "description": "The 2011 data zone code by the same rule, otherwise NULL."},
    {"name": "datazone_2011_status", "type": "string", "width": 16, "nullable": False, "source": "DATA_ZONE_2011",
     "description": "As datazone_2001_status, for the 2011 column."},
    {"name": "inspection_date_parsed", "type": "date", "nullable": False, "source": "INSPECTION_DATE",
     "description": "INSPECTION_DATE (yyyy-mm-dd) as a date: the day the assessor saw the building. The dated joins choose the certificate by it. Outliers (2002 to 2108) are kept as published. A value that does not parse stops the build."},
    {"name": "lodgement_date_parsed", "type": "date", "nullable": False, "source": "LODGEMENT_DATE",
     "description": "LODGEMENT_DATE (yyyy-mm-dd) as a date. The administrative date of the certificate, a median of 8 days after the inspection. The ten-year validity runs from it."},
    {"name": "created_at_parsed", "type": "datetime", "nullable": False, "source": "CREATED_AT",
     "description": "CREATED_AT (dd/mm/yyyy hh:mm:ss) as a timestamp to the second: when the certificate was lodged on the register. Never later than the last day of the release quarter."},
    {"name": "historic_flag", "type": "bool", "nullable": False, "source": "HISTORIC",
     "description": "1 where HISTORIC is True (the certificate has been superseded), 0 where False. Any other value stops the build."},
    {"name": "floor_area_int", "type": "int32", "nullable": False, "source": "FLOOR_AREA",
     "description": "The conditioned floor area of the building in square metres as an integer, 4 to 138,037 in this release. Shared with dwellings in unit, not in what is measured."},
    {"name": "current_energy_performance_rating_int", "type": "int32", "nullable": False, "source": "CURRENT_ENERGY_PERFORMANCE_RATING",
     "description": "The current energy performance rating as an integer: calculated emissions in kg of CO2 per square metre per year, lower is better, negative allowed. Not the domestic rating, which scores energy cost and where higher is better."},
    {"name": "potential_energy_performance_rating_num", "type": "decimal", "nullable": True, "source": "POTENTIAL_ENERGY_PERFORMANCE_RATING",
     "description": "The potential energy performance rating (kg of CO2 per square metre per year after the listed improvements) as decimal(19,4). NULL exactly where the published text is 'Data removed' (1,712 rows)."},
    {"name": "building_emissions_num", "type": "decimal", "nullable": False, "source": "BUILDING_EMISSIONS",
     "description": "The Building Emission Rate (kg of CO2 per square metre per year) as decimal(19,4). The same quantity as the domestic emissions per floor area."},
    {"name": "primary_energy_value_int", "type": "int32", "nullable": False, "source": "PRIMARY_ENERGY_VALUE",
     "description": "The primary energy indicator (kWh per square metre per year) as an integer. The same quantity as the domestic primary energy indicator."},
]


def load_published(path: Path = PUBLISHED) -> list:
    raw = yaml.safe_load(Path(path).read_text())
    if raw.get("version") != 1:
        raise ValueError("Unsupported published-columns version")
    columns = raw["columns"]
    names = [c["name"] for c in columns]
    if len(set(names)) != len(names):
        raise ValueError("a published column name repeats")
    return columns


def width(max_len: int) -> int:
    if max_len == 0:
        return EMPTY_COLUMN_WIDTH
    for bucket in WIDTH_BUCKETS:
        if bucket > max_len:
            return bucket
    raise ValueError(f"a value of {max_len} characters does not fit any width bucket")


def fields(published: list) -> list:
    out = [dict(f) for f in KEY_FIELDS]
    for c in published:
        out.append({"name": c["name"], "type": "string", "width": width(c["max_len"]), "nullable": False,
                    "group": "published", "label": c["label"], "max_len": c["max_len"],
                    "description": f"As published. Publisher's label: {c['label']}."})
    for f in DERIVED_FIELDS:
        d = dict(f)
        d["group"] = "derived"
        out.append(d)
    names = [f["name"] for f in out]
    folded = {}
    for name in names:
        folded.setdefault(name.lower(), []).append(name)
    clashes = {k: v for k, v in folded.items() if len(v) > 1}
    if clashes:
        raise ValueError(f"column names that differ only by case: {clashes}")
    return out


def schema(published: list) -> dict:
    f = fields(published)
    return {"version": SCHEMA_VERSION, "table": TABLE, "key": KEY, "columns": len(f), "fields": f}


def write(published: list | None = None) -> None:
    published = published or load_published()
    text = "# Frozen output schema of epc_nondomestic. Order, type, width and nullability are the contract.\n" \
           "# Generated by python -m epc_nd_ingest.columns; do not edit by hand.\n" + \
           yaml.safe_dump(schema(published), sort_keys=False, allow_unicode=True, width=120)
    SCHEMA.write_text(text)


def main(argv=None) -> int:
    write()
    print(f"wrote {SCHEMA}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

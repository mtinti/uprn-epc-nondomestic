"""A fixture release for running the upload notebook against SQL Server through pyodbc: the
default awkward rows of every test, plus the cases a load through pyodbc can get wrong. Writes
the delivery folder (CSV, two SQL scripts, the notebook built from the fixture's manifest).

    python loader/notebook_probe/build_fixture.py <scratch folder>
"""
import shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
from synthetic import default_rows, make_release, make_row
from epc_nd_ingest import pipeline

HERE = Path(sys.argv[1]).resolve()   # a scratch folder: work/, delivery/ and fixture_manifest.json are written under it
HERE.mkdir(parents=True, exist_ok=True)
rows = default_rows() + [
    # Non-ASCII in several columns: Gaelic accents, a no-break space, curly quotes, the euro sign, an en dash, a superscript two.
    make_row(8, POST_TOWN="Càfé – Àlloa", IMPROVEMENT_RECOMMENDATIONS="EPC-L5; LOW; SHORT; ‘top-up’ €500 for 25 m² ü ",
             CONSTITUENCY_LABEL="Steòrnabhagh a Deas", ADDRESS1="UNIT 8 TEST HOUSE"),
    # Every wide column one short of the width it accepts: the row is far over 8,000 characters,
    # and the nvarchar(max) cell is 7,999 characters long.
    make_row(9, IMPROVEMENT_RECOMMENDATIONS="I" * 7999, PROPERTY_TYPE="P" * 99, ADDRESS1="A" * 99, ADDRESS2="B" * 99, POST_TOWN="T" * 99,
             DATA_ZONE="S01000416 (" + "Z" * 87 + ")", CONSTITUENCY_LABEL="W" * 99, TRANSACTION_TYPE="X" * 99, MAIN_HEATING_FUEL="F" * 99,
             BUILDING_ENVIRONMENT="E" * 99),
    # Large and negative decimals at the 4-decimal edge, a far date, a small-hours timestamp, a tiny floor area.
    make_row(10, BUILDING_EMISSIONS="123456789012345.6789", POTENTIAL_ENERGY_PERFORMANCE_RATING="-0.0001", LODGEMENT_DATE="2024-12-13",
             INSPECTION_DATE="2108-02-01", CREATED_AT="01/01/2024 00:00:00", FLOOR_AREA="4", CURRENT_ENERGY_PERFORMANCE_RATING="42155",
             CURRENT_ENERGY_PERFORMANCE_BAND="G", PRIMARY_ENERGY_VALUE="238089"),
    # One current certificate and nothing else for this UPRN.
    make_row(11, OSG_REFERENCE_NUMBER="35000099", BUILDING_REFERENCE_NUMBER="1000000099"),
    # A twelve-digit UPRN at the top of the Gazetteer range.
    make_row(12, OSG_REFERENCE_NUMBER="999999999999", BUILDING_REFERENCE_NUMBER="1000000100"),
    # One building assessed twice, the pair step 6 shows: superseded in 2019, current in 2024.
    make_row(13, OSG_REFERENCE_NUMBER="35000200", BUILDING_REFERENCE_NUMBER="1000000200", HISTORIC="True", year=2019),
    make_row(14, OSG_REFERENCE_NUMBER="35000200", BUILDING_REFERENCE_NUMBER="1000000200"),
    # A character outside the Basic Multilingual Plane takes two UTF-16 code units in SQL Server.
    # Row 15 fills nvarchar(100) exactly with 98 letters and one such character, and nvarchar(32)
    # with 30 and one. Row 16 holds one at the end of a value over 4,000 units in the max column.
    make_row(15, ADDRESS1="A" * 98 + "\U0001F3E2", PROPERTY_TYPE_SHORT="S" * 30 + "\U0001F3E2", POST_TOWN="\U0001F3E2 ALLOA \U00010000"),
    make_row(16, IMPROVEMENT_RECOMMENDATIONS="EPC-H1; HIGH; LONG; " + "y" * 4430 + "\U0001F3E2"),
]
work = HERE / "work"
shutil.rmtree(work, ignore_errors=True); work.mkdir()
registry = make_release(work, rows=rows)
manifest = pipeline.build(results=work / "results", registry_path=registry, source_root=work / "sources", log=lambda *a: None)
assert manifest["summary"]["blocking_failed"] == 0, manifest["summary"]
print("fixture rows", manifest["csv"]["rows"], "digest", manifest["csv"]["digest"]["total"])
delivery = HERE / "delivery"
shutil.rmtree(delivery, ignore_errors=True); delivery.mkdir()
shutil.copy(work / "results" / "epc_nondomestic.csv.gz", delivery)
shutil.copy(work / "results" / "manifest.json", HERE / "fixture_manifest.json")
for name in ("import_csv.sql", "check_loaded_digest.sql"):
    shutil.copy(ROOT / "docs" / "sql" / name, delivery)
subprocess.run([sys.executable, str(ROOT / "loader" / "make_notebook.py"), str(work / "results"), str(delivery / "upload_epc_nondomestic.ipynb")], check=True)

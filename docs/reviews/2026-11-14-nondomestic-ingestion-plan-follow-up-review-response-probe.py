# Probe for the response to docs/reviews/2026-11-14-nondomestic-ingestion-plan-follow-up-review.md.
# It runs the three join queries of uprn-epc (commit d3d1ea4) in DuckDB, through the substitutions
# of uprn-epc's own tests, against an empty table, and prints the columns each returns. It also
# checks that no query reads the clock. It reads no data and writes nothing.
#
#   python3 -I <this file> <uprn-epc checkout>
import sys, re
from pathlib import Path
EPC = Path(sys.argv[1]); sys.path.insert(0, str(EPC))
import duckdb
from tests.test_joins import duck, SQL

con = duckdb.connect()
con.execute("CREATE TABLE epc_domestic (epc_release VARCHAR, source_year SMALLINT, source_row INTEGER, uprn_sepcr BIGINT, uprn_osg BIGINT, "
            "pc_norm VARCHAR, inspection_date_parsed DATE, lodgement_date_parsed DATE, created_at_parsed TIMESTAMP, historic_flag BOOLEAN, rrn VARCHAR, "
            "CURRENT_ENERGY_RATING VARCHAR, current_energy_efficiency_int INTEGER, POTENTIAL_ENERGY_RATING VARCHAR, total_floor_area_int INTEGER, "
            "PROPERTY_TYPE VARCHAR, BUILT_FORM VARCHAR, CONSTRUCTION_AGE_BAND VARCHAR, TENURE VARCHAR, MAIN_FUEL VARCHAR)")
cohorts = {"join_by_uprn.sql": "cohort_row_id INTEGER, pseudo_id INTEGER, uprn VARCHAR, cohort_date DATE",
           "join_latest_by_uprn.sql": "cohort_row_id INTEGER, pseudo_id INTEGER, uprn VARCHAR",
           "join_by_postcode.sql": "cohort_row_id INTEGER, pseudo_id INTEGER, postcode VARCHAR, cohort_date DATE"}
out = {}
for name, cols in cohorts.items():
    text = (SQL / name).read_text()
    con.execute(f"CREATE OR REPLACE TABLE cohort ({cols})")
    out[name] = [d[0] for d in con.execute(duck(text)).description]
    clock = re.findall(r"GETDATE|SYSDATETIME|CURRENT_TIMESTAMP|GETUTCDATE", text, re.I)
    print(f"{name}: {len(out[name])} columns, reads the clock: {bool(clock)}")
    print("  ", ", ".join(out[name]))
    assert not clock
dated, undated = set(out["join_by_uprn.sql"]), set(out["join_latest_by_uprn.sql"])
missing = ["cohort_date", "epc_inspection_date", "epc_age_days", "epc_lodged_before_inspection", "historic_flag", "epc_tie_candidates", "epc_tie_rule"]
print("columns of the dated query that the undated query does not return:", sorted(dated - undated))
assert all(c in dated and c not in undated for c in missing)
print("all assertions passed")

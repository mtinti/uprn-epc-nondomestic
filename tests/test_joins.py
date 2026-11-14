"""The example join queries, run in DuckDB against a table created from the generated schema,
with the cases the plan names.

The queries are T-SQL for SQL Server. DuckDB runs them after six textual substitutions that
change spelling and nothing else: TRY_CONVERT(bigint, x) to TRY_CAST(x AS BIGINT), DATEDIFF(day,
a, b) to datediff('day', a, b), N'...' to '...', NCHAR(9) to chr(9), #cohort to cohort, and the
two IF EXISTS ... THROW guards removed (their presence is asserted; the container probe exercises
them in T-SQL). The container probe (loader/sqlserver_probe.sh) runs the T-SQL itself against SQL
Server with the same output contract."""

import datetime as dt
import re
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest
import yaml

from epc_nd_ingest import columns as col
from epc_nd_ingest import pipeline
from epc_nd_ingest.reader import norm_postcode

from synthetic import make_release

ROOT = Path(__file__).resolve().parent.parent
SQL = ROOT / "docs" / "sql"
PARQUET = ROOT / "results" / "epc_nondomestic.parquet"
GUARD = re.compile(r"IF EXISTS \(SELECT 1 FROM #cohort WHERE cohort_row_id IS NULL\)\n\s*THROW 51000, '[^']*', 1;\n"
                   r"IF EXISTS \(SELECT 1 FROM #cohort GROUP BY cohort_row_id HAVING COUNT\(\*\) > 1\)\n\s*THROW 51000, '[^']*', 1;\n")
QUERIES = ("join_by_uprn.sql", "join_latest_by_uprn.sql", "join_by_postcode.sql")
DUCK_TYPE = {"string": "VARCHAR", "int16": "SMALLINT", "int32": "INTEGER", "int64": "BIGINT", "decimal": "DECIMAL(19,4)",
             "date": "DATE", "datetime": "TIMESTAMP", "bool": "BOOLEAN"}

# The output contract of docs/EPC_NonDomestic_Plan.md, section 7: each query's columns, in order.
DATES = ["epc_inspection_date", "epc_lodgement_date", "epc_lodged_before_inspection"]
MEASUREMENTS = ["CURRENT_ENERGY_PERFORMANCE_BAND", "current_energy_performance_rating_int", "POTENTIAL_ENERGY_PERFORMANCE_BAND",
                "potential_energy_performance_rating_num", "PROPERTY_TYPE_SHORT", "PROPERTY_TYPE", "MAIN_HEATING_FUEL"]
SHARED = ["floor_area_int", "building_emissions_num", "primary_energy_value_int"]
TIES = ["epc_tie_candidates", "epc_tie_rule"]
CONTRACT = {
    "join_by_uprn.sql": ["cohort_row_id", "pseudo_id", "epc_status", "cohort_date"] + DATES + ["epc_age_days"] + MEASUREMENTS + SHARED + ["historic_flag", "rrn"] + TIES,
    "join_latest_by_uprn.sql": ["cohort_row_id", "pseudo_id", "epc_status"] + DATES + MEASUREMENTS + SHARED + ["rrn"],
    "join_by_postcode.sql": ["cohort_row_id", "pseudo_id", "epc_status", "cohort_date", "building", "building_status", "uprn_osg"] + DATES
                            + ["epc_age_days"] + MEASUREMENTS + SHARED + ["historic_flag", "rrn"] + TIES,
}
# The columns that describe the chosen certificate: NULL unless the row is matched.
CERTIFICATE = DATES + ["epc_age_days"] + MEASUREMENTS + SHARED + ["historic_flag", "rrn"]
COHORT = {"join_by_uprn.sql": "CREATE TABLE cohort (cohort_row_id INTEGER, pseudo_id INTEGER, uprn VARCHAR, cohort_date DATE)",
          "join_latest_by_uprn.sql": "CREATE TABLE cohort (cohort_row_id INTEGER, pseudo_id INTEGER, uprn VARCHAR)",
          "join_by_postcode.sql": "CREATE TABLE cohort (cohort_row_id INTEGER, pseudo_id INTEGER, postcode VARCHAR, cohort_date DATE)"}


def duck(sql: str) -> str:
    assert GUARD.search(sql), "the query must stop on a NULL or repeated cohort_row_id"
    sql = GUARD.sub("", sql)
    sql = re.sub(r"TRY_CONVERT\(bigint, (.*?)\) AS uprn_int", r"TRY_CAST(\1 AS BIGINT) AS uprn_int", sql)
    sql = sql.replace("DATEDIFF(day, ", "datediff('day', ")
    sql = sql.replace("NCHAR(9)", "chr(9)")
    sql = re.sub(r"\bN'", "'", sql)
    sql = sql.replace("#cohort", "cohort")
    return sql


def schema_fields() -> list:
    return yaml.safe_load(col.SCHEMA.read_text())["fields"]


def create_table(con) -> list:
    """epc_nondomestic exactly as the generated schema declares it: names, order, types, nullability."""
    fields = schema_fields()
    con.execute("CREATE TABLE epc_nondomestic (" + ", ".join(
        f'"{f["name"]}" {DUCK_TYPE[f["type"]]}' + ("" if f["nullable"] else " NOT NULL") for f in fields) + ")")
    return [f["name"] for f in fields]


def cert(row, uprn_sepcr, uprn_osg, postcode, inspected, historic, band="D", lodged=None, created=None, kind="Office/Workshop") -> dict:
    """A certificate. It is lodged on the inspection day unless `lodged` says otherwise, and the
    register timestamp is 09:00 on the lodgement day unless `created` says otherwise. pc_norm is
    made from the postcode by the build's own rule."""
    lodged = lodged or inspected
    values = {f["name"]: ("" if f["type"] == "string" and not f["nullable"] else None) for f in schema_fields()}
    values.update({
        "epc_release": "TEST", "source_row": row, "HISTORIC": str(historic), "BUILDING_REFERENCE_NUMBER": str(uprn_sepcr),
        "OSG_REFERENCE_NUMBER": "" if uprn_osg is None else str(uprn_osg), "POSTCODE": postcode, "INSPECTION_DATE": inspected,
        "LODGEMENT_DATE": lodged, "PROPERTY_TYPE_SHORT": kind, "PROPERTY_TYPE": kind + " (full)", "MAIN_HEATING_FUEL": "Natural Gas",
        "CURRENT_ENERGY_PERFORMANCE_BAND": band, "POTENTIAL_ENERGY_PERFORMANCE_BAND": "C",
        "rrn": f"0000-0000-0000-0000-{row:04d}", "uprn_sepcr": uprn_sepcr, "uprn_osg": uprn_osg, "pc_norm": norm_postcode(postcode),
        "datazone_2001_status": "empty", "datazone_2011_status": "empty",
        "inspection_date_parsed": dt.date.fromisoformat(inspected), "lodgement_date_parsed": dt.date.fromisoformat(lodged),
        "created_at_parsed": dt.datetime.fromisoformat(created or (lodged + " 09:00:00")), "historic_flag": historic,
        "floor_area_int": 250, "current_energy_performance_rating_int": 55, "potential_energy_performance_rating_num": Decimal("40.0000"),
        "building_emissions_num": Decimal("55.2100"), "primary_energy_value_int": 380,
    })
    return values


ROWS = [
    # UPRN 35000001: three certificates, 2010, 2015, 2020; only the last current. The 2020 one was
    # inspected twelve days before it was lodged.
    cert(1, 1000000001, 35000001, "FK10 1AA", "2010-06-01", True, "E"),
    cert(2, 1000000001, 35000001, "FK10 1AA", "2015-06-01", True, "D"),
    cert(3, 1000000001, 35000001, "FK10 1AA", "2020-05-20", False, "C", lodged="2020-06-01"),
    # UPRN 35000002: two certificates on the same day in 2012 that nothing separates, then one in 2018.
    cert(4, 1000000002, 35000002, "FK10 1AA", "2012-03-03", True, "F"),
    cert(5, 1000000002, 35000002, "FK10 1AA", "2012-03-03", True, "E"),
    cert(6, 1000000002, 35000002, "FK10 1AA", "2018-01-01", False, "D"),
    # UPRN 35000003: two current certificates on different days.
    cert(7, 1000000003, 35000003, "FK10 1AB", "2019-01-01", False, "B"),
    cert(8, 1000000003, 35000003, "FK10 1AB", "2019-02-01", False, "B+"),
    # UPRN 35000004: no current certificate; lodged before its inspection date, a publisher typo.
    cert(9, 1000000004, 35000004, "FK10 1AB", "2011-01-05", True, "G", lodged="2011-01-01"),
    # A building with no Gazetteer UPRN, in FK10 1AB.
    cert(10, 1000000005, None, "FK10 1AB", "2016-05-05", False, "D", kind="Hospitals/Care Home"),
    # UPRN 35000006: one assessment lodged twice on the same day, one current.
    cert(11, 1000000006, 35000006, "FK10 1AC", "2021-04-01", True, "E", created="2021-04-01 10:00:00"),
    cert(12, 1000000006, 35000006, "FK10 1AC", "2021-04-01", False, "C", created="2021-04-01 09:00:00"),
    # UPRN 35000007: a same-day pair, both superseded by a later certificate; the register timestamps differ.
    cert(13, 1000000007, 35000007, "FK10 1AC", "2014-02-02", True, "F", created="2014-02-02 09:00:00"),
    cert(14, 1000000007, 35000007, "FK10 1AC", "2014-02-02", True, "D+", created="2014-02-02 16:30:00"),
    cert(15, 1000000007, 35000007, "FK10 1AC", "2022-02-02", False, "B"),
    # UPRN 35000008: the current certificate is not the one inspected last.
    cert(16, 1000000008, 35000008, "FK10 1AD", "2019-01-01", False, "C+"),
    cert(17, 1000000008, 35000008, "FK10 1AD", "2021-01-01", True, "E+"),
    # UPRN 35000009: the building's postcode changed between certificates, FK10 1ZA then FK10 1ZB.
    cert(18, 1000000009, 35000009, "FK10 1ZA", "2020-01-01", True, "E"),
    cert(19, 1000000009, 35000009, "FK10 1ZB", "2025-01-01", False, "B"),
    # A building without a UPRN: one assessment lodged twice on the same day, one current.
    cert(20, 1000000010, None, "FK10 1ZC", "2023-03-03", True, "F", created="2023-03-03 11:00:00"),
    cert(21, 1000000010, None, "FK10 1ZC", "2023-03-03", False, "D", created="2023-03-03 10:00:00"),
    # UPRN 35000011: two certificates nothing separates, inspected on one day at two postcodes.
    cert(22, 1000000011, 35000011, "FK10 1ZD", "2022-07-07", True, "E"),
    cert(23, 1000000011, 35000011, "FK10 1ZE", "2022-07-07", True, "D"),
]


@pytest.fixture
def con():
    c = duckdb.connect()
    names = create_table(c)
    c.executemany("INSERT INTO epc_nondomestic VALUES (" + ",".join("?" * len(names)) + ")", [[r[n] for n in names] for r in ROWS])
    return c


def run(con, name, cohort_rows) -> list:
    """The query's rows as dicts keyed by output column, after checking the output contract."""
    con.execute("DROP TABLE IF EXISTS cohort")
    con.execute(COHORT[name])
    con.executemany(f"INSERT INTO cohort VALUES ({','.join('?' * len(cohort_rows[0]))})", cohort_rows)
    result = con.execute(duck((SQL / name).read_text()))
    columns = [d[0] for d in result.description]
    assert columns == CONTRACT[name], name
    return [dict(zip(columns, r)) for r in result.fetchall()]


def d(text):
    return dt.date.fromisoformat(text)


def test_each_query_returns_exactly_its_columns_in_order(con):
    counts = {}
    for name, first in (("join_by_uprn.sql", (1, 1, "35000001", d("2024-01-01"))), ("join_latest_by_uprn.sql", (1, 1, "35000001")),
                        ("join_by_postcode.sql", (1, 1, "FK10 1AA", d("2024-01-01")))):
        rows = run(con, name, [first])     # run() compares the column names with the contract
        counts[name] = len(rows[0])
    assert counts == {"join_by_uprn.sql": 22, "join_latest_by_uprn.sql": 17, "join_by_postcode.sql": 25}
    undated = set(CONTRACT["join_latest_by_uprn.sql"])
    assert not undated & {"cohort_date", "epc_age_days", "historic_flag", "epc_tie_candidates", "epc_tie_rule"}
    # No non-domestic value takes a domestic name, and no query joins through a year.
    for name in QUERIES:
        text = (SQL / name).read_text()
        for domestic in ("CURRENT_ENERGY_RATING", "current_energy_efficiency_int", "total_floor_area_int", "BUILT_FORM", "TENURE", "source_year", "epc_domestic"):
            assert domestic not in text, (name, domestic)


def test_no_query_reads_the_clock():
    for name in QUERIES:
        text = (SQL / name).read_text()
        assert not re.search(r"GETDATE|SYSDATETIME|CURRENT_TIMESTAMP|GETUTCDATE|SYSUTCDATETIME|CURRENT_DATE", text, re.I), name


def test_join_by_uprn_statuses_and_dates(con):
    rows = run(con, "join_by_uprn.sql", [
        (1, 101, "35000001", d("2009-01-01")),       # before the first certificate
        (2, 102, "35000001", d("2015-06-01")),       # on the day of the second
        (3, 103, "35000001", d("2024-01-01")),       # after the third
        (4, 104, "000035000001", d("2024-01-01")),   # padded: the same building
        (5, 105, " 35000002 ", d("2012-06-01")),     # two on the latest eligible day
        (6, 106, "35000002", d("2019-01-01")),       # a later single certificate is eligible
        (7, 107, "99999999", d("2024-01-01")),       # no certificate ever
        (8, 108, "", d("2024-01-01")),
        (9, 109, None, d("2024-01-01")),
        (10, 110, "ABC", d("2024-01-01")),
        (11, 111, "35000003", d("2024-01-01")),      # two current, different days: the later wins
        (12, 112, "35000001", d("2020-05-25")),      # inspected before the date, lodged after it: the 2020 certificate
        (13, 113, "35000006", d("2024-01-01")),      # same-day pair, one current: the current one, band C not E
        (14, 114, "35000007", d("2015-01-01")),      # same-day pair, both superseded: the later register timestamp, D+ not F
        (15, 115, "35000007", d("2024-01-01")),      # the later single certificate; no tie
        (16, 116, "35000008", d("2024-01-01")),      # the current certificate is not the one inspected last
        (17, 117, "35000004", d("2024-01-01")),      # no current certificate: the dated join still answers
    ])
    assert len(rows) == 17 and [r["pseudo_id"] for r in rows] == list(range(101, 118))
    by_id = {r["cohort_row_id"]: r for r in rows}
    assert {k: v["epc_status"] for k, v in by_id.items()} == {
        1: "no_certificate_by_date", 2: "matched", 3: "matched", 4: "matched", 5: "ambiguous_as_of", 6: "matched", 7: "uprn_not_in_epc",
        8: "no_uprn", 9: "no_uprn", 10: "no_uprn", 11: "matched", 12: "matched", 13: "matched", 14: "matched", 15: "matched", 16: "matched", 17: "matched"}
    tie = {k: (v["epc_tie_candidates"], v["epc_tie_rule"]) for k, v in by_id.items()}
    assert tie[5] == (2, "unresolved")            # both superseded, identical register timestamps
    assert tie[13] == (2, "current") and by_id[13]["CURRENT_ENERGY_PERFORMANCE_BAND"] == "C"
    assert tie[14] == (2, "latest_lodged") and by_id[14]["CURRENT_ENERGY_PERFORMANCE_BAND"] == "D+"
    assert tie[15] == (1, None) and by_id[15]["CURRENT_ENERGY_PERFORMANCE_BAND"] == "B"
    assert all(tie[k] == (1, None) for k in (2, 3, 4, 6, 11, 12, 16, 17)) and all(tie[k] == (None, None) for k in (1, 7, 8, 9, 10))
    assert by_id[2]["epc_inspection_date"] == d("2015-06-01") and by_id[2]["epc_age_days"] == 0 and by_id[2]["CURRENT_ENERGY_PERFORMANCE_BAND"] == "D"
    assert by_id[3]["epc_inspection_date"] == d("2020-05-20") and by_id[3]["epc_lodgement_date"] == d("2020-06-01")
    assert by_id[3]["CURRENT_ENERGY_PERFORMANCE_BAND"] == "C" and by_id[4]["CURRENT_ENERGY_PERFORMANCE_BAND"] == "C"
    assert by_id[6]["epc_inspection_date"] == d("2018-01-01") and by_id[6]["epc_age_days"] == 365
    assert by_id[11]["epc_inspection_date"] == d("2019-02-01")
    assert by_id[12]["epc_inspection_date"] == d("2020-05-20") and by_id[12]["epc_age_days"] == 5    # by lodgement it would have been the 2015 certificate
    # The current certificate was inspected in 2019, a superseded one in 2021: the dated join takes the latest inspection.
    assert by_id[16]["epc_inspection_date"] == d("2021-01-01") and by_id[16]["historic_flag"] is True and by_id[16]["CURRENT_ENERGY_PERFORMANCE_BAND"] == "E+"
    # Lodged before its inspection: dated by the inspection, flagged.
    assert by_id[17]["epc_inspection_date"] == d("2011-01-05") and by_id[17]["epc_lodgement_date"] == d("2011-01-01") and by_id[17]["epc_lodged_before_inspection"] == 1
    assert all(by_id[k]["epc_lodged_before_inspection"] == 0 for k in (2, 3, 4, 6, 11, 12))
    # The measurements and the three shared quantities arrive under their own names.
    assert by_id[3]["current_energy_performance_rating_int"] == 55 and by_id[3]["potential_energy_performance_rating_num"] == Decimal("40")
    assert (by_id[3]["floor_area_int"], by_id[3]["building_emissions_num"], by_id[3]["primary_energy_value_int"]) == (250, Decimal("55.21"), 380)
    assert by_id[3]["PROPERTY_TYPE_SHORT"] == "Office/Workshop" and by_id[3]["rrn"] == "0000-0000-0000-0000-0003"


def test_a_row_that_is_not_matched_carries_no_certificate_value(con):
    rows = run(con, "join_by_uprn.sql", [(1, 1, "35000001", d("2009-01-01")), (2, 1, " 35000002 ", d("2012-06-01")), (3, 1, "99999999", d("2024-01-01")),
                                         (4, 1, "", d("2024-01-01")), (5, 1, "35000001", d("2024-01-01"))])
    for r in rows:
        if r["epc_status"] == "matched":
            assert all(r[c] is not None for c in CERTIFICATE), r["cohort_row_id"]
            assert r["epc_age_days"] == (r["cohort_date"] - r["epc_inspection_date"]).days
        else:
            assert all(r[c] is None for c in CERTIFICATE), (r["cohort_row_id"], r["epc_status"])
    assert [r["epc_status"] for r in rows] == ["no_certificate_by_date", "ambiguous_as_of", "uprn_not_in_epc", "no_uprn", "matched"]
    rows = run(con, "join_latest_by_uprn.sql", [(1, 1, "35000004"), (2, 1, "35000003"), (3, 1, "99999999"), (4, 1, "x"), (5, 1, "35000001")])
    undated_certificate = [c for c in CERTIFICATE if c in CONTRACT["join_latest_by_uprn.sql"]]
    for r in rows:
        assert all((r[c] is not None) == (r["epc_status"] == "matched") for c in undated_certificate), r["cohort_row_id"]


def test_one_person_many_rows_each_row_gets_its_own_certificate(con):
    """A longitudinal cohort repeats a person at different dates and addresses. Each row must
    keep its own eligible set: the 2015 observation must not receive the 2020 certificate, and
    repeated rows must not read as ambiguity."""
    rows = run(con, "join_by_uprn.sql", [
        (1, 7, "35000001", d("2015-06-01")),
        (2, 7, "35000001", d("2024-01-01")),
        (3, 7, "35000001", d("2024-01-01")),    # a duplicate observation
        (4, 7, "35000004", d("2024-01-01")),    # the same person at another address
        (5, 7, "35000002", d("2012-06-01")),    # a same-day tie the rule cannot break stays ambiguous
    ])
    by_id = {r["cohort_row_id"]: r for r in rows}
    assert len(rows) == 5 and all(r["pseudo_id"] == 7 for r in rows)
    assert by_id[1]["epc_status"] == "matched" and by_id[1]["epc_inspection_date"] == d("2015-06-01")
    assert by_id[2]["epc_inspection_date"] == d("2020-05-20") and by_id[3]["epc_inspection_date"] == d("2020-05-20")
    assert by_id[4]["epc_status"] == "matched" and by_id[4]["CURRENT_ENERGY_PERFORMANCE_BAND"] == "G"
    assert by_id[5]["epc_status"] == "ambiguous_as_of"


def test_join_latest_by_uprn_statuses(con):
    rows = run(con, "join_latest_by_uprn.sql", [
        (1, 7, "35000001"), (2, 7, "35000003"), (3, 8, "35000004"), (4, 8, "99999999"), (5, 9, ""), (6, 9, "000035000002"), (7, 9, "35000008"),
    ])
    assert {r["cohort_row_id"]: r["epc_status"] for r in rows} == {
        1: "matched", 2: "ambiguous_latest", 3: "no_current_certificate", 4: "uprn_not_in_epc", 5: "no_uprn", 6: "matched", 7: "matched"}
    by_id = {r["cohort_row_id"]: r for r in rows}
    assert by_id[1]["CURRENT_ENERGY_PERFORMANCE_BAND"] == "C" and by_id[6]["CURRENT_ENERGY_PERFORMANCE_BAND"] == "D"
    # Both certificate dates are returned although the query takes no date.
    assert by_id[1]["epc_inspection_date"] == d("2020-05-20") and by_id[1]["epc_lodgement_date"] == d("2020-06-01") and by_id[1]["epc_lodged_before_inspection"] == 0
    # The current certificate, although a superseded one was inspected later.
    assert by_id[7]["epc_inspection_date"] == d("2019-01-01") and by_id[7]["CURRENT_ENERGY_PERFORMANCE_BAND"] == "C+"
    assert len(rows) == 7 and [r["pseudo_id"] for r in rows] == [7, 7, 8, 8, 9, 9, 9]


def test_join_by_postcode_one_row_per_building(con):
    rows = run(con, "join_by_postcode.sql", [
        (1, 7, "fk10 1ab", d("2024-01-01")),   # three buildings: 35000003 (two current, later wins), 35000004 (historic only), the building without a UPRN
        (2, 7, "FK10 1AA", d("2012-03-03")),   # the same person: 35000001 has 2010; 35000002 has the same-day pair
        (3, 8, "FK10 1AA", d("2009-01-01")),   # buildings exist, no certificate yet
        (4, 8, "ZZ1 1ZZ", d("2024-01-01")),
        (5, 9, "", d("2024-01-01")),
    ])
    one = {r["building"]: r for r in rows if r["cohort_row_id"] == 1}
    assert sorted(one) == [1000000003, 1000000004, 1000000005] and all(r["epc_status"] == "matched" for r in one.values())
    assert one[1000000003]["building_status"] == "matched" and one[1000000003]["epc_inspection_date"] == d("2019-02-01")
    assert one[1000000004]["CURRENT_ENERGY_PERFORMANCE_BAND"] == "G" and one[1000000004]["epc_lodged_before_inspection"] == 1
    assert one[1000000005]["uprn_osg"] is None and one[1000000005]["PROPERTY_TYPE_SHORT"] == "Hospitals/Care Home"
    two = {r["building"]: r for r in rows if r["cohort_row_id"] == 2}
    assert two[1000000001]["building_status"] == "matched" and two[1000000001]["epc_inspection_date"] == d("2010-06-01")
    assert two[1000000002]["building_status"] == "ambiguous_as_of" and (two[1000000002]["epc_tie_candidates"], two[1000000002]["epc_tie_rule"]) == (2, "unresolved")
    assert all(two[1000000002][c] is None for c in CERTIFICATE) and two[1000000002]["uprn_osg"] == 35000002
    assert (two[1000000001]["epc_tie_candidates"], two[1000000001]["epc_tie_rule"]) == (1, None)
    three = {r["building"]: r for r in run(con, "join_by_postcode.sql", [(1, 1, "FK10 1AC", d("2021-12-31"))])}
    assert three[1000000006]["CURRENT_ENERGY_PERFORMANCE_BAND"] == "C" and three[1000000006]["epc_tie_rule"] == "current"
    assert three[1000000007]["CURRENT_ENERGY_PERFORMANCE_BAND"] == "D+" and three[1000000007]["epc_tie_rule"] == "latest_lodged"
    assert [(r["epc_status"], r["building"]) for r in rows if r["cohort_row_id"] == 3] == [("no_certificate_by_date", None)]
    assert [r["epc_status"] for r in rows if r["cohort_row_id"] == 4] == ["postcode_not_in_epc"]
    assert [r["epc_status"] for r in rows if r["cohort_row_id"] == 5] == ["no_postcode"]


def test_postcode_join_follows_a_building_whose_postcode_changed(con):
    """The building was certified at FK10 1ZA in 2020 and at FK10 1ZB in 2025. Between the two it
    is at ZA. After both it is at ZB and no longer at ZA, where filtering by postcode before
    ranking would still return it with the 2020 certificate."""
    rows = run(con, "join_by_postcode.sql", [
        (1, 1, "FK10 1ZA", d("2022-06-01")), (2, 1, "FK10 1ZB", d("2022-06-01")),
        (3, 1, "FK10 1ZA", d("2026-06-01")), (4, 1, "FK10 1ZB", d("2026-06-01")),
        (5, 1, "FK10 1ZA", d("2019-01-01")),
    ])
    by_id = {r["cohort_row_id"]: r for r in rows}
    assert len(rows) == 5
    assert by_id[1]["epc_status"] == "matched" and by_id[1]["building"] == 1000000009 and by_id[1]["epc_inspection_date"] == d("2020-01-01")
    assert by_id[2]["epc_status"] == "no_certificate_by_date" and by_id[2]["building"] is None    # the ZB certificate is later than the date
    assert by_id[3]["epc_status"] == "no_building_at_postcode_by_date" and by_id[3]["building"] is None and by_id[3]["epc_inspection_date"] is None
    assert by_id[4]["epc_status"] == "matched" and by_id[4]["epc_inspection_date"] == d("2025-01-01") and by_id[4]["CURRENT_ENERGY_PERFORMANCE_BAND"] == "B"
    assert by_id[5]["epc_status"] == "no_certificate_by_date"


def test_postcode_join_ties_without_a_uprn_and_across_two_postcodes(con):
    rows = run(con, "join_by_postcode.sql", [(1, 1, "FK10 1ZC", d("2024-01-01")), (2, 1, "FK10 1ZD", d("2024-01-01")), (3, 1, "FK10 1ZE", d("2024-01-01"))])
    by_id = {r["cohort_row_id"]: r for r in rows}
    # A building without a UPRN follows the tie rule like any other: the current certificate of the pair.
    assert by_id[1]["building"] == 1000000010 and by_id[1]["uprn_osg"] is None and by_id[1]["building_status"] == "matched"
    assert by_id[1]["CURRENT_ENERGY_PERFORMANCE_BAND"] == "D" and (by_id[1]["epc_tie_candidates"], by_id[1]["epc_tie_rule"]) == (2, "current")
    # Two certificates nothing separates, at two postcodes: ambiguous at both, the building's UPRN and no certificate value.
    for k in (2, 3):
        assert by_id[k]["epc_status"] == "matched" and by_id[k]["building"] == 1000000011 and by_id[k]["building_status"] == "ambiguous_as_of"
        assert by_id[k]["uprn_osg"] == 35000011 and by_id[k]["epc_tie_rule"] == "unresolved" and all(by_id[k][c] is None for c in CERTIFICATE)


def test_cohort_postcode_is_normalised_like_pc_norm(con):
    """Spaces and tabs are removed on the cohort side as they are in pc_norm, and a cohort
    postcode of spaces and tabs only is no postcode."""
    rows = run(con, "join_by_postcode.sql", [
        (1, 1, "FK10\t1ZB", d("2026-06-01")), (2, 1, " \tfk10 1zb ", d("2026-06-01")), (3, 1, "FK101ZB", d("2026-06-01")),
        (4, 1, " \t ", d("2026-06-01")), (5, 1, None, d("2026-06-01")),
    ])
    assert [(r["epc_status"], r["building"]) for r in rows] == [("matched", 1000000009)] * 3 + [("no_postcode", None)] * 2


def test_a_tab_in_the_source_postcode_matches_with_and_without_a_tab_in_the_cohort(tmp_path):
    """Through the build: the synthetic release holds the postcode ' <tab>FK10 1AB'. Its pc_norm
    is made by the reader, and the query finds the building from a cohort postcode with a space,
    with a tab, and with neither."""
    registry = make_release(tmp_path)
    pipeline.build(results=tmp_path / "results", registry_path=registry, source_root=tmp_path / "sources", log=lambda *a: None)
    con = duckdb.connect()
    con.execute(f"CREATE TABLE epc_nondomestic AS SELECT * FROM read_parquet('{(tmp_path / 'results' / 'epc_nondomestic.parquet').as_posix()}')")
    assert con.execute("SELECT POSTCODE, pc_norm FROM epc_nondomestic WHERE source_row = 3").fetchone() == (" \tFK10 1AB", "FK101AB")
    rows = run(con, "join_by_postcode.sql", [(1, 1, "FK10 1AB", d("2026-01-01")), (2, 1, "FK10\t1AB", d("2026-01-01")), (3, 1, "\tFK101AB ", d("2026-01-01"))])
    assert [(r["epc_status"], r["building"], r["uprn_osg"]) for r in rows] == [("matched", 1000000003, None)] * 3


def test_every_join_declares_the_cohort_key_not_null():
    for name in QUERIES:
        sql = (SQL / name).read_text()
        assert "cohort_row_id int NOT NULL PRIMARY KEY" in sql, name
        assert GUARD.search(sql), name


@pytest.mark.skipif(not PARQUET.is_file(), reason="no build present")
def test_on_the_real_release_each_building_is_returned_at_one_postcode_as_of_a_date():
    """Every postcode of the release as a cohort row, as of the last day of the quarter. A
    building must come back once, at the postcode of its latest certificate by that date, and
    never at a postcode it has left. Filtering by postcode before ranking returned 262 buildings
    at a postcode their latest certificate contradicts."""
    con = duckdb.connect()
    con.execute(f"CREATE TABLE epc_nondomestic AS SELECT * FROM read_parquet('{PARQUET.as_posix()}')")
    as_of = d("2026-09-30")
    postcodes = [r[0] for r in con.execute("SELECT DISTINCT POSTCODE FROM epc_nondomestic ORDER BY 1").fetchall()]
    rows = run(con, "join_by_postcode.sql", [(i + 1, i + 1, pc, as_of) for i, pc in enumerate(postcodes)])
    returned = [(r["building"], norm_postcode(postcodes[r["cohort_row_id"] - 1])) for r in rows if r["building"] is not None]
    latest = dict(con.execute("""SELECT uprn_sepcr, pc_norm FROM (SELECT uprn_sepcr, pc_norm, ROW_NUMBER() OVER (PARTITION BY uprn_sepcr
        ORDER BY inspection_date_parsed DESC, CASE WHEN historic_flag THEN 1 ELSE 0 END, created_at_parsed DESC) AS rn
        FROM epc_nondomestic WHERE inspection_date_parsed <= ?) WHERE rn = 1""", [as_of]).fetchall())
    # Several spellings of one postcode are several cohort rows: compare the distinct pairs.
    pairs = set(returned)
    assert {b for b, _ in pairs} == set(latest), "every building with a certificate by the date is returned"
    assert all(latest[b] == pc for b, pc in pairs), "no building is returned at a postcode it has left"
    assert len(pairs) == len(latest)
    statuses = {r["epc_status"] for r in rows}
    assert statuses <= {"matched", "no_certificate_by_date", "no_building_at_postcode_by_date"} and "matched" in statuses

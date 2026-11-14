"""Run the fixture's upload_epc_nondomestic.ipynb against SQL Server in Docker through pyodbc, as
it is and under hostile conditions: the notebook's own code, cell by cell, in a Jupyter kernel.

Runs inside the image of loader/notebook_probe/Dockerfile, started by loader/notebook_probe.sh:
/data/delivery is the fixture's delivery folder (CSV, two SQL scripts, notebook), read-only;
/out receives the executed notebooks and results.json. SA_PW and SERVER come from the environment.

Scenarios: the full notebook twice; a changed byte in the CSV stopping at step 2; then five
changes to the loaded table, each failing the digest of step 5 and passing again once restored
(a changed value, a NULL made empty, a trailing space removed, a tab replaced by a space, the
last character of the nvarchar(max) cell changed); a batch SQL Server rejects, which keeps the
chunks committed before it; a decimal not in 4-decimal form and a text too long for its column,
each stopping before any insert; then the full notebook once more. After each full run every
cell of a chosen set of columns is read back through pyodbc and compared with the CSV text."""
import csv, gzip, json, os, secrets, shutil, sys, time, traceback
from pathlib import Path

import nbformat, pyodbc
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError

SA_PW = os.environ.pop("SA_PW")
SERVER = os.environ.get("SERVER", "epc_nd_mssql")
DELIVERY, RUNS, OUT = Path("/data/delivery"), Path("/tmp/runs"), Path("/out")
USER, USER_PW = "epc_nd_nbtest_user", secrets.token_urlsafe(24) + "aA1!"
DB, TABLE = "epc_nd_nbtest", "dbo.epc_nondomestic"
NOTEBOOK, CSV_NAME = "upload_epc_nondomestic.ipynb", "epc_nondomestic.csv"
FIXTURE_ROWS = 16
SCENARIOS = 13   # main() must record exactly this many, every one ok, or exit nonzero
RESULTS = []


def sa(db="master"):
    return pyodbc.connect(f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={SERVER};DATABASE={db};UID=sa;PWD={SA_PW};"
                          "Encrypt=yes;TrustServerCertificate=yes;", autocommit=True, timeout=30)


def q(sql, db=DB):
    with sa(db) as cn:
        cur = cn.cursor().execute(sql)
        return cur.fetchall() if cur.description else None


def setup():
    with sa() as cn:
        cur = cn.cursor()
        cur.execute(f"IF DB_ID(N'{DB}') IS NOT NULL BEGIN ALTER DATABASE [{DB}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{DB}]; END")
        cur.execute(f"IF SUSER_ID(N'{USER}') IS NOT NULL DROP LOGIN [{USER}]")
        cur.execute(f"CREATE LOGIN [{USER}] WITH PASSWORD = N'{USER_PW}', CHECK_POLICY = OFF")
        cur.execute(f"CREATE DATABASE [{DB}]")
    with sa(DB) as cn:
        cur = cn.cursor()
        cur.execute(f"CREATE USER [{USER}] FOR LOGIN [{USER}]")
        cur.execute(f"GRANT CREATE TABLE TO [{USER}]")
        cur.execute(f"GRANT ALTER, SELECT, INSERT, UPDATE, DELETE, REFERENCES ON SCHEMA::dbo TO [{USER}]")


def teardown():
    with sa() as cn:
        cur = cn.cursor()
        cur.execute(f"IF DB_ID(N'{DB}') IS NOT NULL BEGIN ALTER DATABASE [{DB}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE [{DB}]; END")
        cur.execute(f"IF SUSER_ID(N'{USER}') IS NOT NULL DROP LOGIN [{USER}]")


def folder(name, mutate=None):
    path = RUNS / name
    if path.exists():
        shutil.rmtree(path)
    shutil.copytree(DELIVERY, path)
    if mutate:
        mutate(path)
    return path


def step_index(nb, step):
    return next(i for i, c in enumerate(nb.cells) if c.cell_type == "code" and c.source.startswith(f"# Step {step} "))


def point_at(nb, path):
    cell = nb.cells[step_index(nb, 1)]
    src = cell.source
    # The notebook ships with an empty CONN. The probe fills it with the test login of the throwaway server.
    connection = f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={SERVER};DATABASE={DB};UID={USER};PWD={USER_PW};Encrypt=yes;TrustServerCertificate=yes;"
    for old, new in [('FOLDER   = Path(r"")', f'FOLDER   = Path(r"{path}")'), ('CONN     = ""', f'CONN     = "{connection}"')]:
        assert src.count(old) == 1, old
        src = src.replace(old, new)
    cell.source = src


def run(name, path, steps=None, edit=None, expect_fail=None, expect_error=None, expect_text=(), check=None):
    nb = nbformat.read(path / NOTEBOOK, as_version=4)
    point_at(nb, path)
    if edit:
        edit(nb)
    chosen = [i for i, c in enumerate(nb.cells) if c.cell_type == "code"]
    if steps is not None:
        chosen = [step_index(nb, s) for s in steps]
    started, failed, error = time.time(), None, None
    # A cell that runs longer than ten minutes on a 16-row fixture is a hang, and fails the scenario.
    client = NotebookClient(nb, kernel_name="python3", timeout=600, resources={"metadata": {"path": str(path)}})
    with client.setup_kernel():
        for i in chosen:
            try:
                client.execute_cell(nb.cells[i], i)
            except Exception as e:
                first = nb.cells[i].source.splitlines()[0]
                failed = first[2:].split(" —")[0]
                error = ((e.ename + ": " + str(e.evalue)) if isinstance(e, CellExecutionError) else repr(e))[:400]
                break
    # Never write the test password into the saved notebook.
    nb.cells[step_index(nb, 1)].source = nb.cells[step_index(nb, 1)].source.replace(USER_PW, "<redacted>")
    nbformat.write(nb, OUT / f"{name}.ipynb")
    text = "\n".join(o.get("text", "") + o.get("data", {}).get("text/plain", "") for c in nb.cells if c.cell_type == "code" for o in c.get("outputs", []))
    found = {t: t in text for t in expect_text}
    ok = (failed == expect_fail) and all(found.values()) and (expect_error is None or (error or "").find(expect_error) >= 0)
    extra = None
    if check:
        try:
            extra = check()
            ok = ok and extra.get("ok", True)
        except Exception as e:
            extra, ok = {"check_error": repr(e)}, False
    result = {"test": name, "ok": ok, "failed_at": failed, "expected_failure": expect_fail, "expected_error": expect_error,
              "error": error, "texts_found": found, "extra": extra, "seconds": round(time.time() - started, 1)}
    RESULTS.append(result)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    (OUT / "results.json").write_text(json.dumps(RESULTS, indent=1, ensure_ascii=False))
    return result


def csv_rows():
    csv.field_size_limit(1 << 24)
    with gzip.open(DELIVERY / (CSV_NAME + ".gz"), "rt", encoding="utf-8", newline="") as fh:
        return {int(r["source_row"]): r for r in csv.DictReader(fh)}


B = "COLLATE Latin1_General_100_BIN2"


def loaded_matches_csv():
    """Read back through pyodbc and compare, cell by cell, with the CSV text: the published text
    columns as they are, empty for empty; the derived ones rendered in SQL; NULL where the CSV is
    empty. Then the cells this extract is awkward for, counted by code point and by DATALENGTH,
    never with = or LEN, which ignore a trailing space."""
    rows = csv_rows()
    cols = ["ADDRESS1", "ADDRESS2", "POST_TOWN", "POSTCODE", "IMPROVEMENT_RECOMMENDATIONS", "CONSTITUENCY_LABEL", "PROPERTY_TYPE", "PROPERTY_TYPE_SHORT", "DATA_ZONE",
            "BUILDING_REFERENCE_NUMBER", "CURRENT_ENERGY_PERFORMANCE_BAND", "NEW_BUILD_ENERGY_PERFORMANCE_RATING", "POTENTIAL_ENERGY_PERFORMANCE_RATING",
            "ASSET_RATING", "MEETS_2002_STANDARD", "REPORT_REFERENCE_NUMBER", "OSG_REFERENCE_NUMBER", "rrn", "pc_norm", "datazone_2001", "datazone_2011"]
    rendered = {"uprn_osg": "CONVERT(nvarchar(30), uprn_osg)", "uprn_sepcr": "CONVERT(nvarchar(30), uprn_sepcr)",
                "lodgement_date_parsed": "CONVERT(nvarchar(30), lodgement_date_parsed, 23)", "inspection_date_parsed": "CONVERT(nvarchar(30), inspection_date_parsed, 23)",
                "created_at_parsed": "REPLACE(CONVERT(nvarchar(30), created_at_parsed, 126), 'T', ' ')",
                "historic_flag": "CONVERT(nvarchar(1), historic_flag)", "building_emissions_num": "CONVERT(nvarchar(40), building_emissions_num)",
                "potential_energy_performance_rating_num": "CONVERT(nvarchar(40), potential_energy_performance_rating_num)",
                "floor_area_int": "CONVERT(nvarchar(20), floor_area_int)", "current_energy_performance_rating_int": "CONVERT(nvarchar(20), current_energy_performance_rating_int)",
                "primary_energy_value_int": "CONVERT(nvarchar(20), primary_energy_value_int)"}
    nullable = ("rrn", "pc_norm", "datazone_2001", "datazone_2011", "uprn_osg", "potential_energy_performance_rating_num")
    select = ", ".join([f"[{c}]" for c in cols] + list(rendered.values()))
    got = q(f"SELECT source_row, {select} FROM {TABLE}")
    assert len(got) == len(rows) == FIXTURE_ROWS, (len(got), len(rows))
    diffs, checked = [], 0
    for r in got:
        key = r[0]; expect = rows[key]
        for i, c in enumerate(cols + list(rendered)):
            e, g = expect[c], r[1 + i]
            if c in nullable and e == "":
                e = None
            checked += 1
            if e != g:
                diffs.append({"row": key, "column": c, "csv_length": len(e or ""), "sql_length": len(g) if isinstance(g, str) else None,
                              "csv": (e or "")[:40], "sql": (g or "")[:40] if isinstance(g, str) else g})
    # Row 7 holds the 4,451-character cell that ends with a space, row 9 the 7,999-character one,
    # row 16 a cell of 4,451 characters whose last is a supplementary character: 4,452 UTF-16 units.
    long = [x[0] for x in q(f"SELECT DATALENGTH(IMPROVEMENT_RECOMMENDATIONS) / 2 FROM {TABLE} WHERE source_row IN (7, 9, 16) ORDER BY source_row")]
    # Row 15 fills two bounded columns to the last unit with a supplementary character at the end.
    # The last four bytes are the surrogate pair of U+1F3E2 in UTF-16LE, whatever the collation.
    full = list(q(f"SELECT DATALENGTH(ADDRESS1) / 2, DATALENGTH(PROPERTY_TYPE_SHORT) / 2, "
                  f"SUBSTRING(CONVERT(varbinary(max), ADDRESS1), DATALENGTH(ADDRESS1) - 3, 4), "
                  f"SUBSTRING(CONVERT(varbinary(max), PROPERTY_TYPE_SHORT), DATALENGTH(PROPERTY_TYPE_SHORT) - 3, 4) FROM {TABLE} WHERE source_row = 15")[0])
    full = [full[0], full[1], bytes(full[2]).hex(), bytes(full[3]).hex()]
    counts = q(f"SELECT COUNT(*), SUM(CASE WHEN uprn_osg IS NULL THEN 1 ELSE 0 END), SUM(CASE WHEN rrn IS NULL THEN 1 ELSE 0 END), "
               f"SUM(CASE WHEN DATALENGTH(OSG_REFERENCE_NUMBER) = 0 THEN 1 ELSE 0 END), SUM(CASE WHEN OSG_REFERENCE_NUMBER IS NULL THEN 1 ELSE 0 END), "
               f"SUM(CASE WHEN potential_energy_performance_rating_num IS NULL THEN 1 ELSE 0 END), "
               f"SUM(CASE WHEN POTENTIAL_ENERGY_PERFORMANCE_RATING = N'Data removed' {B} THEN 1 ELSE 0 END), "
               f"SUM(CASE WHEN CHARINDEX(NCHAR(9), ADDRESS1 {B}) > 0 THEN 1 ELSE 0 END), SUM(CASE WHEN CHARINDEX(NCHAR(9), POSTCODE {B}) > 0 THEN 1 ELSE 0 END), "
               f"SUM(CASE WHEN CHARINDEX(NCHAR(65533), ADDRESS2 {B}) > 0 THEN 1 ELSE 0 END), "
               f"SUM(CASE WHEN UNICODE(RIGHT(IMPROVEMENT_RECOMMENDATIONS, 1)) = 32 THEN 1 ELSE 0 END), "
               f"SUM(CASE WHEN CHARINDEX(NCHAR(9), pc_norm {B}) > 0 OR CHARINDEX(N' ', pc_norm {B}) > 0 THEN 1 ELSE 0 END) FROM {TABLE}")[0]
    expected_counts = [FIXTURE_ROWS, 1, 1, 1, 0, 1, 1, 1, 1, 1,
                       sum(r["IMPROVEMENT_RECOMMENDATIONS"].endswith(" ") for r in rows.values()), 0]
    nbsp = q(f"SELECT COUNT(*) FROM {TABLE} WHERE CHARINDEX(NCHAR(160), ADDRESS1 {B}) > 0 AND CHARINDEX(N'€', IMPROVEMENT_RECOMMENDATIONS {B}) > 0")[0][0]
    ok = (not diffs and long == [4451, 7999, 4452] and full == [100, 32, "3cd8e2df", "3cd8e2df"]
          and list(counts) == expected_counts and nbsp == 1)
    return {"ok": ok, "cells_checked": checked, "diffs": diffs, "long_cells": long, "full_bounded_cells": full, "counts": list(counts),
            "expected_counts": expected_counts, "nbsp_euro_rows": nbsp}


def main():
    OUT.mkdir(exist_ok=True)
    setup()
    full_ok = ("the file is exactly what the build wrote", "every check passed", "seven rows in, seven out, every status as expected")
    run("01_full_run", folder("a"), expect_text=full_ok, check=loaded_matches_csv)
    run("02_rerun_same_folder", RUNS / "a", expect_text=full_ok, check=loaded_matches_csv)

    def flip(p):
        with gzip.open(p / (CSV_NAME + ".gz")) as src, open(p / CSV_NAME, "wb") as dst:
            shutil.copyfileobj(src, dst)
        data = bytearray((p / CSV_NAME).read_bytes()); i = data.index(b"Natural Gas"); data[i] = ord("n")
        (p / CSV_NAME).write_bytes(data)
    before = q(f"SELECT COUNT_BIG(*), CHECKSUM_AGG(BINARY_CHECKSUM(*)) FROM {TABLE}")[0]
    unchanged = lambda: {"ok": q(f"SELECT COUNT_BIG(*), CHECKSUM_AGG(BINARY_CHECKSUM(*)) FROM {TABLE}")[0] == before}
    run("03_one_byte_changed_in_csv", folder("t03", flip), expect_fail="Step 2", expect_error="the file is not the one this build produced", check=unchanged)

    # Changes to the loaded table: step 5 must fail on each, then pass once it is restored. The
    # original cell is kept in a table, so the restore puts back exactly what the load wrote.
    def tampered(name, row, column, new_value):
        q(f"DROP TABLE IF EXISTS dbo.probe_saved; SELECT source_row, [{column}] AS saved INTO dbo.probe_saved FROM {TABLE} WHERE source_row = {row}")
        changed = q(f"UPDATE {TABLE} SET [{column}] = {new_value} WHERE source_row = {row}; SELECT @@ROWCOUNT")
        try:
            return run(name, RUNS / "a", steps=[1, 2, 5], expect_fail="Step 5", expect_error="does not match the build", expect_text=("FAIL",))
        finally:
            q(f"UPDATE t SET [{column}] = s.saved FROM {TABLE} t JOIN dbo.probe_saved s ON s.source_row = t.source_row; DROP TABLE dbo.probe_saved")
    tampered("04_changed_value_caught_by_digest", 1, "CURRENT_ENERGY_PERFORMANCE_BAND", "N'E'")
    tampered("05_null_made_empty_caught_by_digest", 2, "rrn", "N''")
    tampered("06_trailing_space_removed_caught_by_digest", 1, "IMPROVEMENT_RECOMMENDATIONS",
             "LEFT(IMPROVEMENT_RECOMMENDATIONS, DATALENGTH(IMPROVEMENT_RECOMMENDATIONS) / 2 - 1)")
    tampered("06b_tab_replaced_by_space_caught_by_digest", 3, "ADDRESS1", f"REPLACE(ADDRESS1 {B}, NCHAR(9), N' ')")
    tampered("06c_last_character_of_the_max_cell_changed_caught_by_digest", 9, "IMPROVEMENT_RECOMMENDATIONS",
             "STUFF(IMPROVEMENT_RECOMMENDATIONS, DATALENGTH(IMPROVEMENT_RECOMMENDATIONS) / 2, 1, N'#')")
    run("07_restored_passes_again", RUNS / "a", steps=[1, 2, 5], expect_text=("every check passed",), check=unchanged)

    # A batch the server rejects: chunks of 4 rows, the second carrying a value SQL Server cannot convert.
    def break_batch(nb):
        cell = nb.cells[step_index(nb, 4)]
        cell.source = cell.source.replace("CHUNK = 20_000", "CHUNK = 4").replace(
            "        cur.executemany(insert, chunk[COLUMNS].values.tolist())",
            "        if loaded == 4: chunk.loc[chunk.index[0], 'source_row'] = 'x'\n        cur.executemany(insert, chunk[COLUMNS].values.tolist())")
        assert "loaded == 4" in cell.source and "CHUNK = 4" in cell.source
    def first_chunk_only():
        n = q(f"SELECT COUNT(*) FROM {TABLE}")[0][0]
        return {"ok": n == 4, "rows_left_in_table": n, "note": "step 4 commits per chunk: the rows before the failing chunk stay"}
    run("08_failed_batch_keeps_earlier_chunks", RUNS / "a", steps=[1, 2, 3, 4], edit=break_batch, expect_fail="Step 4",
        expect_error="Conversion failed when converting the nvarchar value 'x'", check=first_chunk_only)

    # The checks of step 4 before anything is sent: a decimal not in 4-decimal form, and a text
    # longer than its bounded column, each stop before the insert.
    def break_decimal(nb):
        cell = nb.cells[step_index(nb, 4)]
        old = "        chunk = chunk.astype(object)"
        assert cell.source.count(old) == 1
        cell.source = cell.source.replace(old, old + "\n        chunk.loc[chunk.index[0], 'building_emissions_num'] = '1.5'")
    empty = lambda: {"ok": q(f"SELECT COUNT(*) FROM {TABLE}")[0][0] == 0}
    run("09_bad_decimal_stops_before_insert", RUNS / "a", steps=[1, 2, 3, 4], edit=break_decimal, expect_fail="Step 4",
        expect_error="building_emissions_num: '1.5' is not a 4-decimal value", check=empty)

    def break_width(nb):
        cell = nb.cells[step_index(nb, 4)]
        old = "        chunk = chunk.astype(object)"
        assert cell.source.count(old) == 1
        # 32 characters, 33 UTF-16 code units: one too many for nvarchar(32) although the character count fits.
        cell.source = cell.source.replace(old, old + "\n        chunk.loc[chunk.index[0], 'PROPERTY_TYPE_SHORT'] = 'x' * 31 + chr(0x1F3E2)")
    run("09b_text_too_long_for_its_column_stops_before_insert", RUNS / "a", steps=[1, 2, 3, 4], edit=break_width, expect_fail="Step 4",
        expect_error="PROPERTY_TYPE_SHORT: a value of 33 UTF-16 code units does not fit nvarchar(32)", check=empty)
    run("10_full_run_after_failures", RUNS / "a", expect_text=full_ok, check=loaded_matches_csv)
    teardown()
    failed = [r["test"] for r in RESULTS if not r["ok"]]
    print("SUMMARY", len(RESULTS) - len(failed), "of", len(RESULTS), "tests as expected", flush=True)
    # A caller or CI must see a failure as a nonzero status, never only as a word in the output.
    if failed or len(RESULTS) != SCENARIOS:
        print(f"FAILED: {failed or 'none'}; {len(RESULTS)} of {SCENARIOS} scenarios recorded", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        (OUT / "results.json").write_text(json.dumps(RESULTS, indent=1, ensure_ascii=False))
        raise

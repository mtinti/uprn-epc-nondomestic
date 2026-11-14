"""The upload notebook: it is generated from the manifest, every code cell parses, and the
table-definition parsing of step 3 reproduces the CSV header from the shipped import script."""

import ast
import gzip
import json
import re
import subprocess
import sys
from pathlib import Path

import duckdb
import nbformat
import pytest

ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK = ROOT / "loader" / "upload_epc_nondomestic.ipynb"
MANIFEST = ROOT / "results" / "manifest.json"
IMPORT_SQL = ROOT / "docs" / "sql" / "import_csv.sql"

needs_build = pytest.mark.skipif(not (NOTEBOOK.is_file() and MANIFEST.is_file()), reason="no build or notebook present")


@needs_build
def test_notebook_cells_parse_and_carry_the_manifest_numbers():
    nb = nbformat.read(NOTEBOOK, as_version=4)
    m = json.loads(MANIFEST.read_text())["csv"]
    code = [c.source for c in nb.cells if c.cell_type == "code"]
    assert len(code) == 7
    for source in code:
        ast.parse(source.replace("display(", "print("))
    step2 = code[1]
    assert m["uncompressed_sha256"] in step2 and str(m["uncompressed_bytes"]) in step2
    assert str(m["rows"]) in step2 and m["digest"]["total"] in step2
    text = "\n".join(c.source for c in nb.cells)
    assert "TEST STREET" not in text and "TEST HOUSE" not in text   # no address value is ever embedded in the notebook
    for stale in ("epc_domestic.csv", "source_year", "ADDENDUM_TEXT", "CURRENT_ENERGY_RATING", "total_floor_area_int"):
        assert stale not in text, stale


@needs_build
def test_notebook_connections_cannot_inherit_an_open_transaction():
    """Found by the notebook probe of 30 October 2026: pyodbc pools connections, the SQL Server
    ODBC driver opens an implicit transaction on any statement under autocommit=False, and a pooled
    connection comes back with that transaction still open. Step 4's autocommit connection was given
    step 1's session and its CREATE INDEX statements never committed, so step 5 waited forever on the
    schema locks. Pooling must be off before the first connection, every connection that only reads must
    autocommit, and the two that write must end with no transaction open."""
    nb = nbformat.read(NOTEBOOK, as_version=4)
    code = {c.source.split(" ")[2]: c.source for c in nb.cells if c.cell_type == "code"}
    step1 = code["1"]
    assert step1.index("pyodbc.pooling = False") < step1.index("pyodbc.connect(")
    connects = re.findall(r"pyodbc\.connect\((.*?)\)", "\n".join(code.values()))
    assert len(connects) == 7
    without_autocommit = [c for c in connects if "autocommit=True" not in c]
    assert without_autocommit == ["CONN, timeout=120"], without_autocommit    # step 4's loading connection, which commits per chunk
    step3, step4 = code["3"], code["4"]
    assert "cn.autocommit = False" in step3 and step3.count("cn.autocommit = True") == 2 and step3.index("cn.commit()") < step3.rindex("cn.autocommit = True") < step3.index("display(")
    assert "cn.close()" in step4 and step4.index("cn.close()") < step4.index("for statement in INDEXES")
    assert "SET LOCK_TIMEOUT" in step3 and "SET LOCK_TIMEOUT" in step4 and "SET LOCK_TIMEOUT" in code["5"]


def _step_3_pattern():
    """The column pattern as the notebook's step 3 carries it, so the test exercises the
    notebook's own code and not a copy of it."""
    nb = nbformat.read(NOTEBOOK, as_version=4)
    step3 = next(c.source for c in nb.cells if c.cell_type == "code" and c.source.startswith("# Step 3 "))
    namespace = {"re": re}
    exec(next(l for l in step3.splitlines() if l.startswith("COLUMN_LINE = ")), namespace)
    return namespace["COLUMN_LINE"]


@needs_build
def test_step_3_parsing_reproduces_the_csv_header_with_the_max_column():
    recipe = IMPORT_SQL.read_text(encoding="utf-8")
    block = re.search(r"CREATE TABLE epc_nondomestic \((.*?)\n\);", recipe, re.S)
    assert block
    spec = _step_3_pattern().findall(block.group(1))
    columns = [name for name, _, _ in spec]
    types = {name: kind for name, kind, _ in spec}
    not_null = {name for name, _, nn in spec if nn}
    assert len(columns) == 57 and len(columns) - len(not_null) == 6
    assert {n for n in columns if n not in not_null} == {"rrn", "uprn_osg", "pc_norm", "datazone_2001", "datazone_2011", "potential_energy_performance_rating_num"}
    # The nvarchar(max) column is parsed like any other, in its place.
    assert types["IMPROVEMENT_RECOMMENDATIONS"] == "nvarchar(max)" and columns.index("IMPROVEMENT_RECOMMENDATIONS") == 30
    assert [n for n, t in types.items() if t == "nvarchar(max)"] == ["IMPROVEMENT_RECOMMENDATIONS"]
    assert len([l for l in block.group(1).splitlines() if l.strip().startswith("[")]) == len(columns)
    csv_path = ROOT / "results" / "epc_nondomestic.csv.gz"
    if csv_path.is_file():
        with gzip.open(csv_path, "rt", encoding="utf-8", newline="") as fh:
            header = fh.readline().rstrip("\n").split(",")
        assert header == columns
    indexes = [l for l in recipe.splitlines() if l.startswith("CREATE INDEX IX_epc_nondomestic_")]
    assert len(indexes) == 3


@needs_build
def test_a_pattern_that_knows_only_bounded_nvarchar_would_drop_the_max_column():
    """The defect the plan review found in uprn-epc's notebook: its pattern silently skipped an
    nvarchar(max) column. The notebook here must see all three columns of this definition and
    count the lines it understood."""
    ddl = "    [A] nvarchar(32) NOT NULL,\n    [LONG] nvarchar(max) NOT NULL,\n    [B] bigint,"
    assert [n for n, _, _ in _step_3_pattern().findall(ddl)] == ["A", "LONG", "B"]
    old = re.compile(r"\[([^\]]+)\] (nvarchar\(\d+\)|bigint|smallint|int|bit|datetime2\(0\)|date|decimal\(\d+,\d+\))( NOT NULL)?")
    assert [n for n, _, _ in old.findall(ddl)] == ["A", "B"]
    nb = nbformat.read(NOTEBOOK, as_version=4)
    step3 = next(c.source for c in nb.cells if c.cell_type == "code" and c.source.startswith("# Step 3 "))
    assert "assert len(declared) == len(COLUMNS)" in step3 and step3.index("assert len(declared) == len(COLUMNS)") < step3.index("DROP TABLE IF EXISTS")


@needs_build
def test_step_4_binds_the_max_column_and_checks_what_it_stored():
    nb = nbformat.read(NOTEBOOK, as_version=4)
    step4 = next(c.source for c in nb.cells if c.cell_type == "code" and c.source.startswith("# Step 4 "))
    namespace = {"re": re, "TYPES": {"A": "nvarchar(32)", "LONG": "nvarchar(max)", "N": "decimal(19,4)", "D": "date"}}
    for name in ("WIDTH", "LIMIT", "longest_sent"):
        exec(next(l for l in step4.splitlines() if l.startswith(f"{name} = ")), namespace)
    assert namespace["WIDTH"] == {"A": 32, "LONG": 0, "N": 40, "D": 40}
    assert namespace["LIMIT"] == {"A": 32} and namespace["longest_sent"] == {"LONG": 0}
    assert "assert stored == sent" in step4
    # Both lengths are in UTF-16 code units, the unit of DATALENGTH / 2: the notebook's own helper,
    # run here, counts a supplementary character as two.
    import pandas as pd
    helper = {}
    start = step4.index('SUPPLEMENTARY = "')
    exec(step4[start:step4.index("\n\n", start)], helper)
    values = pd.Series(["abc", "ab\U0001F3E2", "x" * 4450 + "\U0001F3E2"])
    assert helper["sql_length"](values).tolist() == [3, 4, 4452] == [len(v.encode("utf-16-le")) // 2 for v in values]
    assert "lengths = sql_length(chunk[col])" in step4 and "int(sql_length(chunk[col]).max())" in step4
    assert ".str.len() > limit" not in step4 and "chunk[col].str.len().max()" not in step4
    # An empty cell of the nullable decimal is allowed, an empty cell of a required one is not.
    assert 'if col in NULLABLE:\n                bad &= chunk[col].ne("")' in step4


def _step_6_queries():
    """The two queries of step 6, with T-SQL spelling changed for DuckDB: TOP (1) to LIMIT 1,
    COUNT_BIG to COUNT, CONVERT(decimal(5,1), x) to CAST(x AS DECIMAL(5,1))."""
    nb = nbformat.read(NOTEBOOK, as_version=4)
    step6 = next(c.source for c in nb.cells if c.cell_type == "code" and c.source.startswith("# Step 6 "))
    queries = re.findall(r'pd\.read_sql\(f"""(.*?)""", cn\)', step6, re.S)
    assert len(queries) == 2
    out = []
    for q in queries:
        q = q.replace("{TABLE}", "epc_nondomestic").replace("COUNT_BIG(*)", "COUNT(*)")
        q = re.sub(r"CONVERT\(decimal\(5,1\), (.*?)\) AS", r"CAST(\1 AS DECIMAL(5,1)) AS", q)
        q = re.sub(r"SELECT TOP \(1\) (.*?) ORDER BY uprn_osg\)", r"SELECT \1 ORDER BY uprn_osg LIMIT 1)", q, flags=re.S)
        assert "TOP" not in q, q
        out.append(q)
    return out


def _table(con, pairs):
    con.execute("CREATE TABLE epc_nondomestic (source_row INTEGER, uprn_osg BIGINT, pc_norm VARCHAR, inspection_date_parsed DATE, lodgement_date_parsed DATE, "
                "created_at_parsed TIMESTAMP, historic_flag BOOLEAN, CURRENT_ENERGY_PERFORMANCE_BAND VARCHAR, current_energy_performance_rating_int INTEGER, "
                "floor_area_int INTEGER, building_emissions_num DECIMAL(19,4), primary_energy_value_int INTEGER, PROPERTY_TYPE_SHORT VARCHAR)")
    rows = [(1, 35000009, "FK101AA", "2024-01-04", "2024-01-05", "2024-01-05 09:00:00", False, "C", 40, 900, 40.2, 250, "Office/Workshop")]
    for uprn, n in pairs:
        for i in range(n):
            rows.append((100 + len(rows), uprn, "FK101AA", f"{2015 + i}-05-30", f"{2015 + i}-06-01", f"{2015 + i}-06-01 09:00:00", i < n - 1, "D", 60, 80, 60.0, 300, "Retail/Financial"))
    con.executemany("INSERT INTO epc_nondomestic VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)


@needs_build
def test_step_6_picks_one_twice_assessed_building():
    """Two buildings each with two certificates, plus one with three and one with one: the sample
    must return the first row of the file and the two certificates of the lowest qualifying UPRN."""
    per_year, sample = _step_6_queries()
    con = duckdb.connect()
    _table(con, [(35000002, 2), (35000001, 2), (35000003, 3), (35000004, 1)])
    years = con.execute(per_year).fetchall()
    assert [y[0] for y in years] == [2015, 2016, 2017, 2024] and sum(y[1] for y in years) == 9
    rows = con.execute(sample).fetchall()
    assert [(r[0] == 1, r[1]) for r in rows] == [(False, 35000001), (False, 35000001), (True, 35000009)]


@needs_build
def test_step_6_with_no_twice_assessed_building_shows_the_first_row_only():
    _, sample = _step_6_queries()
    con = duckdb.connect()
    _table(con, [(35000003, 3), (35000004, 1)])
    rows = con.execute(sample).fetchall()
    assert len(rows) == 1 and rows[0][0] == 1


def test_the_old_grouped_min_selector_fails_with_two_qualifying_buildings():
    """The form uprn-epc's notebook carried before 30 October 2026: GROUP BY returns one MIN per
    group, so the equality receives several rows. DuckDB rejects it as SQL Server does."""
    con = duckdb.connect()
    _table(con, [(35000002, 2), (35000001, 2)])
    with pytest.raises(duckdb.Error, match="More than one row"):
        con.execute("SELECT * FROM epc_nondomestic WHERE uprn_osg = (SELECT MIN(uprn_osg) FROM epc_nondomestic "
                    "WHERE uprn_osg IS NOT NULL GROUP BY uprn_osg HAVING COUNT(*) = 2)").fetchall()


# --- the connection string of a site never enters the committed notebook ----------------------

def _step_1() -> str:
    nb = json.loads(NOTEBOOK.read_text())
    return next("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code" and "".join(c["source"]).startswith("# Step 1 "))


def test_the_committed_notebook_has_an_empty_connection_string_and_stops_on_it():
    step1 = _step_1()
    assert re.search(r'^CONN     = ""$', step1, re.M), "the committed notebook must carry an empty CONN"
    assert not re.search(r'^(SERVER|DATABASE)\s*=', step1, re.M)
    # The only place a server is named is the comment that shows the shape, with placeholders.
    assert re.findall(r"SERVER=([^;\"]*)", step1) == ["<server>"] and re.findall(r"DATABASE=([^;\"]*)", step1) == ["<database>"]
    assert "TrustServerCertificate" not in step1
    # An empty CONN stops the cell before anything is unpacked or connected to.
    stop = step1.index("if not CONN.strip():")
    assert stop < step1.index("packed = FOLDER") and stop < step1.index("pyodbc.connect(")
    env = {}
    with pytest.raises(ValueError, match="CONN is empty"):
        exec("CONN = '  '\n" + step1[stop:step1.index("\n\n", stop)], env)


def _make_notebook(*args):
    return subprocess.run([sys.executable, str(ROOT / "loader" / "make_notebook.py"), *map(str, args)], capture_output=True, text=True, cwd=ROOT)


@needs_build
def test_a_site_copy_carries_the_connection_string_and_cannot_be_written_into_the_repository(tmp_path):
    site = tmp_path / "site_connection.txt"
    site.write_text("DRIVER={ODBC Driver 18 for SQL Server};SERVER=a-test-server;DATABASE=a_test_db;Trusted_Connection=yes;\n")
    out = tmp_path / "site_copy.ipynb"
    done = _make_notebook(ROOT / "results", out, "--site", site)
    assert done.returncode == 0, done.stderr
    text = out.read_text()
    assert "SERVER=a-test-server;DATABASE=a_test_db" in text and 'CONN     = \\"\\"' not in text
    before = NOTEBOOK.read_bytes()
    # The committed path, and any other path inside the repository outside local/, is refused.
    for target in (NOTEBOOK, ROOT / "docs" / "site_copy.ipynb"):
        done = _make_notebook(ROOT / "results", target, "--site", site)
        assert done.returncode != 0 and "not written inside the repository" in done.stderr, target
        assert not (ROOT / "docs" / "site_copy.ipynb").exists()
    assert NOTEBOOK.read_bytes() == before
    # A site file that is empty, or holds more than one line, is refused.
    for bad in ("", "DRIVER=x;\nSERVER=y;\n"):
        site.write_text(bad)
        done = _make_notebook(ROOT / "results", tmp_path / "bad.ipynb", "--site", site)
        assert done.returncode != 0 and "must hold one line" in done.stderr
    assert not (tmp_path / "bad.ipynb").exists()

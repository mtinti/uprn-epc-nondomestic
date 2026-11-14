"""Write loader/upload_epc_nondomestic.ipynb, the notebook that loads the non-domestic EPC CSV
into SQL Server from a client machine through pyodbc, as the postcode-simd, datazone-ahah and
uprn-epc upload notebooks do. It carries this build's hash, row count and digest from
results/manifest.json, and the column counts of docs/sql/import_csv.sql.

    python loader/make_notebook.py [results_dir [output.ipynb]] [--site FILE]

Without arguments it reads results/manifest.json and writes loader/upload_epc_nondomestic.ipynb.
The two arguments let a test build a notebook for a fixture release and run it against SQL Server.

The notebook is written with an empty connection string. --site FILE writes a copy for one site,
with the connection string that FILE holds on one line, to a path outside the repository or under
local/.
"""

import json
import re
import sys
from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parent.parent
# A site's own connection string never goes into the committed notebook. Without --site the
# notebook is written with an empty CONN for the analyst to fill in. With --site FILE, where FILE
# holds the ODBC connection string on one line, the notebook is written with it, and only to a
# path outside the repository or under local/, which git ignores.
ARGS = sys.argv[1:]
SITE = None
if "--site" in ARGS:
    _i = ARGS.index("--site")
    if _i + 1 >= len(ARGS):
        sys.exit("stopped: --site needs the path of a file holding the connection string")
    SITE = Path(ARGS[_i + 1])
    del ARGS[_i:_i + 2]
RESULTS = Path(ARGS[0]) if len(ARGS) > 0 else ROOT / "results"
OUT = Path(ARGS[1]) if len(ARGS) > 1 else ROOT / "loader" / "upload_epc_nondomestic.ipynb"
m = json.loads((RESULTS / "manifest.json").read_text())
c = m["csv"]
o = m["observations"]["table"]
built = m["built_at"][:10]
release = m["epc_release"]

# The table definition the notebook will parse, read here only to say what to expect of it.
# COLUMN_PATTERN is the one pattern both this generator and the notebook's step 3 use. It knows
# nvarchar(max): a pattern that knew only nvarchar(n) would drop that column without an error.
COLUMN_PATTERN = r"\[([^\]]+)\] (nvarchar\(\d+\)|nvarchar\(max\)|bigint|smallint|int|bit|datetime2\(0\)|date|decimal\(\d+,\d+\))( NOT NULL)?"
_recipe = (ROOT / "docs" / "sql" / "import_csv.sql").read_text(encoding="utf-8")
_spec = re.findall(COLUMN_PATTERN, re.search(r"CREATE TABLE epc_nondomestic \((.*?)\n\);", _recipe, re.S).group(1))
assert len(_spec) == c["columns"], f"import_csv.sql declares {len(_spec)} columns and the build wrote {c['columns']}; regenerate the SQL"
_kinds = {}
for _name, _type, _nn in _spec:
    _kind = "nvarchar(max)" if _type == "nvarchar(max)" else re.sub(r"\(.*\)", "", _type) if _type.startswith("nvarchar") else _type
    _kinds[_kind] = _kinds.get(_kind, 0) + 1
KIND_TEXT = ", ".join(f"{k} {v}" for k, v in sorted(_kinds.items(), key=lambda kv: -kv[1]))
NULLABLE_NAMES = [n for n, t, nn in _spec if not nn]
MAX_NAMES = [n for n, t, nn in _spec if t == "nvarchar(max)"]
INDEX_COUNT = sum(1 for line in _recipe.splitlines() if line.startswith("CREATE INDEX IX_epc_nondomestic_"))
size_mb = c["uncompressed_bytes"] / 1e6

cells = []
md = lambda s: cells.append(nbf.v4.new_markdown_cell(s.strip()))
code = lambda s: cells.append(nbf.v4.new_code_cell(s.strip()))

md(f"""
# Load the Scottish non-domestic EPCs into SQL Server

**What this notebook does.** It loads `epc_nondomestic`, one row per non-domestic Energy Performance
Certificate in the Scottish Government's extended historic extract, release {release} (build of {built},
{c['rows']:,} rows by {c['columns']} columns), into SQL Server from this machine through pyodbc, proves the
load is faithful with the digest the build recorded, and then shows the table in use: rows per year, a
few certificates, and the left join by UPRN with its statuses.

**Before you start**

1. Put in one folder: `epc_nondomestic.csv.gz` (or the unpacked `epc_nondomestic.csv`, {size_mb:.0f} MB),
   `import_csv.sql` and `check_loaded_digest.sql` from `docs/sql/`.
2. Set `FOLDER`, `CONN` and `TABLE` in step 1.
3. You need `CREATE TABLE` rights in the database. Step 1 tells you whether you have them.

**Time.** Step 4 sends {c['rows']:,} rows of {c['columns']} columns through pyodbc and prints progress every
20,000 rows. It commits every chunk, so an interrupted run can be read for how far it got and then
restarted from step 3. Against a SQL Server container on the same machine the rows of release 2026Q3 took
8 seconds and the digest check of step 5 took 1 (run of 14 November 2026). Over a network to the HIC
server expect longer.

**Run the cells in order, top to bottom.** Every step says what it does, what to expect and why.

**Not all-or-nothing.** Step 3 drops and recreates the table and step 4 commits each chunk, so a failure in
step 4 or 5 leaves a table that is incomplete or unverified. The message says which step failed and the
run restarts from step 3. For a first load that is fine. To refresh a table that people already use, set
`TABLE` to a new name, run the notebook, and rename the two tables only after step 5 has passed.

**Addresses.** The CSV holds the three address lines and the postcode. Both stay inside the safe haven. An
analyst-facing view without the address columns is suggested.

**Not the domestic table.** The rating and the band of a non-domestic certificate rate emissions, and lower
is better. They are not the rating and band of `epc_domestic`, which score energy cost.
""")

md("""
---
## Part 1. Set up

### Step 1. Settings, connection and files

**What it does.** Sets the folder, the connection string and the table; unpacks the CSV if only the archive is present;
lists the files it needs; connects and shows who you are connected as.

**What to expect.** Three lines starting `found`, then one row: server, database, your login,
`can_create_table = 1` and the SQL Server version (2019 or later is needed for the UTF-8 collation of the
digest), then `ready`. A missing file or a missing right raises here and nothing later runs.

**Why.** Every later step reads these files and this connection. Step 3 drops and recreates the table, so
the checks that would make it fail half way are made here, before anything is dropped. Connection pooling is
turned off: with it on, a later step can be handed an earlier step's connection with a transaction still
open, and its own statements then run inside that transaction and never commit (found with a fixture run
against SQL Server on 30 October 2026, where step 5 waited on step 4's uncommitted indexes).
""")
code("""
# Step 1 — settings, connection, permissions, files present
import hashlib, re, time
from pathlib import Path

import pandas as pd
import pyodbc

# No connection pooling: a pooled physical connection comes back in the commit mode its last user
# left it in, whatever autocommit the new handle declares, so a connection that believes it is in
# autocommit runs every statement inside a transaction it never commits (probed 31 October 2026,
# loader/notebook_probe/pooling_diag.py).
# Must be set before the first connection of the kernel.
pyodbc.pooling = False

# EDIT: the folder holding the three files
FOLDER   = Path(r"")

# EDIT: the ODBC connection string of your site, on one line. It names the driver, the server,
# the database and how you sign in. Its shape, with your own values in place of the two in <>:
#   DRIVER={ODBC Driver 18 for SQL Server};SERVER=<server>;DATABASE=<database>;Trusted_Connection=yes;
# A copy of this notebook prepared for your site may arrive with the line already filled in.
CONN     = ""
TABLE    = "dbo.epc_nondomestic"   # one row per published certificate

if not CONN.strip():
    raise ValueError("CONN is empty. Put your site's ODBC connection string in step 1, then run the cell again.")

# The CSV may arrive compressed: unpack it once, beside the archive.
packed = FOLDER / "epc_nondomestic.csv.gz"
if not (FOLDER / "epc_nondomestic.csv").is_file() and packed.is_file():
    import gzip, shutil
    print("unpacking", packed.name, "...")
    with gzip.open(packed, "rb") as src, open(FOLDER / "epc_nondomestic.csv", "wb") as dst:
        shutil.copyfileobj(src, dst, 1 << 20)

missing = []
for name in ["epc_nondomestic.csv", "import_csv.sql", "check_loaded_digest.sql"]:
    path = FOLDER / name
    print(f"{'found   ' if path.is_file() else 'MISSING '} {name:28} "
          + (f"{path.stat().st_size:>14,} bytes" if path.is_file() else ""))
    if not path.is_file():
        missing.append(name)

with pyodbc.connect(CONN, timeout=10, autocommit=True) as cn:
    who = pd.read_sql(
        "SELECT @@SERVERNAME AS srv, DB_NAME() AS db, SUSER_NAME() AS login, "
        "HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'CREATE TABLE') AS can_create_table, "
        "CONVERT(varchar(20), SERVERPROPERTY('ProductVersion')) AS version", cn)
    display(who)

# Nothing later may run unless everything step 3 onward needs is here: step 3 drops the table.
if missing:
    raise FileNotFoundError(f"missing from {FOLDER}: {', '.join(missing)}")
if int(who.can_create_table[0]) != 1:
    raise PermissionError(f"{who.login[0]} cannot CREATE TABLE in {who.db[0]}; ask for the right before running step 3")
print("ready")
""")

md(f"""
### Step 2. Is this exactly the file the build produced?

**What it does.** Hashes the CSV, counts its rows and reads its header, and compares them with what the
build of {built} recorded: SHA256 `{c['uncompressed_sha256'][:8]}…`, {c['uncompressed_bytes']:,} bytes,
{c['rows']:,} rows plus a header, {c['columns']} columns.

**What to expect.** `match` on the hash, the expected row and column counts, and the closing message. Any
mismatch stops the cell. Rows are counted with the csv module, not by newline, so a cell with a newline
inside its quotes would still count as one row.

**Why.** A file can be truncated by a download or altered by being opened and saved in Excel. Checking the
hash first means nothing is loaded from a file that is not the build's own. The digest total stored here is
used again in step 5, inside SQL Server.
""")
code(f"""
# Step 2 — verify the transferred file against the build of {built}
import csv
csv.field_size_limit(1 << 24)

EXPECTED = {{
    "csv":          "epc_nondomestic.csv",
    "sha256":       "{c['uncompressed_sha256']}",
    "bytes":        {c['uncompressed_bytes']},
    "rows":         {c['rows']},
    "columns":      {c['columns']},
    "digest_total": "{c['digest']['total']}",   # checked in step 5, inside SQL Server
}}

path = FOLDER / EXPECTED["csv"]
digest = hashlib.sha256()
with open(path, "rb") as fh:
    while True:
        block = fh.read(1 << 20)
        if not block:
            break
        digest.update(block)

rows = 0
with open(path, encoding="utf-8", newline="") as fh:
    reader = csv.reader(fh)
    header = next(reader)
    for _ in reader:
        rows += 1

print(f"size    {{path.stat().st_size:>14,}}   expected {{EXPECTED['bytes']:>14,}}")
print(f"sha256  {{digest.hexdigest()}}")
print(f"        {{EXPECTED['sha256']}}   {{'match' if digest.hexdigest() == EXPECTED['sha256'] else 'MISMATCH'}}")
print(f"rows    {{rows:>14,}}   expected {{EXPECTED['rows']:>14,}}")
print(f"columns {{len(header):>14}}   expected {{EXPECTED['columns']:>14}}")
print(f"first three: {{header[:3]}}")
print(f"last three:  {{header[-3:]}}")

assert digest.hexdigest() == EXPECTED["sha256"], "the file is not the one this build produced"
assert rows == EXPECTED["rows"] and len(header) == EXPECTED["columns"]
print("\\nthe file is exactly what the build wrote")
""")

md(f"""
---
## Part 2. Create and load the table

### Step 3. Create the table from the shipped definition

**What it does.** Takes the `CREATE TABLE epc_nondomestic` statement from `import_csv.sql`, checks its columns
are exactly the CSV's header in the same order, then drops and recreates the table under your name, with the
primary key `(epc_release, source_row)`.

**What to expect.** `{c['columns']} columns`, then the type counts: {KIND_TEXT}. `{', '.join(MAX_NAMES)}` is
`nvarchar(max)` because three of its values are longer than the 4,000 characters a bounded column holds. A
table showing {c['columns']} columns created, of which {len(NULLABLE_NAMES)} are nullable, and the two key columns.

**Why.** The definition ships with the build and is tested against the schema, so using it rather than
writing one by hand guarantees the same types, widths, nullability and key. The drop and the create run in
one transaction: if the create fails, the previous table is still there. The {INDEX_COUNT} join indexes are built in
step 4 after the rows, which is faster than maintaining them during the load.
""")
code("""
# Step 3 — create the table from the shipped definition
recipe = (FOLDER / "import_csv.sql").read_text(encoding="utf-8")

block = re.search(r"CREATE TABLE epc_nondomestic \\((.*?)\\n\\);", recipe, re.S)
assert block, "could not find the table definition in import_csv.sql"

# One line per column: [name] type, then NOT NULL or nothing. nvarchar(max) is a type like the others.
COLUMN_LINE = re.compile(r"\\[([^\\]]+)\\] (nvarchar\\(\\d+\\)|nvarchar\\(max\\)|bigint|smallint|int|bit|datetime2\\(0\\)|date|decimal\\(\\d+,\\d+\\))( NOT NULL)?")
spec = COLUMN_LINE.findall(block.group(1))
TYPES = {name: kind for name, kind, _ in spec}
NOT_NULL = {name for name, _, nn in spec if nn}
COLUMNS = list(TYPES)
# Every line of the definition that names a column must have been understood: a type the pattern
# does not know would otherwise drop its column here and only fail later, or not at all.
declared = [line for line in block.group(1).splitlines() if line.strip().startswith("[")]
assert len(declared) == len(COLUMNS), f"{len(declared)} column lines in the definition, {len(COLUMNS)} understood"
assert COLUMNS == header, "the file's header does not match the shipped table definition"

bare = TABLE.split(".")[-1]
ddl = (block.group(0)
       .replace("CREATE TABLE epc_nondomestic", f"CREATE TABLE {TABLE}")
       .replace("PK_epc_nondomestic", f"PK_{bare}"))
INDEXES = [line.replace("ON epc_nondomestic", f"ON {TABLE}").replace("IX_epc_nondomestic_", f"IX_{bare}_")
           for line in recipe.splitlines() if line.startswith("CREATE INDEX IX_epc_nondomestic_")]
assert len(INDEXES) == 3

kinds = {}
for t in TYPES.values():
    k = t if t == "nvarchar(max)" else re.sub(r"\\(.*\\)", "", t) if t.startswith("nvarchar") else t
    kinds[k] = kinds.get(k, 0) + 1
print(f"{len(COLUMNS)} columns:", kinds, f"; {len(COLUMNS) - len(NOT_NULL)} nullable")
print(ddl.splitlines()[0]); print("   ..."); print("\\n".join(ddl.splitlines()[-2:]))

# One transaction: SQL Server DDL is transactional, so a failed CREATE rolls the DROP back and the
# previous table survives. The transaction is closed before the two queries below, so this connection
# holds no lock when the cell ends. A table someone else is reading makes the DROP wait; the lock
# timeout turns a long wait into an error here rather than a silent hang.
with pyodbc.connect(CONN, timeout=30, autocommit=True) as cn:
    cur = cn.cursor()
    cur.execute("SET LOCK_TIMEOUT 120000;")
    cn.autocommit = False
    try:
        cur.execute(f"DROP TABLE IF EXISTS {TABLE};")
        cur.execute(ddl)
    except Exception:
        cn.rollback()
        cn.autocommit = True
        print(f"create failed; {TABLE} is as it was before this cell")
        raise
    cn.commit()
    cn.autocommit = True
    display(pd.read_sql(
        f\"\"\"SELECT COUNT(*) AS columns_created,
                   SUM(CASE WHEN is_nullable = 1 THEN 1 ELSE 0 END) AS nullable
            FROM sys.columns WHERE object_id = OBJECT_ID('{TABLE}')\"\"\", cn))
    display(pd.read_sql(
        f\"\"\"SELECT i.name AS index_name, c.name AS key_column, ic.key_ordinal
            FROM sys.indexes i
            JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
            JOIN sys.columns c ON c.object_id = i.object_id AND c.column_id = ic.column_id
            WHERE i.object_id = OBJECT_ID('{TABLE}') AND i.is_primary_key = 1
            ORDER BY ic.key_ordinal\"\"\", cn))
""")

md(f"""
### Step 4. Load the rows, then build the join indexes

**What it does.** Reads the CSV in chunks of 20,000 rows and inserts them, binding every value as text and
letting SQL Server convert it into the column's declared type. An empty cell is kept as the empty string in
the {c['columns'] - len(NULLABLE_NAMES)} `NOT NULL` columns, which is what the publisher wrote, and becomes NULL in the {len(NULLABLE_NAMES)} nullable derived
columns ({', '.join('`' + n + '`' for n in NULLABLE_NAMES)}). Before
each chunk is sent, every decimal is checked to be in fixed notation with exactly 4 decimals (or empty, in the
one nullable decimal column), every date to be `yyyy-mm-dd`, every bit to be 0 or 1, and every text to fit its
column. Text is measured as SQL Server measures it, in UTF-16 code units, where an emoji or another
character outside the Basic Multilingual Plane counts as two. When every row is in, the {INDEX_COUNT}
indexes for the join routes are created.

**What to expect.** Progress every 20,000 rows, then `loaded {c['rows']:,} rows`, then one row:
{c['rows']:,} rows in the table, `uprn_osg` NULL in {o['uprn_osg_empty_rows']:,}, `rrn` NULL in
{o['rrn_empty_rows']:,}, `OSG_REFERENCE_NUMBER` NULL in 0 and empty in {o['uprn_osg_empty_rows']:,}, and the longest
`IMPROVEMENT_RECOMMENDATIONS` at {o['longest_text_per_column']['IMPROVEMENT_RECOMMENDATIONS']:,}. Then the {INDEX_COUNT} index names.

**Why.** The server cannot read this machine's files, so `BULK INSERT` is not available. Sending the rows
from here is the alternative. Empty and NULL mean different things in this table and the digest in step 5
tells them apart, so the rule above is the same one the shipped import script applies with `ISNULL` and
`NULLIF`. The `nvarchar(max)` column is bound with size 0, which the notebook probe showed sends a value of
any length whole. The pyodbc documentation does not describe that binding, so step 4 also reads the longest
value back and compares its length with the file's.
""")
code(f"""
# Step 4 — load the rows: empty stays empty in NOT NULL columns, becomes NULL in nullable ones
NULLABLE = [c for c in COLUMNS if c not in NOT_NULL]
DECIMALS = [c for c, t in TYPES.items() if t.startswith("decimal")]
DATES    = [c for c, t in TYPES.items() if t == "date"]
BITS     = [c for c, t in TYPES.items() if t == "bit"]
DECIMAL_TEXT = re.compile(r"^-?\\d{{1,15}}\\.\\d{{4}}$")
DATE_TEXT    = re.compile(r"^\\d{{4}}-\\d{{2}}-\\d{{2}}$")
# Lengths are counted as SQL Server counts an nvarchar, in UTF-16 code units: the characters, plus
# one for each character outside the Basic Multilingual Plane (an emoji, say), which takes two.
SUPPLEMENTARY = "[\\U00010000-\\U0010FFFF]"
def sql_length(values):
    return values.str.len() + values.str.count(SUPPLEMENTARY)

# The size each parameter is bound with: the declared width of an nvarchar(n), 0 for nvarchar(max),
# 40 for a value sent as text and converted by the server. LIMIT is the longest text a bounded
# column takes; a longer value is refused here, before anything is sent, with the column named.
WIDTH = {{c: (0 if t == "nvarchar(max)" else int(re.search(r"\\d+", t).group()) if t.startswith("nvarchar") else 40) for c, t in TYPES.items()}}
LIMIT = {{c: int(re.search(r"\\d+", t).group()) for c, t in TYPES.items() if t.startswith("nvarchar(") and t != "nvarchar(max)"}}
longest_sent = {{c: 0 for c, t in TYPES.items() if t == "nvarchar(max)"}}

CHUNK = 20_000
insert = (f"INSERT INTO {{TABLE}} ([" + "], [".join(COLUMNS) + "]) "
          f"VALUES ({{', '.join('?' * len(COLUMNS))}})")

started, loaded, next_report = time.time(), 0, 20_000
with pyodbc.connect(CONN, timeout=120) as cn:
    cur = cn.cursor()
    cur.fast_executemany = True
    cur.setinputsizes([(pyodbc.SQL_WVARCHAR, WIDTH[c], 0) for c in COLUMNS])
    for chunk in pd.read_csv(path, dtype=str, keep_default_na=False, chunksize=CHUNK, encoding="utf-8"):
        chunk = chunk.astype(object)
        for col in DECIMALS:
            bad = ~chunk[col].str.match(DECIMAL_TEXT)
            if col in NULLABLE:
                bad &= chunk[col].ne("")    # an empty cell of a nullable decimal is its NULL, set below
            assert not bad.any(), f"{{col}}: {{chunk.loc[bad, col].iloc[0]!r}} is not a 4-decimal value"
        for col in DATES:
            bad = ~chunk[col].str.match(DATE_TEXT)
            assert not bad.any(), f"{{col}}: {{chunk.loc[bad, col].iloc[0]!r}} is not yyyy-mm-dd"
        for col in BITS:
            assert chunk[col].isin(["0", "1"]).all(), f"{{col}}: a value other than 0 or 1"
        for col, limit in LIMIT.items():
            lengths = sql_length(chunk[col])
            too_long = lengths > limit
            assert not too_long.any(), f"{{col}}: a value of {{int(lengths[too_long].max())}} UTF-16 code units does not fit nvarchar({{limit}})"
        for col in longest_sent:
            longest_sent[col] = max(longest_sent[col], int(sql_length(chunk[col]).max()))
        for col in NULLABLE:
            chunk.loc[chunk[col].eq(""), col] = None
        cur.executemany(insert, chunk[COLUMNS].values.tolist())
        cn.commit()
        loaded += len(chunk)
        if loaded >= next_report or loaded == EXPECTED["rows"]:
            print(f"  {{loaded:>10,}} rows   {{loaded / (time.time() - started):>6,.0f}} rows/s   {{time.time() - started:>6.0f}}s elapsed")
            next_report += 20_000
cn.close()   # the with block committed; close so this connection holds nothing while the indexes build

print(f"\\nloaded {{loaded:,}} rows in {{time.time() - started:.0f}}s; creating the {{len(INDEXES)}} join indexes ...")
with pyodbc.connect(CONN, timeout=3600, autocommit=True) as cn:
    cn.cursor().execute("SET LOCK_TIMEOUT 120000;")
    for statement in INDEXES:
        cn.cursor().execute(statement)
    display(pd.read_sql(f\"\"\"
        SELECT COUNT_BIG(*) AS rows_in_table,
               SUM(CASE WHEN uprn_osg IS NULL THEN 1 ELSE 0 END)      AS uprn_osg_null,
               SUM(CASE WHEN rrn IS NULL THEN 1 ELSE 0 END)           AS rrn_null,
               SUM(CASE WHEN OSG_REFERENCE_NUMBER IS NULL THEN 1 ELSE 0 END)        AS osg_text_null,
               SUM(CASE WHEN DATALENGTH(OSG_REFERENCE_NUMBER) = 0 THEN 1 ELSE 0 END) AS osg_text_empty,
               MAX(DATALENGTH(IMPROVEMENT_RECOMMENDATIONS)) / 2                      AS longest_improvements
        FROM {{TABLE}}\"\"\", cn))
    # The nvarchar(max) binding: the longest value in the table must be as long as the longest sent.
    # Both are in UTF-16 code units: DATALENGTH counts bytes, two per unit. LEN would not count a
    # trailing space.
    for col, sent in longest_sent.items():
        stored = cn.cursor().execute(f"SELECT MAX(DATALENGTH([{{col}}])) / 2 FROM {{TABLE}}").fetchone()[0]
        assert stored == sent, f"{{col}}: the longest value sent has {{sent}} UTF-16 code units, the longest stored {{stored}}"
        print(f"{{col}}: longest value {{sent:,}} UTF-16 code units sent and stored")
    display(pd.read_sql(f\"\"\"SELECT name AS index_name FROM sys.indexes
                             WHERE object_id = OBJECT_ID('{{TABLE}}') AND is_primary_key = 0 AND name IS NOT NULL\"\"\", cn))
""")

md("""
---
## Part 3. Prove the load is faithful

### Step 5. The digest, recomputed inside SQL Server

**What it does.** Runs the table section of `check_loaded_digest.sql` against your table: the column
structure (names, order, types with precision, scale and width, nullability, bound to this table's object),
the natural key, reserved characters in text, the row count, and a digest of every row compared with the
total the build recorded.

**What to expect.** Five checks, all `pass`, in well under a minute.

**Why.** Steps 2 to 4 check the file and the mechanics; this checks the result. The digest renders each
loaded row exactly as the CSV wrote it and hashes it, so a single changed cell, an empty string loaded as
NULL, or a non-ASCII character read in the wrong code page makes it fail. It is the one check that compares
the table in SQL Server with the build.
""")
code("""
# Step 5 — recompute the digest inside SQL Server and compare it with the build
check = (FOLDER / "check_loaded_digest.sql").read_text(encoding="utf-8")

start = check.rindex("-- ===", 0, check.index("-- epc_nondomestic: structure"))
end   = check.index("-- ===", check.index("END\\n", start))
section = check[start:end].replace("epc_nondomestic", TABLE)

preamble = f\"\"\"
SET NOCOUNT ON;
SET LOCK_TIMEOUT 300000;
DROP TABLE IF EXISTS #expected;
CREATE TABLE #expected (name sysname PRIMARY KEY, row_count bigint NOT NULL,
                        digest_total decimal(38,0) NOT NULL, digest_version int NOT NULL);
INSERT INTO #expected (name, row_count, digest_total, digest_version)
VALUES (N'{TABLE}', {EXPECTED["rows"]}, {EXPECTED["digest_total"]}, 1);
DROP TABLE IF EXISTS #result;
CREATE TABLE #result (table_name sysname, check_name nvarchar(200), expected nvarchar(200),
                      actual nvarchar(200), difference bigint NULL, passed bit NOT NULL);
\"\"\"

print("checking structure, key, framing characters, row count and digest ...")
started = time.time()
with pyodbc.connect(CONN, timeout=3600, autocommit=True) as cn:
    cn.cursor().execute(preamble + section)          # temp tables live for this connection
    outcome = pd.read_sql(
        \"\"\"SELECT check_name, expected, actual, difference,
                  CASE passed WHEN 1 THEN 'pass' ELSE 'FAIL' END AS outcome
           FROM #result ORDER BY check_name\"\"\", cn)
display(outcome)
print(f"{len(outcome)} checks in {time.time() - started:.0f}s")

assert len(outcome) == 5, "a check did not run, which is not the same as passing"
assert (outcome["outcome"] == "pass").all(), "the loaded table does not match the build"
print(f"\\nevery check passed: {TABLE} is the table the build produced")
""")

md(f"""
---
## Part 4. The table in use

### Step 6. Rows per year, and three certificates

**What it does.** Counts rows by the year the certificate was lodged on the register, with the share
superseded and the number without a UPRN, then shows the typed columns of three certificates: the first row
of the file, and the two certificates of one building that has been assessed twice (the lowest such UPRN.
With none, only the first row shows).

**What to expect.** Fourteen years, 2013 to 2026, {c['rows']:,} rows in all. The superseded share falls from over a
third in 2013 to about 2% in 2026, because recent certificates have not yet been replaced. About a third of
each year's certificates have no UPRN. Then three rows of rating, band, floor area, dates and the UPRN.

**Why.** `HISTORIC = True` means superseded, not expired. A building's certificates share `uprn_osg`. The
dated join in step 7 chooses between them by inspection date. The extract is one file, so the year here is
the year of `created_at_parsed`, not a file.
""")
code("""
# Step 6 — rows per year of lodgement, and three certificates
with pyodbc.connect(CONN, timeout=600, autocommit=True) as cn:
    display(pd.read_sql(f\"\"\"
        SELECT YEAR(created_at_parsed) AS created_year, COUNT_BIG(*) AS rows,
               SUM(CASE WHEN historic_flag = 1 THEN 1 ELSE 0 END) AS superseded,
               CONVERT(decimal(5,1), 100.0 * SUM(CASE WHEN historic_flag = 1 THEN 1 ELSE 0 END) / COUNT_BIG(*)) AS superseded_pct,
               SUM(CASE WHEN uprn_osg IS NULL THEN 1 ELSE 0 END) AS no_uprn
        FROM {TABLE} GROUP BY YEAR(created_at_parsed) ORDER BY created_year\"\"\", cn))

    print("the first certificate of the file, and both certificates of one building assessed twice")
    display(pd.read_sql(f\"\"\"
        SELECT source_row, uprn_osg, pc_norm, inspection_date_parsed, lodgement_date_parsed, historic_flag,
               CURRENT_ENERGY_PERFORMANCE_BAND, current_energy_performance_rating_int, floor_area_int, building_emissions_num,
               primary_energy_value_int, PROPERTY_TYPE_SHORT
        FROM {TABLE}
        WHERE source_row = 1
           OR uprn_osg = (SELECT TOP (1) uprn_osg FROM {TABLE} WHERE uprn_osg IS NOT NULL
                         GROUP BY uprn_osg HAVING COUNT(*) = 2 ORDER BY uprn_osg)
        ORDER BY uprn_osg, inspection_date_parsed\"\"\", cn))
""")

md("""
### Step 7. The left join by UPRN

**What it does.** Builds a small temporary cohort with every kind of UPRN a real extract can carry and joins
it with `join_by_uprn.sql`'s logic: the certificate with the latest inspection on or before the cohort
date (a same-day tie broken in favour of the current certificate, then the latest register lodgement),
one row per cohort row, a status on each. The cohort rows take a real UPRN from the table so the cases
are live.

**What to expect.** Seven rows in, seven out: `matched` for the UPRN on its inspection date and for the same
UPRN padded to twelve digits, `no_certificate_by_date` for a date before any certificate, `uprn_not_in_epc`
for UPRN 1, `no_uprn` for empty, NULL and a non-integer.

**Why.** No cohort row may disappear, every row must say why it has no value, and the UPRN is compared as a
number, never as text, so padding does not matter. `uprn_not_in_epc` is the usual result for a real cohort:
most non-domestic buildings have no certificate. The full query with its guards and all its columns is
`docs/sql/join_by_uprn.sql`.
""")
code("""
# Step 7 — the left join by UPRN, with its statuses
with pyodbc.connect(CONN, timeout=600, autocommit=True) as cn:
    cur = cn.cursor()
    cur.execute(f\"\"\"
        DROP TABLE IF EXISTS #cohort;
        CREATE TABLE #cohort (cohort_row_id int NOT NULL PRIMARY KEY, pseudo_id int, uprn nvarchar(20), cohort_date date);
        DECLARE @u bigint = (SELECT TOP (1) uprn_osg FROM {TABLE} WHERE uprn_osg IS NOT NULL AND historic_flag = 0
                             GROUP BY uprn_osg HAVING COUNT(*) = 1 ORDER BY uprn_osg);
        DECLARE @d date = (SELECT MAX(inspection_date_parsed) FROM {TABLE} WHERE uprn_osg = @u);
        INSERT INTO #cohort VALUES
            (1, 1, CONVERT(nvarchar(20), @u), @d),
            (2, 1, RIGHT(REPLICATE(N'0', 12) + CONVERT(nvarchar(20), @u), 12), @d),
            (3, 1, CONVERT(nvarchar(20), @u), '2000-01-01'),
            (4, 2, N'1', '2030-01-01'), (5, 2, N'', '2030-01-01'), (6, 3, NULL, '2030-01-01'), (7, 3, N'x', '2030-01-01');\"\"\")
    out = pd.read_sql(f\"\"\"
        WITH cohort AS (
            SELECT c.cohort_row_id, c.pseudo_id, c.cohort_date,
                   TRY_CONVERT(bigint, NULLIF(LTRIM(RTRIM(c.uprn)), N'')) AS uprn_int
            FROM #cohort AS c),
        eligible AS (
            SELECT c.cohort_row_id, e.epc_release, e.source_row,
                   RANK() OVER (PARTITION BY c.cohort_row_id ORDER BY e.inspection_date_parsed DESC) AS rk_day,
                   RANK() OVER (PARTITION BY c.cohort_row_id ORDER BY e.inspection_date_parsed DESC,
                                CASE WHEN e.historic_flag = 0 THEN 0 ELSE 1 END, e.created_at_parsed DESC) AS rk_final
            FROM cohort AS c JOIN {TABLE} AS e ON e.uprn_osg = c.uprn_int AND e.inspection_date_parsed <= c.cohort_date),
        latest AS (
            SELECT cohort_row_id, SUM(CASE WHEN rk_day = 1 THEN 1 ELSE 0 END) AS n_day, SUM(CASE WHEN rk_final = 1 THEN 1 ELSE 0 END) AS n,
                   MIN(CASE WHEN rk_final = 1 THEN epc_release END) AS epc_release,
                   MIN(CASE WHEN rk_final = 1 THEN source_row END) AS source_row
            FROM eligible GROUP BY cohort_row_id),
        known AS (SELECT DISTINCT uprn_osg FROM {TABLE} WHERE uprn_osg IS NOT NULL)
        SELECT c.cohort_row_id, c.pseudo_id,
               CASE WHEN c.uprn_int IS NULL THEN 'no_uprn'
                    WHEN k.uprn_osg IS NULL THEN 'uprn_not_in_epc'
                    WHEN l.cohort_row_id IS NULL THEN 'no_certificate_by_date'
                    WHEN l.n > 1 THEN 'ambiguous_as_of'
                    ELSE 'matched' END AS epc_status,
               c.cohort_date,
               e.inspection_date_parsed AS epc_inspection_date, e.lodgement_date_parsed AS epc_lodgement_date,
               DATEDIFF(day, e.inspection_date_parsed, c.cohort_date) AS epc_age_days,
               e.CURRENT_ENERGY_PERFORMANCE_BAND, e.current_energy_performance_rating_int, e.PROPERTY_TYPE_SHORT,
               e.floor_area_int, e.building_emissions_num, e.primary_energy_value_int, l.n_day AS epc_tie_candidates
        FROM cohort AS c
        LEFT JOIN known AS k ON k.uprn_osg = c.uprn_int
        LEFT JOIN latest AS l ON l.cohort_row_id = c.cohort_row_id
        LEFT JOIN {TABLE} AS e ON l.n = 1 AND e.epc_release = l.epc_release AND e.source_row = l.source_row
        ORDER BY c.cohort_row_id\"\"\", cn)
display(out)
assert len(out) == 7, "a cohort row disappeared or was duplicated"
assert out.epc_status.tolist() == ["matched", "matched", "no_certificate_by_date", "uprn_not_in_epc", "no_uprn", "no_uprn", "no_uprn"]
print("seven rows in, seven out, every status as expected")
""")

EMPTY_CONN = 'CONN     = ""'
if SITE is not None:
    connection = SITE.read_text(encoding="utf-8").strip()
    if not connection or "\n" in connection:
        sys.exit(f"stopped: {SITE} must hold one line, the ODBC connection string")
    target = OUT.resolve()
    if target.is_relative_to(ROOT.resolve()) and not target.is_relative_to((ROOT / "local").resolve()):
        sys.exit(f"stopped: a notebook with a site's connection string is not written inside the repository, where it could be committed. "
                 f"Give a path under {ROOT / 'local'} or outside {ROOT}.")
    step1 = next(c for c in cells if c.cell_type == "code" and c.source.startswith("# Step 1 "))
    assert step1.source.count(EMPTY_CONN) == 1
    step1.source = step1.source.replace(EMPTY_CONN, "CONN     = " + json.dumps(connection))
nb = nbf.v4.new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
                                                "language_info": {"name": "python"}})
nbf.write(nb, OUT)
print(f"wrote {OUT} ({len(cells)} cells)")

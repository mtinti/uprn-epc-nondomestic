# Probes for the response to docs/reviews/2026-11-14-nondomestic-ingestion-plan-review.md.
# Each block calls real code of uprn-epc (commit d3d1ea4) or reads the pinned extract, and asserts
# the outcome the review reports. It writes only inside a temporary folder. It prints no address
# and no postcode value.
#
#   python3 -I <this file> <uprn-epc checkout> <extract.csv> <epc_domestic.parquet>
import sys, csv, io, re, json, random, tempfile, collections, datetime as dt
from pathlib import Path
EPC, CSV, DOM = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
sys.path.insert(0, str(EPC))
import yaml, duckdb
from epc_ingest.core import output, sources
C = collections.Counter
tmp = Path(tempfile.mkdtemp())

print("== Finding 2a. load_schema refuses a string column without an integer width")
base = {"version": "v", "table": "t", "key": ["k"], "fields": [{"name": "k", "type": "int32", "nullable": False}]}
for width in ("max", None, 8000):
    s = dict(base, fields=base["fields"] + [{"name": "LONG", "type": "string", "nullable": False, "width": width}])
    p = tmp / "schema.yaml"; p.write_text(yaml.safe_dump(s))
    try:
        output.load_schema(p); got = "accepted"
    except ValueError as e:
        got = f"ValueError: {str(e).split(': ', 1)[1]}"
    print(f"  width {width!r}: {got}")
    assert (got == "accepted") == (width == 8000)

print("== Finding 2b. load_registry refuses a member without a year")
reg = yaml.safe_load((EPC / "epc_ingest/sources.yaml").read_text())
reg["release"]["members"] = [{"file": "x/extract.csv", "sha256": "0" * 64, "bytes": 1, "rows": 1}]
p = tmp / "sources.yaml"; p.write_text(yaml.safe_dump(reg))
try:
    sources.load_registry(p, tmp); got = "accepted"
except KeyError as e:
    got = f"KeyError: {e}"
print("  one member, no year:", got); assert got == "KeyError: 'year'"

print("== Finding 2c. the notebook's column pattern drops an nvarchar(max) column")
nb = json.loads((EPC / "loader/upload_epc.ipynb").read_text())
line = next(l for c in nb["cells"] for l in "".join(c["source"]).splitlines() if l.startswith("COLUMN_LINE = "))
ns = {"re": re}; exec(line, ns)
ddl = "    [A] nvarchar(32) NOT NULL,\n    [LONG] nvarchar(max) NOT NULL,\n    [B] bigint NULL"
found = [name for name, _, _ in ns["COLUMN_LINE"].findall(ddl)]
print("  columns parsed from a three-column definition:", found); assert found == ["A", "B"]

rows = list(csv.reader(io.StringIO(open(CSV, "rb").read().decode("utf-8-sig"), newline="")))
H, data = rows[0], rows[2:]
ix = {n: i for i, n in enumerate(H)}
norm = lambda p: (p.upper().replace(" ", "").replace("\t", "")) or None
recs = [{"row": k + 1, "brn": r[ix["BUILDING_REFERENCE_NUMBER"]], "osg": r[ix["OSG_REFERENCE_NUMBER"]], "pc": norm(r[ix["POSTCODE"]]),
         "insp": dt.date.fromisoformat(r[ix["INSPECTION_DATE"]]), "hist": r[ix["HISTORIC"]] == "True",
         "created": dt.datetime.strptime(r[ix["CREATED_AT"]], "%d/%m/%Y %H:%M:%S"), "short": r[ix["PROPERTY_TYPE_SHORT"]]} for k, r in enumerate(data)]

print("== Finding 3. postcode fallback and a building whose postcode changed")
import pyarrow as pa
con = duckdb.connect()
con.register("src", pa.table({k: [r[k] for r in recs] for k in recs[0]}))
con.sql("create table e as select * from src")
multi = con.sql("select count(*) from (select brn from e where pc is not null group by 1 having count(distinct pc) > 1)").fetchone()[0]
print("  register numbers with two or more pc_norm:", multi); assert multi == 258
AS_OF = "DATE '2026-09-30'"
RANKED = """row_number() over (partition by {part} order by insp desc, case when hist then 1 else 0 end, created desc) rn"""
latest_all = f"select brn, pc from (select brn, pc, {RANKED.format(part='brn')} from e where insp <= {AS_OF}) where rn = 1"
inherited = f"select brn, pc from (select brn, pc, {RANKED.format(part='brn, pc')} from e where pc is not null and insp <= {AS_OF}) where rn = 1"
stale = con.sql(f"select count(*) from ({inherited}) i join ({latest_all}) l using (brn) where i.pc is distinct from l.pc").fetchone()[0]
print("  as of 30 September 2026, building and postcode pairs the inherited selection returns although the building's latest certificate has another postcode:", stale)
assert stale == 262
fixed = con.sql(f"select count(*) from ({latest_all}) l join (select distinct brn, pc from e) c using (brn, pc)").fetchone()[0]
print("  pairs returned when the latest certificate is chosen first and its postcode compared after:", fixed, "of", con.sql("select count(distinct brn) from e").fetchone()[0], "buildings")
print("  uprn-epc has the same query. Register numbers with two or more pc_norm in epc_domestic 2026Q2:",
      con.sql(f"select count(*) from (select uprn_sepcr from read_parquet('{DOM}') where pc_norm is not null group by 1 having count(distinct pc_norm) > 1)").fetchone()[0])

print("== Finding 4. the cohort side must normalise like the source side")
con.sql("create table t(v varchar)"); con.execute("insert into t values (?), (?), (?)", ["EH1\t1AA", "EH1 1AA", " \teh1 1aa "])
for label, expr in [("spaces only, as uprn-epc's query", "nullif(upper(replace(v, ' ', '')), '')"), ("spaces and tabs", "nullif(upper(replace(replace(v, ' ', ''), chr(9), '')), '')")]:
    keys = [x[0] for x in con.sql(f"select {expr} from t").fetchall()]
    print(f"  cohort rule {label}: matches source key EH11AA in {sum(k == norm('EH1\t1AA') for k in keys)} of 3")
other = sum(1 for r in recs if r["pc"] and not re.fullmatch(r"[A-Z0-9]+", r["pc"]))
print("  pc_norm values in the extract with a character other than A to Z and 0 to 9:", other); assert other == 0

print("== Finding 5. where 'Data removed' occurs, against the typed copies the plan named")
for n in ["FLOOR_AREA", "CURRENT_ENERGY_PERFORMANCE_RATING", "BUILDING_EMISSIONS", "PRIMARY_ENERGY_VALUE", "POTENTIAL_ENERGY_PERFORMANCE_RATING", "ASSET_RATING"]:
    v = [r[ix[n]] for r in data]
    print(f"  {n}: 'Data removed' {sum(c == 'Data removed' for c in v)}, neither a number nor 'Data removed' {sum(1 for c in v if c != 'Data removed' and not re.fullmatch(r'-?[0-9]+([.][0-9]+)?', c))}")

print("== Finding 6. UPRNs in both registers, by type, under an explicit rule")
dom = {u for (u,) in duckdb.sql(f"select distinct uprn_osg from read_parquet('{DOM}') where uprn_osg is not null").fetchall()}
def breakdown(records):
    last, anyc, cur = {}, collections.defaultdict(set), {}
    for r in records:
        if r["osg"] and int(r["osg"]) in dom:
            u = int(r["osg"]); last[u] = r["short"]; anyc[u].add(r["short"])
            if not r["hist"]: cur[u] = r["short"]
    return len(last), C(last.values()), C(s for v in anyc.values() for s in v), C(cur.get(u, "no current certificate") for u in last)
n, last, anyc, cur = breakdown(recs)
print("  shared UPRNs:", n); assert n == 2005
print("  Hospitals/Care Home: last row in file", last["Hospitals/Care Home"], "| any certificate", anyc["Hospitals/Care Home"], "| current certificate", cur["Hospitals/Care Home"])
assert (last["Hospitals/Care Home"], anyc["Hospitals/Care Home"], cur["Hospitals/Care Home"]) == (82, 84, 46)
print("  by type of the current certificate:", cur.most_common())
shuffled = recs[:]; random.Random(1).shuffle(shuffled)
n2, last2, anyc2, cur2 = breakdown(shuffled)
print("  after shuffling the rows: current-certificate breakdown unchanged", cur2 == cur, "| any-certificate unchanged", anyc2 == anyc, "| last-row breakdown unchanged", last2 == last)
assert cur2 == cur and anyc2 == anyc
types = collections.defaultdict(set)
for r in recs:
    if r["osg"]: types[r["osg"]].add(r["short"])
print("  UPRNs with two or more PROPERTY_TYPE_SHORT over their certificates:", sum(len(v) > 1 for v in types.values()))

print("== Shared UPRNs with no current non-domestic certificate: which register lodged last")
nd_last = {}
for r in recs:
    if r["osg"] and int(r["osg"]) in dom:
        u = int(r["osg"]); nd_last[u] = max(nd_last.get(u, r["created"]), r["created"])
no_cur = [u for u in nd_last if u not in {int(r["osg"]) for r in recs if r["osg"] and not r["hist"]}]
con.register("nc", pa.table({"u": no_cur, "nd_last": [nd_last[u] for u in no_cur]}))
later, cur_dom = con.sql(f"""select count(*) filter (d_last > nd_last), count(*) filter (d_cur > 0) from nc join
    (select uprn_osg, max(created_at_parsed) d_last, sum(case when historic_flag then 0 else 1 end) d_cur from read_parquet('{DOM}') group by 1) d on d.uprn_osg = nc.u""").fetchone()
print("  shared UPRNs with no current non-domestic certificate:", len(no_cur), "| a domestic certificate was lodged after the last non-domestic one:", later, "| the UPRN has a current domestic certificate:", cur_dom)

print("== Same-day pairs by register number")
g = collections.defaultdict(list)
for r in recs: g[(r["brn"], r["insp"])].append(r)
pairs = [v for v in g.values() if len(v) > 1]
print("  register number and inspection day with two certificates:", len(pairs), "| with a UPRN:", sum(bool(v[0]["osg"]) for v in pairs),
      "| current certificates per pair:", sorted(C(sum(not x["hist"] for x in v) for v in pairs).items()))
print("all assertions passed")

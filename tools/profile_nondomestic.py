# Profile of the non-domestic EPC extract, written for docs/EPC_NonDomestic_Plan.md (14 November 2026).
# Every number the plan quotes comes from this script. It reads the files and writes nothing.
# The CSV is read with Python's csv module, so an empty cell stays the empty string.
# It prints no address and no postcode value, only counts and shapes.
#
#   python3 -I tools/profile_nondomestic.py <extract.csv> <epc_domestic.parquet> <DataZone2011_lookup.csv> <SG_SIMD_2012.dbf>
#
# The last three arguments are files of the uprn-epc project: its built table and its two pinned data zone lists.
import sys, csv, io, collections, re, datetime as dt, struct, hashlib
path, dom, dz11, dz01 = sys.argv[1:5]
raw_bytes = open(path, 'rb').read()
print("bytes", len(raw_bytes), "sha256", hashlib.sha256(raw_bytes).hexdigest())
print("byte order mark", raw_bytes[:3] == b'\xef\xbb\xbf', "| CRLF", raw_bytes.count(b'\r\n'), "| LF", raw_bytes.count(b'\n'), "| CR without LF", raw_bytes.count(b'\r') - raw_bytes.count(b'\r\n'))
text = raw_bytes.decode('utf-8-sig')  # strict: an undecodable byte raises
rows = list(csv.reader(io.StringIO(text, newline='')))
H, LABELS, data = rows[0], rows[1], rows[2:]
ix = {n: i for i, n in enumerate(H)}
col = lambda n: [r[ix[n]] for r in data]
C = collections.Counter
print("columns", len(H), "| label row fields", len(LABELS), "| fields per data row", dict(C(len(r) for r in data)))
print("U+FFFD in the two header rows", sum('\ufffd' in c for c in H + LABELS))
print("\nname | label | empty | distinct | longest | cells with edge whitespace")
for n, lab in zip(H, LABELS):
    v = col(n)
    print(f"  {n} | {lab} | {sum(c == '' for c in v)} | {len(set(v))} | {max(map(len, v))} | {sum(c != c.strip() for c in v)}")
print("\nvalue lists")
for n in ["HISTORIC", "PROPERTY_TYPE_SHORT", "PROPERTY_TYPE", "TRANSACTION_TYPE", "CURRENT_ENERGY_PERFORMANCE_BAND", "POTENTIAL_ENERGY_PERFORMANCE_BAND", "NEW_BUILD_ENERGY_PERFORMANCE_BAND", "ASSET_RATING_BAND", "MEETS_2002_STANDARD", "RENEWABLE_SOURCES", "ELECTRICITY_SOURCE", "BUILDING_ENVIRONMENT", "MAIN_HEATING_FUEL"]:
    print(" ", n, C(col(n)).most_common())
print("'Data removed' cells by column", {n: sum(c == 'Data removed' for c in col(n)) for n in H if any(c == 'Data removed' for c in col(n))})
print("number columns: shapes with digits folded to 9, then smallest and largest")
for n in ["FLOOR_AREA", "CURRENT_ENERGY_PERFORMANCE_RATING", "POTENTIAL_ENERGY_PERFORMANCE_RATING", "NEW_BUILD_ENERGY_PERFORMANCE_RATING", "ASSET_RATING", "BUILDING_EMISSIONS", "PRIMARY_ENERGY_VALUE", "APPROXIMATE_ENERGY_USE", "TARGET_EMISSIONS"]:
    nums = [float(c) for c in col(n) if re.fullmatch(r'-?\d+(\.\d+)?', c)]
    print(" ", n, C(re.sub(r'\d+', '9', c) for c in col(n)).most_common(), min(nums), max(nums), "| most decimals", max(len((c.split('.') + [''])[1]) for c in col(n) if c != 'Data removed'))
print("date shapes", {n: C(re.sub(r'\d', '9', c) for c in col(n)).most_common() for n in ["INSPECTION_DATE", "LODGEMENT_DATE", "CREATED_AT"]})
rrn_ = col('REPORT_REFERENCE_NUMBER')
print("RRN: empty", sum(c == '' for c in rrn_), "| distinct non-empty", len({c for c in rrn_ if c}), "| repeated non-empty", sum(1 for c in rrn_ if c) - len({c for c in rrn_ if c}), "| shapes", C(re.sub(r'\d', '9', c) for c in rrn_).most_common())
_u, _b = collections.defaultdict(set), collections.defaultdict(set)
for b_, o_ in zip(col('BUILDING_REFERENCE_NUMBER'), col('OSG_REFERENCE_NUMBER')):
    if o_: _u[o_].add(b_); _b[b_].add(o_)
print("distinct UPRN", len(_u), "| UPRN with 2+ register numbers", sum(len(s) > 1 for s in _u.values()), "| register number with 2+ UPRN", sum(len(s) > 1 for s in _b.values()))
_cur = C(b_ for b_, h_ in zip(col('BUILDING_REFERENCE_NUMBER'), col('HISTORIC')) if h_ == 'False')
print("current certificates per register number", sorted(C(_cur.values()).items()))
_curu = C(o_ for o_, h_ in zip(col('OSG_REFERENCE_NUMBER'), col('HISTORIC')) if h_ == 'False' and o_)
print("current certificates per UPRN", sorted(C(_curu.values()).items()), "| UPRN with none", len(_u) - len(_curu))
print("rows", len(data), "duplicate whole rows", len(data) - len(set(map(tuple, data))))
# characters
ctrl, nonascii, fffd = C(), C(), []
for k, r in enumerate(data):
    for i, c in enumerate(r):
        if any(ord(ch) < 32 or ch in '\x7f\x1f\x00' for ch in c): ctrl[(H[i], tuple(sorted({hex(ord(ch)) for ch in c if ord(ch) < 32})))] += 1
        if any(ord(ch) > 127 for ch in c): nonascii[H[i]] += 1
        if '�' in c: fffd.append((k + 1, H[i], c[max(0, c.index('�') - 25): c.index('�') + 25] if H[i] not in ('ADDRESS1', 'ADDRESS2') else '<address cell, not printed>'))
print("control characters by column", dict(ctrl))
print("non-ASCII cells by column", dict(nonascii))
print("astral characters (two UTF-16 units)", sum(1 for r in data for c in r for ch in c if ord(ch) > 0xFFFF))
print("U+FFFD data cells", fffd)
allch = C(ch for r in data for c in r for ch in c if ord(ch) > 127)
print("non-ASCII characters", [(hex(ord(k)), v) for k, v in allch.most_common(15)])
# long text
L = sorted((len(c) for c in col('IMPROVEMENT_RECOMMENDATIONS')), reverse=True)
print("IMPROVEMENT_RECOMMENDATIONS: longest", L[:5], "over 4000:", sum(x > 4000 for x in L), "over 3330:", sum(x > 3330 for x in L), "over 2000:", sum(x > 2000 for x in L))
print("  trailing space cells", sum(c.endswith(' ') for c in col('IMPROVEMENT_RECOMMENDATIONS')), "leading", sum(c.startswith(' ') for c in col('IMPROVEMENT_RECOMMENDATIONS')))
print("  measures per cell (split on |): max", max(c.count('|') + 1 for c in col('IMPROVEMENT_RECOMMENDATIONS') if c))
print("longest row in characters", max(sum(map(len, r)) for r in data))
# UPRN
osg = col('OSG_REFERENCE_NUMBER'); lod = col('LODGEMENT_DATE')
by = collections.defaultdict(lambda: [0, 0])
for o, l in zip(osg, lod): by[l[:4]][0] += 1; by[l[:4]][1] += (o == '')
print("OSG empty: total", sum(o == '' for o in osg), "by lodgement year %", {y: round(100 * e / n, 1) for y, (n, e) in sorted(by.items())})
print("OSG digit lengths", sorted(C(len(o) for o in osg if o).items()), "leading zero", sum(o.startswith('0') for o in osg if o), "range", min(int(o) for o in osg if o), max(int(o) for o in osg if o))
print("OSG 8-digit: first three digits", C(o[:3] for o in osg if len(o) == 8).most_common(5))
brn = col('BUILDING_REFERENCE_NUMBER'); print("BRN range", min(brn), max(brn))
hist = col('HISTORIC')
cur_by_brn = C(b for b, h in zip(brn, hist) if h == 'False'); allb = set(brn)
nocur = allb - set(cur_by_brn)
print("BRN: distinct", len(allb), "with no current certificate", len(nocur), "of which with a UPRN", len({b for b, o in zip(brn, osg) if b in nocur and o}))
u2b = collections.defaultdict(set)
for b, o in zip(brn, osg):
    if o: u2b[o].add(b)
b_with = {b for s in u2b.values() for b in s}
print("BRN that has a UPRN in one row and none in another", len({b for b, o in zip(brn, osg) if o == '' and b in b_with}))
# certificates per building
print("certificates per BRN", sorted(C(C(brn).values()).items()))
# dates
ins = [dt.date.fromisoformat(x) for x in col('INSPECTION_DATE')]; lo = [dt.date.fromisoformat(x) for x in lod]
cr = [dt.datetime.strptime(x, '%d/%m/%Y %H:%M:%S') for x in col('CREATED_AT')]
print("CREATED_AT range", min(cr), max(cr), "| inspection range", min(ins), max(ins), "| lodgement", min(lo), max(lo))
print("CREATED_AT date equals LODGEMENT_DATE", sum(c.date() == l for c, l in zip(cr, lo)), "differs", sum(c.date() != l for c, l in zip(cr, lo)), "max abs days", max(abs((c.date() - l).days) for c, l in zip(cr, lo)))
lag = [(l - i).days for i, l in zip(ins, lo)]
b = C('before inspection' if x < 0 else 'same day' if x == 0 else '1-7' if x <= 7 else '8-30' if x <= 30 else '31-365' if x <= 365 else 'over a year' for x in lag)
print("lodgement minus inspection, days", dict(b), "median", sorted(lag)[len(lag) // 2], "min", min(lag), "max", max(lag))
print("inspection after extract date 2026-10-21", sum(i > dt.date(2026, 10, 21) for i in ins), "inspection before 2012", sum(i.year < 2012 for i in ins))
print("rows in file order by lodgement date? inversions", sum(lo[k] < lo[k - 1] for k in range(1, len(lo))), "by CREATED_AT", sum(cr[k] < cr[k - 1] for k in range(1, len(cr))))
print("first rows CREATED_AT", [str(x) for x in cr[:3]], "last", [str(x) for x in cr[-3:]])
# ties
g = collections.defaultdict(list)
for k, (o, i) in enumerate(zip(osg, ins)):
    if o: g[(o, i)].append(k)
ties = {k: v for k, v in g.items() if len(v) > 1}
print("UPRN and inspection day with 2+ certificates", len(ties), "sizes", C(len(v) for v in ties.values()), "current among them", [sum(hist[x] == 'False' for x in v) for v in ties.values()])
latest = {}
for (o, i), v in g.items():
    if o not in latest or i > latest[o][0]: latest[o] = (i, v)
print("UPRNs whose latest inspection day carries 2+ certificates", sum(len(v) > 1 for _, v in latest.values()))
print("UPRNs where the current certificate is not the latest inspected", sum(1 for o, (i, v) in latest.items() if not any(hist[x] == 'False' for x in v)), "of", len(latest))
# numbers
pot = col('POTENTIAL_ENERGY_PERFORMANCE_RATING')
print("POTENTIAL rating fractional part", C((p.split('.') + [''])[1] for p in pot if p != 'Data removed').most_common(5))
cur = col('CURRENT_ENERGY_PERFORMANCE_RATING'); ber = col('BUILDING_EMISSIONS')
from decimal import Decimal, ROUND_HALF_UP, ROUND_HALF_EVEN
d = [int(c) - int(Decimal(b).quantize(Decimal(1), rounding=ROUND_HALF_UP)) for c, b in zip(cur, ber)]
print("rating minus BER rounded half up: zero", sum(x == 0 for x in d), "abs 1", sum(abs(x) == 1 for x in d), "more", sum(abs(x) > 1 for x in d))
print("'-0' cells", {n: sum(c in ('-0', '-0.0', '-0.00') for c in col(n)) for n in H if any(c in ('-0', '-0.0', '-0.00') for c in col(n))})
print("leading zeros or plus signs in number columns", {n: sum(bool(re.match(r'^-?0\d|^\+', c)) for c in col(n)) for n in ['FLOOR_AREA', 'CURRENT_ENERGY_PERFORMANCE_RATING', 'NEW_BUILD_ENERGY_PERFORMANCE_RATING', 'ASSET_RATING', 'PRIMARY_ENERGY_VALUE', 'APPROXIMATE_ENERGY_USE', 'BUILDING_EMISSIONS', 'TARGET_EMISSIONS']})
fa = [int(x) for x in col('FLOOR_AREA')]
print("FLOOR_AREA: zero", sum(x == 0 for x in fa), "under 15", sum(x < 15 for x in fa), "over 1500", sum(x > 1500 for x in fa), "over 50000", sum(x > 50000 for x in fa))
band = col('CURRENT_ENERGY_PERFORMANCE_BAND')
cut = lambda k: 'Carbon Neu' if k < 0 else next(b for hi, b in [(7, 'A+'), (15, 'A'), (22, 'B+'), (30, 'B'), (37, 'C+'), (45, 'C'), (52, 'D+'), (60, 'D'), (70, 'E+'), (80, 'E'), (90, 'F+'), (100, 'F'), (10**9, 'G')] if k <= hi)
bad = [(c, b) for c, b in zip(cur, band) if cut(int(c)) != b]
print("band disagrees with the cut of the rating", len(bad), C(bad).most_common(6))
print("band text values", sorted(set(band)), "| potential", sorted(set(col('POTENTIAL_ENERGY_PERFORMANCE_BAND'))))
print("Data removed pairs: potential rating without band or reverse", sum((a == 'Data removed') != (b == 'Data removed') for a, b in zip(pot, col('POTENTIAL_ENERGY_PERFORMANCE_BAND'))), "asset", sum((a == 'Data removed') != (b == 'Data removed') for a, b in zip(col('ASSET_RATING'), col('ASSET_RATING_BAND'))))
print("Data removed by lodgement year (asset)", sorted(C(l[:4] for l, a in zip(lod, col('ASSET_RATING')) if a == 'Data removed').items()))
print("MEETS_2002_STANDARD empty by lodgement before/after 2016-03-20", C((l < dt.date(2016, 3, 20), m) for l, m in zip(lo, col('MEETS_2002_STANDARD'))))
# geography
pc = col('POSTCODE')
norm = [re.sub(r'\s', '', p).upper() for p in pc]
print("postcode: cells with a tab", sum('\t' in p for p in pc), "edge whitespace", sum(p != p.strip() for p in pc), "inner double space", sum('  ' in p.strip() for p in pc), "lower case", sum(p != p.upper() for p in pc))
print("pc_norm length", sorted(C(map(len, norm)).items()), "not a full postcode shape", sum(not re.fullmatch(r'[A-Z]{1,2}\d[A-Z\d]?\d[A-Z]{2}', n) for n in norm))
scot = ('AB', 'DD', 'DG', 'EH', 'FK', 'G', 'HS', 'IV', 'KA', 'KW', 'KY', 'ML', 'PA', 'PH', 'TD', 'ZE')
area = [re.match(r'[A-Z]+', n).group(0) if re.match(r'[A-Z]+', n) else '' for n in norm]
print("postcode areas outside Scotland", C(a for a in area if a not in scot).most_common(12))
la = col('LOCAL_AUTHORITY')
print("LOCAL_AUTHORITY not 00Q/00R and not empty", C(x for x in la if x and not x.startswith(('00Q', '00R'))), "postcode areas of those rows", C(a for a, x in zip(area, la) if x and not x.startswith(('00Q', '00R'))))
print("geography block empty together", C((la_ == '', dz == '', c == '', d11 == '') for la_, dz, c, d11 in zip(la, col('DATA_ZONE'), col('CONSTITUENCY'), col('DATA_ZONE_2011'))).most_common(6))
z11 = set()
for r in csv.DictReader(open(dz11, encoding='cp1252')): z11.add(r['DZ2011_Code'])
raw = open(dz01, 'rb').read(); nrec, hlen, rlen = struct.unpack('<IHH', raw[4:12])
fields, off, p = [], 1, 32
while raw[p] != 0x0D:
    nm = raw[p:p + 11].split(b'\0')[0].decode(); ln = raw[p + 16]; fields.append((nm, off, ln)); off += ln; p += 32
f = next(x for x in fields if x[0] == 'DataZone'); z01 = {raw[hlen + k * rlen + f[1]: hlen + k * rlen + f[1] + f[2]].decode().strip() for k in range(nrec)}
print("pinned lists: 2011", len(z11), "2001", len(z01))
for name, zs in [('DATA_ZONE', z01), ('DATA_ZONE_2011', z11)]:
    st = C()
    for v in col(name):
        m = re.match(r'^(S01\d{6})( |$)', v)
        st['empty' if v == '' else ('code' if m.group(1) in zs else 'unknown_code') if m else 'not_a_datazone'] += 1
    print(name, dict(st), "examples of other shapes", C(v[:14] for v in col(name) if v and not re.match(r'^S01\d{6}( |$)', v)).most_common(4))
print("DATA_ZONE codes found in the 2011 list instead", sum(1 for v in col('DATA_ZONE') if (m := re.match(r'^(S01\d{6})( |$)', v)) and m.group(1) not in z01 and m.group(1) in z11))
# vocabularies and overlap
print("PROPERTY_TYPE_SHORT by current/all", sorted(C(col('PROPERTY_TYPE_SHORT')).items(), key=lambda x: -x[1])[:5])
resid = {'Hospitals/Care Home', 'Residential space', 'Residential school', 'Secure Residential Institution', 'Universities/college', 'Hotel'}
for s in sorted(resid):
    k = [j for j, v in enumerate(col('PROPERTY_TYPE_SHORT')) if v == s]
    print("  ", s, "rows", len(k), "current", sum(hist[j] == 'False' for j in k), "current with UPRN", sum(hist[j] == 'False' and osg[j] != '' for j in k), "distinct UPRN", len({osg[j] for j in k if osg[j]}))
print("PROPERTY_TYPE to PROPERTY_TYPE_SHORT is many to one", all(len(s) == 1 for s in (lambda m: [m.setdefault(a, set()).add(b) or m[a] for a, b in zip(col('PROPERTY_TYPE'), col('PROPERTY_TYPE_SHORT'))])({})))
import duckdb
# UPRNs in both registers. A UPRN's type is that of its current non-domestic certificate, so the
# result does not depend on the order of the rows. A UPRN with no current certificate is counted apart.
dom_uprn = {u for (u,) in duckdb.sql(f"select distinct uprn_osg from read_parquet('{dom}') where uprn_osg is not null").fetchall()}
short = col('PROPERTY_TYPE_SHORT')
shared = {int(o) for o in osg if o and int(o) in dom_uprn}
cur_type = {int(o): s for o, s, h in zip(osg, short, hist) if o and h == 'False' and int(o) in shared}
any_type = collections.defaultdict(set)
for o, s in zip(osg, short):
    if o and int(o) in shared: any_type[int(o)].add(s)
print("UPRNs in both registers", len(shared))
print("  by type of the current non-domestic certificate", C(cur_type.get(u, 'no current certificate') for u in shared).most_common())
print("  with any certificate of the type", C(s for v in any_type.values() for s in v).most_common(8))
types = collections.defaultdict(set)
for o, s in zip(osg, short):
    if o: types[o].add(s)
print("UPRNs with two or more PROPERTY_TYPE_SHORT over their certificates", sum(len(v) > 1 for v in types.values()))
# Postcode changes and same-day pairs by register number, for the postcode join.
pcs = collections.defaultdict(set)
for b, n in zip(brn, norm):
    if n: pcs[b].add(n.replace('\t', ''))
print("register numbers with two or more pc_norm", sum(len(v) > 1 for v in pcs.values()))
gb = collections.defaultdict(list)
for k, (b, i) in enumerate(zip(brn, ins)): gb[(b, i)].append(k)
pairs = [v for v in gb.values() if len(v) > 1]
print("register number and inspection day with 2+ certificates", len(pairs), "| with a UPRN", sum(bool(osg[v[0]]) for v in pairs), "| current certificates per pair", sorted(C(sum(hist[x] == 'False' for x in v) for v in pairs).items()))

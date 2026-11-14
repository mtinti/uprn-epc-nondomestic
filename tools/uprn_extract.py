"""Write every distinct non-empty UPRN of the extract with its length, post town, local authority
code and postcode, for tools/uprn_check_os_open_uprn.py. The output holds postcodes: keep it out
of the repository.

    python3 -P tools/uprn_extract.py <extract.csv> <out.csv>
"""
import csv, sys
csv.field_size_limit(10_000_000)
src, out = sys.argv[1], sys.argv[2]
seen = {}
with open(src, encoding="utf-8-sig", newline="") as fh:
    r = csv.reader(fh)
    hdr = next(r); next(r)
    iu, it, ila, ipc = hdr.index("OSG_REFERENCE_NUMBER"), hdr.index("POST_TOWN"), hdr.index("LOCAL_AUTHORITY"), hdr.index("POSTCODE")
    for row in r:
        u = row[iu].strip()
        if u and u not in seen:
            seen[u] = (row[it].strip(), row[ila].strip(), row[ipc].strip())
with open(out, "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["uprn", "len", "town", "la", "postcode"])
    for u, (t, la, pc) in seen.items():
        w.writerow([u, len(u), t, la, pc])
print(len(seen))

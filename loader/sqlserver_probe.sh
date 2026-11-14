#!/bin/sh
# Run the generated import and check scripts against a throwaway SQL Server 2022 container, then
# probe what the Python tests cannot: that SQL Server renders a date, a timestamp, a bit, a bigint
# and a decimal(19,4) exactly as Python did, that an empty published cell is the empty string and
# an empty derived cell is NULL, that the cells this extract is awkward for arrived unchanged (a
# cell over 4,000 characters, a tab, a trailing space, the replacement character), that the digest
# fails when one of them is changed, and that the three join queries return their columns and
# statuses. Usage: sh loader/sqlserver_probe.sh [results_dir]
# (needs docker; starts the container if absent). Default results dir: results/.
set -eu
cd "$(dirname "$0")/.."
R="${1:-results}"
T=epc_nondomestic
PW='Epc_test_Pw0rd!'
C=epc_nd_mssql
if ! docker ps --format '{{.Names}}' | grep -qx $C; then
  docker start $C >/dev/null 2>&1 || docker run --platform linux/amd64 -d --name $C -e ACCEPT_EULA=Y -e "MSSQL_SA_PASSWORD=$PW" -e MSSQL_PID=Developer \
    -e MSSQL_MEMORY_LIMIT_MB=4096 mcr.microsoft.com/mssql/server:2022-latest >/dev/null
fi
SQL="docker exec -i $C /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P $PW -C -b -t 0"
for i in $(seq 1 90); do $SQL -Q "SELECT 1" >/dev/null 2>&1 && break; sleep 2; done
$SQL -Q "IF DB_ID('epc') IS NULL CREATE DATABASE epc"
ROWS=$(python3 -c "import json;print(json.load(open('$R/manifest.json'))['csv']['rows'])")
TOTAL=$(python3 -c "import json;print(json.load(open('$R/manifest.json'))['csv']['digest']['total'])")
W=$(mktemp -d)
# SQL Server on Linux does not support CODEPAGE, so the container cannot read the UTF-8 file
# as the generated script does on Windows. The probe converts the CSV to UTF-16LE with a byte
# order mark and imports it as widechar; everything else in the script is unchanged. The
# Windows load uses the generated script as it is.
gunzip -c "$R/$T.csv.gz" | { printf '\377\376'; iconv -f UTF-8 -t UTF-16LE; } > "$W/$T.csv"
sed -e "s#/path/to/$T.csv#/tmp/epc/$T.csv#" \
    -e "s#CODEPAGE = '65001'#DATAFILETYPE = 'widechar'#" \
    -e "s#ROWTERMINATOR = '0x0a'#ROWTERMINATOR = '\\\\n'#" docs/sql/import_csv.sql > "$W/import.sql"
grep -q "DATAFILETYPE = 'widechar'" "$W/import.sql" || { echo "the import script was not adapted for Linux"; exit 1; }
sed "s#(N'$T', 0, 0, 1)#(N'$T', $ROWS, $TOTAL, 1)#" docs/sql/check_loaded_digest.sql > "$W/check.sql"
grep -q "(N'$T', $ROWS, $TOTAL, 1)" "$W/check.sql" || { echo "the check script was not given the expected values"; exit 1; }
docker exec $C mkdir -p /tmp/epc
docker cp "$W/$T.csv" $C:/tmp/epc/$T.csv
docker cp "$W/import.sql" $C:/tmp/epc/import.sql
docker cp "$W/check.sql" $C:/tmp/epc/check.sql
echo "== import ($ROWS rows)"
START=$(date +%s)
$SQL -d epc -i /tmp/epc/import.sql
echo "import took $(( $(date +%s) - START ))s"
echo "== check_loaded_digest (expected rows $ROWS, total $TOTAL)"
START=$(date +%s)
$SQL -d epc -i /tmp/epc/check.sql -W -s '|'
echo "check took $(( $(date +%s) - START ))s"

echo "== probe: SQL rendering of chosen cells against the CSV text"
gunzip -c "$R/$T.csv.gz" > "$W/${T}_utf8.csv"
# No address or postcode column is among them: the files of this probe hold none.
python3 - "$W/${T}_utf8.csv" > "$W/probe_expected.txt" <<'PY'
import csv, sys
csv.field_size_limit(1 << 24)
cols = ("uprn_osg", "lodgement_date_parsed", "created_at_parsed", "historic_flag", "building_emissions_num",
        "potential_energy_performance_rating_num", "floor_area_int", "current_energy_performance_rating_int", "rrn",
        "OSG_REFERENCE_NUMBER", "datazone_2001", "MEETS_2002_STANDARD", "CURRENT_ENERGY_PERFORMANCE_BAND")
want = {"first": lambda r: r["source_row"] == "1", "second": lambda r: r["source_row"] == "2",
        "empty UPRN": lambda r: r["OSG_REFERENCE_NUMBER"] == "", "empty RRN": lambda r: r["rrn"] == "",
        "Data removed": lambda r: r["POTENTIAL_ENERGY_PERFORMANCE_RATING"] == "Data removed",
        "negative rating": lambda r: r["current_energy_performance_rating_int"].startswith("-"),
        "cut band": lambda r: r["CURRENT_ENERGY_PERFORMANCE_BAND"] == "Carbon Neu"}
picked = {}
with open(sys.argv[1], newline="", encoding="utf-8") as fh:
    for row in csv.DictReader(fh):
        for name, test in want.items():
            if name not in picked and test(row):
                picked[name] = row
        if len(picked) == len(want):
            break
assert len(picked) == len(want), sorted(set(want) - set(picked))
for row in {r["source_row"]: r for r in picked.values()}.values():
    for col in cols:
        print(f"{row['source_row']}|{col}|{row[col]}")
PY
KEYS=$(python3 -c "print(', '.join(sorted({l.split('|')[0] for l in open('$W/probe_expected.txt')}, key=int)))")
$SQL -d epc -W -h -1 -s '|' -Q "SET NOCOUNT ON; SELECT source_row, c.col, ISNULL(c.val, '') FROM $T CROSS APPLY (VALUES
 ('uprn_osg', CONVERT(nvarchar(40), uprn_osg)), ('lodgement_date_parsed', CONVERT(nvarchar(40), lodgement_date_parsed, 23)),
 ('created_at_parsed', CONVERT(nvarchar(40), created_at_parsed, 120)), ('historic_flag', CONVERT(nvarchar(40), historic_flag)),
 ('building_emissions_num', CONVERT(nvarchar(40), building_emissions_num)), ('potential_energy_performance_rating_num', CONVERT(nvarchar(40), potential_energy_performance_rating_num)),
 ('floor_area_int', CONVERT(nvarchar(40), floor_area_int)), ('current_energy_performance_rating_int', CONVERT(nvarchar(40), current_energy_performance_rating_int)),
 ('rrn', CONVERT(nvarchar(40), rrn)), ('OSG_REFERENCE_NUMBER', CONVERT(nvarchar(40), OSG_REFERENCE_NUMBER)), ('datazone_2001', CONVERT(nvarchar(40), datazone_2001)),
 ('MEETS_2002_STANDARD', CONVERT(nvarchar(40), MEETS_2002_STANDARD)), ('CURRENT_ENERGY_PERFORMANCE_BAND', CONVERT(nvarchar(40), CURRENT_ENERGY_PERFORMANCE_BAND))) c(col, val)
 WHERE source_row IN ($KEYS) ORDER BY source_row, c.col" | sed 's/ *|/|/g; s/ *$//' | grep -v '^$' > "$W/probe_actual.txt" || true
sort "$W/probe_expected.txt" > "$W/e.txt"; sort "$W/probe_actual.txt" > "$W/a.txt"
if diff "$W/e.txt" "$W/a.txt"; then echo "rendering: SQL Server text equals the CSV text for $(wc -l < "$W/e.txt" | tr -d ' ') cells"; else echo "rendering: DIFFERENCES"; exit 1; fi

echo "== probe: empty against NULL, and the awkward cells"
# Characters are tested under a binary collation and by code point, never with = or LEN:
# SQL Server ignores trailing spaces in = and in LEN, and a linguistic collation gives the
# replacement character no weight. DATALENGTH counts bytes, two per character here.
B="COLLATE Latin1_General_100_BIN2"
$SQL -d epc -W -h -1 -s '|' -Q "SET NOCOUNT ON;
SELECT 'address2_empty_not_null', COUNT(*) FROM $T WHERE DATALENGTH(ADDRESS2) = 0 AND ADDRESS2 IS NOT NULL
UNION ALL SELECT 'published_null', COUNT(*) FROM $T WHERE ADDRESS2 IS NULL OR OSG_REFERENCE_NUMBER IS NULL OR MEETS_2002_STANDARD IS NULL OR IMPROVEMENT_RECOMMENDATIONS IS NULL
UNION ALL SELECT 'osg_text_empty', COUNT(*) FROM $T WHERE DATALENGTH(OSG_REFERENCE_NUMBER) = 0
UNION ALL SELECT 'uprn_osg_null', COUNT(*) FROM $T WHERE uprn_osg IS NULL
UNION ALL SELECT 'rrn_null', COUNT(*) FROM $T WHERE rrn IS NULL
UNION ALL SELECT 'rrn_text_empty', COUNT(*) FROM $T WHERE DATALENGTH(REPORT_REFERENCE_NUMBER) = 0
UNION ALL SELECT 'uprn_sepcr_null', COUNT(*) FROM $T WHERE uprn_sepcr IS NULL
UNION ALL SELECT 'historic_mismatch', COUNT(*) FROM $T WHERE CASE WHEN historic_flag = 1 THEN N'True' ELSE N'False' END <> HISTORIC $B
UNION ALL SELECT 'floor_area_mismatch', COUNT(*) FROM $T WHERE CONVERT(int, FLOOR_AREA) <> floor_area_int
UNION ALL SELECT 'data_removed_potential', COUNT(*) FROM $T WHERE POTENTIAL_ENERGY_PERFORMANCE_RATING = N'Data removed' $B
UNION ALL SELECT 'potential_num_null', COUNT(*) FROM $T WHERE potential_energy_performance_rating_num IS NULL
UNION ALL SELECT 'potential_num_null_without_data_removed', COUNT(*) FROM $T WHERE potential_energy_performance_rating_num IS NULL AND POTENTIAL_ENERGY_PERFORMANCE_RATING <> N'Data removed' $B
UNION ALL SELECT 'data_removed_asset', COUNT(*) FROM $T WHERE ASSET_RATING = N'Data removed' $B
UNION ALL SELECT 'carbon_neu', COUNT(*) FROM $T WHERE CURRENT_ENERGY_PERFORMANCE_BAND = N'Carbon Neu' $B AND DATALENGTH(CURRENT_ENERGY_PERFORMANCE_BAND) = 20
UNION ALL SELECT 'minus_zero', COUNT(*) FROM $T WHERE NEW_BUILD_ENERGY_PERFORMANCE_RATING = N'-0' $B
UNION ALL SELECT 'tab_address1', COUNT(*) FROM $T WHERE CHARINDEX(NCHAR(9), ADDRESS1 $B) > 0
UNION ALL SELECT 'tab_address2', COUNT(*) FROM $T WHERE CHARINDEX(NCHAR(9), ADDRESS2 $B) > 0
UNION ALL SELECT 'tab_post_town', COUNT(*) FROM $T WHERE CHARINDEX(NCHAR(9), POST_TOWN $B) > 0
UNION ALL SELECT 'tab_postcode', COUNT(*) FROM $T WHERE CHARINDEX(NCHAR(9), POSTCODE $B) > 0
UNION ALL SELECT 'tab_or_space_in_pc_norm', COUNT(*) FROM $T WHERE CHARINDEX(NCHAR(9), pc_norm $B) > 0 OR CHARINDEX(N' ', pc_norm $B) > 0
UNION ALL SELECT 'replacement_character_address1', COUNT(*) FROM $T WHERE CHARINDEX(NCHAR(65533), ADDRESS1 $B) > 0
UNION ALL SELECT 'trailing_space_improvements', COUNT(*) FROM $T WHERE UNICODE(RIGHT(IMPROVEMENT_RECOMMENDATIONS, 1)) = 32
UNION ALL SELECT 'trailing_space_postcode', COUNT(*) FROM $T WHERE UNICODE(RIGHT(POSTCODE, 1)) = 32
UNION ALL SELECT 'cells_over_4000_characters', COUNT(*) FROM $T WHERE DATALENGTH(IMPROVEMENT_RECOMMENDATIONS) > 8000
UNION ALL SELECT 'longest_cell_characters', MAX(DATALENGTH(IMPROVEMENT_RECOMMENDATIONS)) / 2 FROM $T;" | sed 's/ *|/|/g; s/ *$//' | grep -v '^$' | tee "$W/empty_null.txt"
python3 - "$W/empty_null.txt" "$R/manifest.json" <<'PY'
import json, sys
got = dict(l.split("|") for l in open(sys.argv[1]).read().splitlines())
m = json.load(open(sys.argv[2]))
obs, rows = m["observations"]["table"], m["csv"]["rows"]
tab, removed, trail = obs["cells_with_tab"], obs["data_removed_cells"], obs["cells_with_trailing_space"]
expected = {"published_null": 0, "osg_text_empty": obs["uprn_osg_empty_rows"], "uprn_osg_null": obs["uprn_osg_empty_rows"],
            "rrn_null": obs["rrn_empty_rows"], "rrn_text_empty": obs["rrn_empty_rows"], "uprn_sepcr_null": 0,
            "historic_mismatch": 0, "floor_area_mismatch": 0,
            "data_removed_potential": removed.get("POTENTIAL_ENERGY_PERFORMANCE_RATING", 0), "potential_num_null": obs["potential_rating_null_rows"],
            "potential_num_null_without_data_removed": 0, "data_removed_asset": removed.get("ASSET_RATING", 0),
            "carbon_neu": obs["current_band_values"].get("Carbon Neu", 0),
            "tab_address1": tab.get("ADDRESS1", 0), "tab_address2": tab.get("ADDRESS2", 0), "tab_post_town": tab.get("POST_TOWN", 0),
            "tab_postcode": tab.get("POSTCODE", 0), "tab_or_space_in_pc_norm": 0,
            "replacement_character_address1": obs["cells_with_replacement_character"].get("ADDRESS1", 0),
            "trailing_space_improvements": trail.get("IMPROVEMENT_RECOMMENDATIONS", 0), "trailing_space_postcode": trail.get("POSTCODE", 0),
            "cells_over_4000_characters": obs["cells_over_sql_bounded_width"].get("IMPROVEMENT_RECOMMENDATIONS", 0),
            "longest_cell_characters": obs["longest_text_per_column"]["IMPROVEMENT_RECOMMENDATIONS"]}
bad = {k: (got.get(k), v) for k, v in expected.items() if int(got.get(k, -1)) != v}
if bad:
    print("empty/NULL and awkward cells: DIFFERENCES (SQL Server, manifest)", bad); sys.exit(1)
if int(got["address2_empty_not_null"]) <= 0 or int(got["minus_zero"]) < 0:
    print("empty/NULL: no empty ADDRESS2 was found, so the empty-string case was not exercised"); sys.exit(1)
print(f"empty/NULL and awkward cells: {len(expected)} counts equal the manifest; {got['address2_empty_not_null']} empty ADDRESS2 cells are empty strings, not NULL")
PY

echo "== probe: the digest fails when an awkward cell is changed, and passes again when it is restored"
tamper() {   # name, WHERE that picks one row, the new value of the column, the column
  $SQL -d epc -Q "SET NOCOUNT ON; DROP TABLE IF EXISTS probe_saved;
    SELECT TOP (1) epc_release, source_row, $4 AS saved INTO probe_saved FROM $T WHERE $2 ORDER BY source_row;
    IF @@ROWCOUNT <> 1 THROW 51000, 'the probe found no row to change', 1;
    UPDATE t SET $4 = $3 FROM $T t JOIN probe_saved s ON s.epc_release = t.epc_release AND s.source_row = t.source_row;
    IF @@ROWCOUNT <> 1 THROW 51000, 'the probe did not change one row', 1;" >/dev/null
  if $SQL -d epc -i /tmp/epc/check.sql -W -s '|' > "$W/tamper_$1.txt" 2>&1; then echo "tamper $1: the check PASSED on a changed table"; exit 1; fi
  grep -q "row digest.*FAIL" "$W/tamper_$1.txt" || { echo "tamper $1: the check failed, but not on the digest"; cat "$W/tamper_$1.txt"; exit 1; }
  [ "$(grep -c "|pass" "$W/tamper_$1.txt")" -eq 4 ] || { echo "tamper $1: a check other than the digest failed"; cat "$W/tamper_$1.txt"; exit 1; }
  $SQL -d epc -Q "SET NOCOUNT ON; UPDATE t SET $4 = s.saved FROM $T t JOIN probe_saved s ON s.epc_release = t.epc_release AND s.source_row = t.source_row; DROP TABLE probe_saved;" >/dev/null
  echo "tamper $1: the digest failed and the four other checks passed"
}
tamper last_character_of_the_longest_cell "DATALENGTH(IMPROVEMENT_RECOMMENDATIONS) = (SELECT MAX(DATALENGTH(IMPROVEMENT_RECOMMENDATIONS)) FROM $T)" \
  "STUFF(t.IMPROVEMENT_RECOMMENDATIONS, DATALENGTH(t.IMPROVEMENT_RECOMMENDATIONS) / 2, 1, N'#')" IMPROVEMENT_RECOMMENDATIONS
tamper trailing_space_removed "UNICODE(RIGHT(IMPROVEMENT_RECOMMENDATIONS, 1)) = 32 AND DATALENGTH(IMPROVEMENT_RECOMMENDATIONS) BETWEEN 4 AND 4000" \
  "LEFT(t.IMPROVEMENT_RECOMMENDATIONS, DATALENGTH(t.IMPROVEMENT_RECOMMENDATIONS) / 2 - 1)" IMPROVEMENT_RECOMMENDATIONS
tamper tab_replaced_by_space "CHARINDEX(NCHAR(9), ADDRESS2 $B) > 0" "REPLACE(t.ADDRESS2 $B, NCHAR(9), N' ')" ADDRESS2
tamper empty_cell_made_a_space "DATALENGTH(ADDRESS2) = 0" "N' '" ADDRESS2
$SQL -d epc -i /tmp/epc/check.sql -W -s '|' > "$W/restored.txt" || { echo "after restoring, the check FAILED"; cat "$W/restored.txt"; exit 1; }
[ "$(grep -c "|pass" "$W/restored.txt")" -eq 5 ] || { echo "after restoring, fewer than five checks passed"; exit 1; }
echo "restored: the five checks pass again"

echo "== probe: a fixture with supplementary characters through BULK INSERT"
# The release holds no character outside the Basic Multilingual Plane, so the real table cannot
# show what BULK INSERT does with one. The notebook probe's fixture has them: one at the last
# place of nvarchar(100) and of nvarchar(32), and one at the end of a value over 4,000 units in
# the nvarchar(max) column. It is imported with the same generated script, under another name.
F="$W/fixture"
python3 loader/notebook_probe/build_fixture.py "$F" > "$W/fixture_build.txt"
FROWS=$(python3 -c "import json;print(json.load(open('$F/fixture_manifest.json'))['csv']['rows'])")
FTOTAL=$(python3 -c "import json;print(json.load(open('$F/fixture_manifest.json'))['csv']['digest']['total'])")
gunzip -c "$F/delivery/$T.csv.gz" | { printf '\377\376'; iconv -f UTF-8 -t UTF-16LE; } > "$W/epc_nd_fixture.csv"
sed -e "s#/path/to/$T.csv#/tmp/epc/epc_nd_fixture.csv#" \
    -e "s#CODEPAGE = '65001'#DATAFILETYPE = 'widechar'#" \
    -e "s#ROWTERMINATOR = '0x0a'#ROWTERMINATOR = '\\\\n'#" -e "s#$T#epc_nd_fixture#g" docs/sql/import_csv.sql > "$W/fixture_import.sql"
sed -e "s#(N'$T', 0, 0, 1)#(N'$T', $FROWS, $FTOTAL, 1)#" -e "s#$T#epc_nd_fixture#g" docs/sql/check_loaded_digest.sql > "$W/fixture_check.sql"
grep -q "(N'epc_nd_fixture', $FROWS, $FTOTAL, 1)" "$W/fixture_check.sql" || { echo "the fixture check script was not given the expected values"; exit 1; }
docker cp "$W/epc_nd_fixture.csv" $C:/tmp/epc/epc_nd_fixture.csv
docker cp "$W/fixture_import.sql" $C:/tmp/epc/fixture_import.sql
docker cp "$W/fixture_check.sql" $C:/tmp/epc/fixture_check.sql
$SQL -d epc -i /tmp/epc/fixture_import.sql
$SQL -d epc -i /tmp/epc/fixture_check.sql -W -s '|' > "$W/fixture_check.txt" || { echo "fixture: the check FAILED"; cat "$W/fixture_check.txt"; exit 1; }
[ "$(grep -c "|pass" "$W/fixture_check.txt")" -eq 5 ] || { echo "fixture: fewer than five checks passed"; cat "$W/fixture_check.txt"; exit 1; }
# Lengths in UTF-16 code units (DATALENGTH / 2) and the last four bytes, which must be the
# surrogate pair of U+1F3E2 in UTF-16LE, 3C D8 E2 DF, whatever the collation.
$SQL -d epc -W -h -1 -s '|' -Q "SET NOCOUNT ON;
SELECT 'bounded_100_full', DATALENGTH(ADDRESS1) / 2 FROM epc_nd_fixture WHERE source_row = 15
UNION ALL SELECT 'bounded_32_full', DATALENGTH(PROPERTY_TYPE_SHORT) / 2 FROM epc_nd_fixture WHERE source_row = 15
UNION ALL SELECT 'bounded_100_ends_with_the_pair', CASE WHEN SUBSTRING(CONVERT(varbinary(max), ADDRESS1), DATALENGTH(ADDRESS1) - 3, 4) = 0x3CD8E2DF THEN 1 ELSE 0 END FROM epc_nd_fixture WHERE source_row = 15
UNION ALL SELECT 'bounded_32_ends_with_the_pair', CASE WHEN SUBSTRING(CONVERT(varbinary(max), PROPERTY_TYPE_SHORT), DATALENGTH(PROPERTY_TYPE_SHORT) - 3, 4) = 0x3CD8E2DF THEN 1 ELSE 0 END FROM epc_nd_fixture WHERE source_row = 15
UNION ALL SELECT 'max_with_supplementary_units', DATALENGTH(IMPROVEMENT_RECOMMENDATIONS) / 2 FROM epc_nd_fixture WHERE source_row = 16
UNION ALL SELECT 'max_ends_with_the_pair', CASE WHEN SUBSTRING(CONVERT(varbinary(max), IMPROVEMENT_RECOMMENDATIONS), DATALENGTH(IMPROVEMENT_RECOMMENDATIONS) - 3, 4) = 0x3CD8E2DF THEN 1 ELSE 0 END FROM epc_nd_fixture WHERE source_row = 16
UNION ALL SELECT 'max_7999_units', DATALENGTH(IMPROVEMENT_RECOMMENDATIONS) / 2 FROM epc_nd_fixture WHERE source_row = 9;
DROP TABLE epc_nd_fixture;" | sed 's/ *|/|/g; s/ *$//' | grep -v '^$' > "$W/fixture_actual.txt"
printf 'bounded_100_full|100\nbounded_32_full|32\nbounded_100_ends_with_the_pair|1\nbounded_32_ends_with_the_pair|1\nmax_with_supplementary_units|4452\nmax_ends_with_the_pair|1\nmax_7999_units|7999\n' > "$W/fixture_expected.txt"
if diff "$W/fixture_expected.txt" "$W/fixture_actual.txt"; then echo "fixture: $FROWS rows imported, five checks pass, a supplementary character fills a bounded column to its last unit and survives in the max column"; else echo "fixture: DIFFERENCES"; exit 1; fi

echo "== probe: the three join queries on SQL Server return their columns, in order"
python3 - > "$W/contract.txt" <<'PY'
import sys
sys.path[:0] = [".", "tests"]
from test_joins import CONTRACT
for name, columns in CONTRACT.items():
    print(name + "=" + "|".join(columns))
PY
U="(SELECT TOP (1) uprn_osg FROM $T WHERE uprn_osg IS NOT NULL AND historic_flag = 0 GROUP BY uprn_osg HAVING COUNT(*) = 1 ORDER BY uprn_osg)"
header() {   # query file, cohort DDL columns, one cohort row
  $SQL -d epc -W -s '|' -Q "SET NOCOUNT ON; CREATE TABLE #cohort ($2); INSERT INTO #cohort VALUES $3;
$(sed -n '/^IF EXISTS (SELECT 1 FROM #cohort/,$p' "docs/sql/$1")" | head -1 | sed 's/ *|/|/g; s/ *$//'
}
for Q in join_by_uprn.sql join_latest_by_uprn.sql join_by_postcode.sql; do
  case $Q in
    join_by_uprn.sql) GOT=$(header $Q "cohort_row_id int, pseudo_id int, uprn nvarchar(20), cohort_date date" "(1, 1, CONVERT(nvarchar(20), $U), '2026-09-30')");;
    join_latest_by_uprn.sql) GOT=$(header $Q "cohort_row_id int, pseudo_id int, uprn nvarchar(20)" "(1, 1, CONVERT(nvarchar(20), $U))");;
    join_by_postcode.sql) GOT=$(header $Q "cohort_row_id int, pseudo_id int, postcode nvarchar(10), cohort_date date" "(1, 1, (SELECT TOP (1) POSTCODE FROM $T ORDER BY source_row), '2026-09-30')");;
  esac
  WANT=$(grep "^$Q=" "$W/contract.txt" | cut -d= -f2)
  [ "$GOT" = "$WANT" ] || { echo "$Q: columns differ"; echo " got  $GOT"; echo " want $WANT"; exit 1; }
  echo "$Q: $(echo "$GOT" | tr '|' '\n' | wc -l | tr -d ' ') columns as the contract lists them"
done

echo "== probe: the join statuses, asserted"
$SQL -d epc -W -h -1 -s '|' -Q "SET NOCOUNT ON;
CREATE TABLE #cohort (cohort_row_id int, pseudo_id int, uprn nvarchar(20), cohort_date date);
DECLARE @u bigint = $U;
DECLARE @d date = (SELECT MAX(inspection_date_parsed) FROM $T WHERE uprn_osg = @u);
INSERT INTO #cohort VALUES (1, 1, CONVERT(nvarchar(20), @u), @d), (2, 1, RIGHT(REPLICATE(N'0', 12) + CONVERT(nvarchar(20), @u), 12), @d),
  (3, 1, CONVERT(nvarchar(20), @u), '2000-01-01'), (4, 2, N'1', '2030-01-01'), (5, 2, N'', '2030-01-01'), (6, 3, NULL, '2030-01-01'), (7, 3, N'x', '2030-01-01');
$(sed -n '/^IF EXISTS (SELECT 1 FROM #cohort/,$p' docs/sql/join_by_uprn.sql)
" | sed 's/ *|/|/g; s/ *$//' | grep -v '^$' | cut -d'|' -f1,3,8 > "$W/join_actual.txt"
printf '1|matched|0\n2|matched|0\n3|no_certificate_by_date|NULL\n4|uprn_not_in_epc|NULL\n5|no_uprn|NULL\n6|no_uprn|NULL\n7|no_uprn|NULL\n' > "$W/join_expected.txt"
if diff "$W/join_expected.txt" "$W/join_actual.txt"; then echo "join by UPRN: 7 cohort rows returned once each with the expected status and age"; else echo "join by UPRN: DIFFERENCES"; exit 1; fi

# SQL Server prints "Warning: Null value is eliminated by an aggregate" for the postcode query,
# because MAX(uprn_osg) skips the certificates without a UPRN. It is a message, not an error.
# The postcode join: a postcode that the release holds with a tab, given to the query with the
# tab, with a space in its place and with neither. Each must return the same buildings. Then a
# building whose postcode changed: it is returned at its latest postcode and not at the earlier one.
$SQL -d epc -W -h -1 -s '|' -Q "SET NOCOUNT ON;
CREATE TABLE #cohort (cohort_row_id int, pseudo_id int, postcode nvarchar(10), cohort_date date);
DECLARE @raw nvarchar(32) = (SELECT TOP (1) POSTCODE FROM $T WHERE CHARINDEX(NCHAR(9), POSTCODE $B) > 0 ORDER BY source_row);
DECLARE @norm nvarchar(32) = (SELECT TOP (1) pc_norm FROM $T WHERE POSTCODE = @raw $B);
DECLARE @b bigint = (SELECT TOP (1) uprn_sepcr FROM $T WHERE pc_norm IS NOT NULL GROUP BY uprn_sepcr HAVING COUNT(DISTINCT pc_norm) = 2 AND COUNT(*) = 2 AND COUNT(DISTINCT inspection_date_parsed) = 2 ORDER BY uprn_sepcr);
DECLARE @new nvarchar(32) = (SELECT TOP (1) pc_norm FROM $T WHERE uprn_sepcr = @b ORDER BY inspection_date_parsed DESC);
DECLARE @old nvarchar(32) = (SELECT TOP (1) pc_norm FROM $T WHERE uprn_sepcr = @b ORDER BY inspection_date_parsed ASC);
INSERT INTO #cohort VALUES (1, 1, LEFT(@raw, 10), '2026-09-30'), (2, 1, REPLACE(LEFT(@raw, 10) $B, NCHAR(9), N' '), '2026-09-30'), (3, 1, @norm, '2026-09-30'),
  (4, 1, NCHAR(9) + N' ', '2026-09-30'), (5, 2, @new, '2026-09-30'), (6, 2, @old, '2026-09-30');
$(sed -n '/^WITH cohort AS (/,$p' docs/sql/join_by_postcode.sql | sed 's/^FROM cohort AS c$/INTO #out FROM cohort AS c/')
SELECT 'same_buildings_with_tab_space_or_neither', CASE WHEN (SELECT COUNT(*) FROM #out WHERE cohort_row_id = 1 AND building IS NOT NULL) > 0
    AND NOT EXISTS (SELECT building FROM #out WHERE cohort_row_id = 1 EXCEPT SELECT building FROM #out WHERE cohort_row_id = 2)
    AND NOT EXISTS (SELECT building FROM #out WHERE cohort_row_id = 2 EXCEPT SELECT building FROM #out WHERE cohort_row_id = 3)
    AND NOT EXISTS (SELECT building FROM #out WHERE cohort_row_id = 3 EXCEPT SELECT building FROM #out WHERE cohort_row_id = 1) THEN 1 ELSE 0 END
UNION ALL SELECT 'spaces_and_tabs_only_is_no_postcode', COUNT(*) FROM #out WHERE cohort_row_id = 4 AND epc_status = 'no_postcode'
UNION ALL SELECT 'moved_building_at_its_latest_postcode', COUNT(*) FROM #out WHERE cohort_row_id = 5 AND building = @b AND epc_status = 'matched'
UNION ALL SELECT 'moved_building_not_at_its_earlier_postcode', COUNT(*) FROM #out WHERE cohort_row_id = 6 AND building = @b;" | sed 's/ *|/|/g; s/ *$//' | grep -v '^$' | grep -v '^Warning: Null value is eliminated' > "$W/postcode_actual.txt"
printf 'same_buildings_with_tab_space_or_neither|1\nspaces_and_tabs_only_is_no_postcode|1\nmoved_building_at_its_latest_postcode|1\nmoved_building_not_at_its_earlier_postcode|0\n' > "$W/postcode_expected.txt"
if diff "$W/postcode_expected.txt" "$W/postcode_actual.txt"; then echo "join by postcode: tab, space and neither return the same buildings; a moved building is at its latest postcode only"; else echo "join by postcode: DIFFERENCES"; exit 1; fi

echo "== probe: the cohort key guards, asserted (a NULL key and a repeated key each stop the query)"
for CASE in "(1, 1, N'1', '2030-01-01'), (NULL, 1, N'1', '2030-01-01')" "(1, 1, N'1', '2030-01-01'), (1, 2, N'1', '2030-01-01')"; do
  OUT=$($SQL -d epc -W -h -1 -s '|' -Q "SET NOCOUNT ON;
CREATE TABLE #cohort (cohort_row_id int, pseudo_id int, uprn nvarchar(20), cohort_date date);
INSERT INTO #cohort VALUES $CASE;
$(sed -n '/^IF EXISTS (SELECT 1 FROM #cohort/,$p' docs/sql/join_by_uprn.sql)
" 2>&1 || true)
  echo "$OUT" | grep -q "cohort_row_id must" || { echo "guard: the query did not stop for $CASE"; echo "$OUT" | head -5; exit 1; }
done
echo "guards: both cases stopped with the expected message"
echo "== done; probe files in $W"

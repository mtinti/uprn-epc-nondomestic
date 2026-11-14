"""Build the table: verify the pins, read the extract, check, write, read back, record.

    python -m epc_nd_ingest.pipeline                    # writes results/
    python -m epc_nd_ingest.pipeline --verify-archive   # also hashes the 7z archive and the note first

The extract is one file of 95,719 rows. It is read whole and written as one Parquet row group
and one CSV.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys
from pathlib import Path

import pandas as pd

from . import checks as table_checks
from . import columns as col
from .core import output
from .core import text_output as tx
from .core.checks import BuildStopped, Report
from .core.sources import REGISTRY, ROOT, SOURCE_ROOT, load_registry, sha256, verify
from .reader import LABEL, read_member, read_zone_list

PACKAGE = Path(__file__).resolve().parent
CONTRACT = PACKAGE / "export_contract.yaml"
DECISIONS = PACKAGE / "decisions.yaml"
RESULTS = ROOT / "results"
TABLE = col.TABLE
# Never printed in the build report, which travels with the code.
WITHHELD_FROM_REPORT = ("ADDRESS1", "ADDRESS2", "POST_TOWN", "POSTCODE")


OUTPUTS = ("{table}.parquet", "{csv}", "manifest.json", "BUILD_REPORT.md")


def build(results: Path = RESULTS, registry_path: Path = REGISTRY, source_root: Path = SOURCE_ROOT,
          verify_archive: bool = False, log=print) -> dict:
    """Build into a staging folder beside `results` and move the four outputs into place only
    after every check has passed, so a failed rebuild leaves the last accepted build and its
    manifest untouched and never leaves half-written files beside a manifest they do not match."""
    results = Path(results)
    results.mkdir(parents=True, exist_ok=True)
    stamp = f"{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')}_{os.getpid()}"
    staging = results / f".staging_{stamp}"
    staging.mkdir()
    try:
        manifest = _build(staging, registry_path, source_root, verify_archive, log)
        names = [name.format(table=TABLE, csv=manifest["csv"]["file"]) for name in OUTPUTS]
        promote(staging, results, names, results / f".previous_{stamp}")
        staging.rmdir()
        return manifest
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def promote(staging: Path, results: Path, names: list, previous: Path) -> None:
    """Move the accepted outputs into place as one generation. The files of the last accepted
    build are first moved aside into `previous`, then the new files moved in; if any move
    fails, every move is undone so `results` holds the last accepted build again. Only if the
    rollback itself fails is `previous` kept, and the error names it: the accepted files are
    then split between `results` (those restored before the rollback stopped) and `previous`
    (the rest), so recovery must keep both folders. Nothing accepted is ever deleted. Each step
    is a rename on one filesystem, so an interruption leaves at worst `previous` beside a
    partial `results`. `results` is not readable by another process during promotion."""
    moved_aside, promoted = [], []
    try:
        previous.mkdir()
        for name in names:
            if (results / name).exists():
                os.replace(results / name, previous / name)
                moved_aside.append(name)
        for name in names:
            os.replace(staging / name, results / name)
            promoted.append(name)
    except BaseException as failure:
        try:
            for name in promoted:
                os.replace(results / name, staging / name)
            for name in moved_aside:
                os.replace(previous / name, results / name)
            previous.rmdir()
        except BaseException as rollback_failure:
            raise RuntimeError(f"promotion failed and could not be rolled back; the last accepted build is split between {results} and {previous}, keep both") from rollback_failure
        raise failure
    shutil.rmtree(previous)


def _build(results: Path, registry_path: Path, source_root: Path, verify_archive: bool, log) -> dict:
    report = Report()
    registry = load_registry(registry_path, source_root)
    verify(registry, report, archive=verify_archive)
    schema = output.load_schema(col.SCHEMA)
    contract = tx.load_contract(CONTRACT)
    published = col.load_published()
    decisions_sha256 = sha256(DECISIONS)
    report.equal("schema.matches_generator", schema["fields"], col.fields(published),
                 detail="output_schema.yaml is what python -m epc_nd_ingest.columns writes")
    report.require()

    zones = {}
    for vintage, spec in registry.datazone_lists.items():
        codes = read_zone_list(registry.root / spec["file"], spec)
        report.equal(f"datazones_{vintage}.count", len(codes), spec["zones"])
        report.equal(f"datazones_{vintage}.distinct", len(set(codes)), len(codes))
        zones[vintage] = set(codes)
    report.require()

    metadata = output.table_metadata(registry, schema, decisions_sha256)
    parquet = results / f"{TABLE}.parquet"
    csv_path = results / contract["tables"][TABLE]["file"]
    columns = tx.exported_columns(schema, contract, TABLE)
    kinds = {f["name"]: f["type"] for f in schema["fields"]}
    decimal_columns = [c for c in columns if kinds[c] == "decimal"]

    pq_writer = output.ParquetWriter(schema, parquet, metadata)
    csv_writer = tx.CsvWriter(contract, csv_path)
    per_member, samples, total = {}, [], 0
    try:
        _read_all(registry, published, schema, zones, contract, columns, decimal_columns, pq_writer, csv_writer,
                  per_member, samples, report, log)
    except BaseException:
        pq_writer.abort()
        csv_writer.abort()
        raise
    total = sum(int(d["digest_total"]) for d in per_member.values())
    parquet_sha = pq_writer.close()
    csv_info = csv_writer.close()
    csv_info["digest"] = tx.digest_record(contract, csv_info["rows"], total)
    csv_info["digest_per_member"] = per_member

    # Read back. Parquet: structure, then the row group rendered again must give the digest
    # recorded while writing, and the sampled rows must equal the source cells text for text.
    parquet_info = output.readback_structure(parquet, schema, metadata, report)
    report.equal("readback.parquet.rows", parquet_info["rows"], csv_info["rows"])
    report.equal("readback.parquet.row_groups", parquet_info["row_groups"], 1)
    report.require()
    sample_differences, sample_cells = 0, 0
    by_row = {s["source_row"]: s for s in samples}
    saved = output.read_table(parquet, row_group=0)
    rendered = tx.render(saved, schema, columns, contract)
    report.equal(f"readback.parquet.{LABEL}.digest", str(sum(tx.row_hashes(rendered, contract))), per_member[registry.member["file"]]["digest_total"],
                 detail="the row group rendered again gives the digest recorded while writing")
    for k, row in saved[saved["source_row"].isin(list(by_row))].iterrows():
        for name, cell in by_row[int(row["source_row"])]["cells"].items():
            sample_cells += 1
            if row[name] != cell:
                sample_differences += 1
    del saved, rendered
    report.equal("readback.parquet.sampled_rows_equal_source", sample_differences, 0,
                 detail=f"{len(samples)} rows (first, middle, last of the file), {sample_cells:,} published cells compared with the source text")
    report.require()
    tx.readback_csv_digest(csv_path, columns, schema, contract, report, "readback.csv", csv_info["rows"], total)
    report.require()

    observations = table_checks.check_table(parquet, schema, report, str(registry.release["extracted_from_register"]))
    report.observe("table", observations)
    report.observe("samples", [{"source_row": s["source_row"]} for s in samples])

    manifest = {
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "table": TABLE, "epc_release": registry.epc_release,
        "schema_version": schema["version"], "schema_sha256": schema["sha256"],
        "registry_sha256": registry.sha256, "published_columns_sha256": sha256(col.PUBLISHED),
        "contract_sha256": contract["sha256"], "decisions_sha256": decisions_sha256,
        "parquet": dict(parquet_info, sha256=parquet_sha), "csv": csv_info,
        "publisher": registry.publisher, "licence": registry.licence, "attribution": registry.attribution,
        "redistribution": registry.redistribution,
        "sources": {"archive": registry.release["archive"], "note": registry.release["note"],
                    "members": [{"file": m["file"], "sha256": m["sha256"], "rows": m["rows"]} for m in registry.members]},
        "datazone_lists": {str(k): {"file": v["file"], "sha256": v["sha256"], "zones": v["zones"]} for k, v in registry.datazone_lists.items()},
        "grain": output.GRAIN,
        "summary": report.summary(), "checks": report.to_records(), "observations": report.observations,
    }
    (results / "manifest.json").write_text(json.dumps(manifest, indent=1, default=str))
    (results / "BUILD_REPORT.md").write_text(build_report(manifest, samples, schema))
    return manifest


def _read_all(registry, published, schema, zones, contract, columns, decimal_columns, pq_writer, csv_writer,
              per_member, samples, report, log) -> None:
    member = registry.member
    t0 = dt.datetime.now()
    quarter_end = registry.release["quarter_end"]
    if not isinstance(quarter_end, dt.date):
        quarter_end = dt.date.fromisoformat(str(quarter_end))
    frame, picked = read_member(registry.root / member["file"], member, published, schema, zones, registry.epc_release,
                                quarter_end, report)
    samples += picked
    pq_writer.write(frame)
    rendered = tx.render(frame, schema, columns, contract)
    csv_writer.write(rendered)
    member_total = sum(tx.row_hashes(rendered, contract))
    bad = 0
    for name in decimal_columns:
        for v, text in zip(frame[name], rendered[name]):
            if text != contract["digest"]["null_marker"] and tx.parse_decimal(text) != v:
                bad += 1
    report.equal(f"{LABEL}.decimal_round_trip", bad, 0, detail="every decimal cell: file text, Decimal, 4-place text, Decimal")
    report.require()
    per_member[member["file"]] = {"rows": len(frame), "digest_total": str(member_total)}
    log(f"  {member['file']}: {len(frame):,} rows in {(dt.datetime.now() - t0).seconds}s")


def _counts(d: dict) -> str:
    return ", ".join(f"{k}: {v:,}" for k, v in d.items()) or "none"


def build_report(manifest: dict, samples: list, schema: dict) -> str:
    obs = manifest["observations"]["table"]
    lines = [f"# Build report: {manifest['table']}, release {manifest['epc_release']}, {manifest['built_at'][:19]}Z", "",
             f"Schema `{manifest['schema_version']}`. {manifest['parquet']['rows']:,} rows by {manifest['parquet']['columns']} columns in the Parquet, "
             f"{manifest['csv']['columns']} in the CSV.",
             f"CSV `{manifest['csv']['file']}` SHA256 `{manifest['csv']['sha256']}`, digest total `{manifest['csv']['digest']['total']}`.",
             f"Parquet SHA256 `{manifest['parquet']['sha256']}`.", "",
             "## Rows by the year of lodgement on the register", "",
             "The extract is one file. The year is that of `created_at_parsed`.", "",
             "| Year | Rows | HISTORIC True | HISTORIC False | Empty UPRN | Empty RRN |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for year, rows in obs["rows_per_created_year"].items():
        h = obs["historic_per_created_year"][year]
        lines.append(f"| {year} | {rows:,} | {h['True']:,} | {h['False']:,} | {obs['uprn_osg_empty_rows_per_created_year'].get(year, 0):,} | "
                     f"{obs['rrn_empty_rows_per_created_year'].get(year, 0):,} |")
    lines += ["", "## What the release holds", "", "Counted and reported. None of these stops the build and nothing is repaired.", ""]
    facts = [
        ("Distinct Gazetteer UPRNs (`uprn_osg`)", f"{obs['uprn_osg_distinct']:,}"),
        ("Distinct register numbers (`uprn_sepcr`)", f"{obs['uprn_sepcr_distinct']:,}"),
        ("Rows with no Gazetteer UPRN", f"{obs['uprn_osg_empty_rows']:,}"),
        ("UPRNs by digit count", _counts(obs["uprn_osg_digits"])),
        ("Register numbers with a UPRN in some rows and none in others", f"{obs['uprn_sepcr_with_and_without_uprn_osg']:,}"),
        ("UPRNs with exactly one `HISTORIC = False` certificate", f"{obs['uprn_osg_with_one_current']:,}"),
        ("UPRNs with two or more `HISTORIC = False` certificates (`ambiguous_latest`)", f"{obs['uprn_osg_with_two_or_more_current']:,}"),
        ("UPRNs whose certificates are all `HISTORIC = True` (`no_current_certificate`)", f"{obs['uprn_osg_all_historic']:,}"),
        ("Register numbers with two or more `HISTORIC = False` certificates", f"{obs['uprn_sepcr_with_two_or_more_current']:,}"),
        ("Register numbers whose certificates are all `HISTORIC = True`", f"{obs['uprn_sepcr_all_historic']:,}"),
        ("Register numbers with two or more `pc_norm` over their certificates", f"{obs['uprn_sepcr_with_two_or_more_pc_norm']:,}"),
        ("Register number and inspection day with two or more certificates", f"{obs['same_uprn_sepcr_same_inspection_day_pairs']:,}"),
        ("UPRN and inspection day with two or more certificates", f"{obs['same_uprn_osg_same_inspection_day_pairs']:,}"),
        ("Rows with an empty RRN", f"{obs['rrn_empty_rows']:,}"),
        ("`datazone_2001_status`", _counts(obs["datazone_2001_status"])),
        ("`datazone_2011_status`", _counts(obs["datazone_2011_status"])),
        ("Distinct 2001 and 2011 data zone codes", f"{obs['datazone_2001_distinct']:,} and {obs['datazone_2011_distinct']:,}"),
        ("Rows with `LOCAL_AUTHORITY`, `DATA_ZONE` and `CONSTITUENCY` all empty", f"{obs['geography_columns_all_empty_rows']:,}"),
        ("Rows with a local authority code outside Scotland", f"{obs['local_authority_not_scottish_rows']:,}"),
        ("Rows with an empty postcode", f"{obs['postcode_empty_rows']:,}"),
        ("Distinct `pc_norm`", f"{obs['pc_norm_distinct']:,}"),
        ("`pc_norm` not 5 to 7 characters", f"{obs['pc_norm_not_5_to_7_chars']:,}"),
        ("`pc_norm` with a character other than a letter or a digit", f"{obs['pc_norm_with_other_than_letters_and_digits']:,}"),
        ("Rows with a postcode area outside Scotland", f"{obs['postcode_area_not_scottish_rows']:,}"),
        ("Rows where `pc_norm` removed a tab", f"{obs['postcode_with_tab_rows']:,}"),
        ("Cells with a tab", _counts(obs["cells_with_tab"])),
        ("Cells with an embedded newline", _counts(obs["cells_with_embedded_newline"])),
        ("Cells with the replacement character U+FFFD", _counts(obs["cells_with_replacement_character"])),
        ("Cells that end with a space", _counts(obs["cells_with_trailing_space"])),
        ("Cells with a supplementary character, which takes two UTF-16 code units", _counts(obs["cells_with_supplementary_character"])),
        (f"Cells longer than {4000:,} UTF-16 code units, stored as `nvarchar(max)`", _counts(obs["cells_over_sql_bounded_width"])),
        ("Cells holding `Data removed`", _counts(obs["data_removed_cells"])),
        ("Rows with `potential_energy_performance_rating_num` NULL", f"{obs['potential_rating_null_rows']:,}"),
        ("`floor_area_int` range", f"{obs['floor_area_range'][0]:,} to {obs['floor_area_range'][1]:,}; {obs['floor_area_under_15_rows']:,} rows under 15, {obs['floor_area_over_1500_rows']:,} over 1,500"),
        ("`current_energy_performance_rating_int` range", f"{obs['current_rating_range'][0]:,} to {obs['current_rating_range'][1]:,}; {obs['current_rating_negative_rows']:,} rows negative"),
        ("`building_emissions_num` range", f"{obs['building_emissions_range'][0]} to {obs['building_emissions_range'][1]}"),
        ("`primary_energy_value_int` range", f"{obs['primary_energy_value_range'][0]:,} to {obs['primary_energy_value_range'][1]:,}"),
        ("Rows where the rating is not the emissions rounded", f"{obs['rating_differs_from_rounded_emissions_rows']:,}"),
        ("Rows where the band is not the cut of the rating", f"{obs['band_differs_from_cut_of_rating_rows']:,}"),
        ("`CURRENT_ENERGY_PERFORMANCE_BAND` values", _counts(obs["current_band_values"])),
        ("Rows with empty `MEETS_2002_STANDARD`", f"{obs['meets_2002_standard_empty_rows']:,}"),
        ("Rows lodged before inspection", f"{obs['lodgement_before_inspection_rows']:,}"),
        ("Rows inspected after the extraction date", f"{obs['inspection_after_extraction_rows']:,}"),
        ("Rows inspected more than a year before lodgement", f"{obs['inspection_over_a_year_before_lodgement_rows']:,}"),
        ("Median days from inspection to lodgement", f"{obs['inspection_to_lodgement_median_days']}"),
        ("Rows where `CREATED_AT` and `LODGEMENT_DATE` are different days", f"{obs['created_at_day_differs_from_lodgement_date_rows']:,}"),
        ("Inspection date range", f"{obs['inspection_date_range'][0]} to {obs['inspection_date_range'][1]}"),
        ("Lodgement date range", f"{obs['lodgement_date_range'][0]} to {obs['lodgement_date_range'][1]}"),
        ("`CREATED_AT` range", f"{obs['created_at_range'][0]} to {obs['created_at_range'][1]}"),
    ]
    lines += ["| Fact | Value |", "| --- | --- |"] + [f"| {k} | {v} |" for k, v in facts]
    lines += ["", "## Certificates by `PROPERTY_TYPE_SHORT`", "", "| Value | Rows |", "| --- | ---: |"]
    lines += [f"| {k} | {v:,} |" for k, v in obs["property_type_short_values"].items()]
    widths = {f["name"]: f["width"] for f in schema["fields"] if f["type"] == "string"}
    lines += ["", "## Longest text per column against the width it accepts", "",
              "Both in UTF-16 code units, as SQL Server counts an `nvarchar`: a character outside the Basic Multilingual Plane takes two.", "",
              "| Column | Longest | Width | SQL type |", "| --- | ---: | ---: | --- |"]
    for name, longest in obs["longest_text_per_column"].items():
        sql = f"nvarchar({widths[name]})" if widths[name] <= col.SQL_BOUNDED_MAX else "nvarchar(max)"
        lines.append(f"| `{name}` | {longest} | {widths[name]} | {sql} |")
    lines += ["", "## Checks", "", f"{manifest['summary']['blocking_passed']} passed, {manifest['summary']['blocking_failed']} failed.", "",
              "| Check | Result | Detail |", "| --- | --- | --- |"]
    for c in manifest["checks"]:
        lines.append(f"| `{c['name']}` | {'pass' if c['passed'] else 'FAIL'} | {str(c['detail'])[:160]} |")
    last = samples[-1]
    lines += ["", f"## One certificate cell for cell: row {last['source_row']}", "",
              "The source text of the pinned file, which the Parquet holds unchanged (checked for the first, middle and last row of the file). "
              "The address lines and the postcode are not printed here.", "", "| Column | Source text |", "| --- | --- |"]
    for name, cell in last["cells"].items():
        shown = "(withheld)" if name in WITHHELD_FROM_REPORT else cell.replace("|", "\\|").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        lines.append(f"| `{name}` | `{shown}` |" if shown else f"| `{name}` | |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    verify_archive = "--verify-archive" in argv
    try:
        manifest = build(verify_archive=verify_archive)
    except BuildStopped as stop:
        print(f"stopped: {stop}", file=sys.stderr)
        return 1
    print(f"built {manifest['parquet']['rows']:,} rows; {manifest['summary']['blocking_passed']} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

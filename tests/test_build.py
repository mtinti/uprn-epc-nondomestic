"""The build on a synthetic release: it passes on the publisher's shape, and each hostile file
fails with its own named check and nothing written."""

import csv
import datetime as dt
import gzip
import io
import json
from decimal import Decimal

import pandas as pd
import pytest
import yaml

from epc_nd_ingest import columns as col
from epc_nd_ingest import pipeline
from epc_nd_ingest.core import output
from epc_nd_ingest.core.checks import BuildStopped, Report
from epc_nd_ingest.core.sources import load_registry
from epc_nd_ingest.reader import read_member, read_zone_list

from synthetic import LABELS, MEMBER, NAMES, default_rows, make_release, make_row

TABLE = "epc_nondomestic"
OUTPUT_FILES = {f"{TABLE}.parquet", f"{TABLE}.csv.gz", "manifest.json", "BUILD_REPORT.md"}


def _build(tmp_path, **kwargs):
    registry = make_release(tmp_path, **kwargs)
    return pipeline.build(results=tmp_path / "results", registry_path=registry, source_root=tmp_path / "sources", log=lambda *a: None)


def _saved(tmp_path):
    return output.read_table(tmp_path / "results" / f"{TABLE}.parquet").set_index("source_row")


def test_synthetic_release_builds_and_keeps_every_published_cell(tmp_path):
    manifest = _build(tmp_path)
    assert manifest["summary"]["blocking_failed"] == 0
    assert manifest["csv"]["rows"] == 7 and manifest["parquet"]["row_groups"] == 1
    saved = _saved(tmp_path)
    # The published text is untouched: trailing space, tab, replacement character, cut band, minus zero.
    assert saved.loc[1, "ADDRESS2"] == "TEST STREET " and saved.loc[1, "datazone_2011"] == "S01006982"
    assert saved.loc[2, "REPORT_REFERENCE_NUMBER"] == "" and pd.isna(saved.loc[2, "rrn"]) and bool(saved.loc[2, "historic_flag"])
    assert saved.loc[3, "ADDRESS1"] == "THE OLD MILL\t" and saved.loc[3, "ADDRESS2"] == "CAF� ROW"
    assert saved.loc[3, "OSG_REFERENCE_NUMBER"] == "" and pd.isna(saved.loc[3, "uprn_osg"])
    assert saved.loc[3, "datazone_2001_status"] == "not_a_datazone" and saved.loc[3, "datazone_2011_status"] == "not_a_datazone"
    assert saved.loc[4, "uprn_osg"] == 906700556768 and saved.loc[4, "datazone_2001_status"] == "empty" and pd.isna(saved.loc[4, "datazone_2001"])
    assert saved.loc[6, "CURRENT_ENERGY_PERFORMANCE_BAND"] == "Carbon Neu" and saved.loc[6, "NEW_BUILD_ENERGY_PERFORMANCE_RATING"] == "-0"
    assert saved.loc[7, "CONSTITUENCY_LABEL"] == "Steòrnabhagh a Deas"
    # The CSV carries every column, the address lines included (decision address-lines-loaded).
    with gzip.open(tmp_path / "results" / f"{TABLE}.csv.gz", "rt", encoding="utf-8", newline="") as fh:
        header = fh.readline().rstrip("\n").split(",")
    assert "ADDRESS1" in header and "POST_TOWN" in header and "POSTCODE" in header and "pc_norm" in header
    assert len(header) == 57 and header[:2] == ["epc_release", "source_row"]


def test_typed_copies_equal_their_text(tmp_path):
    _build(tmp_path)
    saved = _saved(tmp_path)
    assert saved.loc[1, "floor_area_int"] == 250 and saved.loc[1, "current_energy_performance_rating_int"] == 65
    assert saved.loc[1, "building_emissions_num"] == Decimal("65.21") and saved.loc[1, "primary_energy_value_int"] == 380
    assert saved.loc[1, "potential_energy_performance_rating_num"] == Decimal("40.00")
    assert saved.loc[1, "inspection_date_parsed"] == dt.date(2024, 3, 2) and saved.loc[1, "created_at_parsed"] == dt.datetime(2024, 3, 11, 10, 1)
    # A negative rating, a negative two-decimal emission rate, a negative primary energy value.
    assert saved.loc[6, "current_energy_performance_rating_int"] == -12 and saved.loc[6, "building_emissions_num"] == Decimal("-12.4")
    assert saved.loc[6, "primary_energy_value_int"] == -55 and saved.loc[6, "potential_energy_performance_rating_num"] == Decimal("-20")
    assert saved.loc[6, "floor_area_int"] == 138037
    for row in saved.itertuples():
        assert row.floor_area_int == int(row.FLOOR_AREA) and row.building_emissions_num == Decimal(row.BUILDING_EMISSIONS)


def test_postcode_with_spaces_and_tabs_gives_a_clean_pc_norm(tmp_path):
    _build(tmp_path)
    saved = _saved(tmp_path)
    assert saved.loc[3, "POSTCODE"] == " \tFK10 1AB" and saved.loc[3, "pc_norm"] == "FK101AB"
    assert saved.loc[4, "POSTCODE"] == "g12 8qq " and saved.loc[4, "pc_norm"] == "G128QQ"


def test_data_removed_is_null_in_the_typed_copy_and_kept_in_the_text(tmp_path):
    manifest = _build(tmp_path)
    saved = _saved(tmp_path)
    assert saved.loc[5, "POTENTIAL_ENERGY_PERFORMANCE_RATING"] == "Data removed" and pd.isna(saved.loc[5, "potential_energy_performance_rating_num"])
    assert saved.loc[5, "ASSET_RATING"] == "Data removed" and saved.loc[5, "ASSET_RATING_BAND"] == "Data removed"
    assert saved["potential_energy_performance_rating_num"].isna().sum() == 1
    assert manifest["observations"]["table"]["data_removed_cells"] == {
        "POTENTIAL_ENERGY_PERFORMANCE_RATING": 1, "POTENTIAL_ENERGY_PERFORMANCE_BAND": 1, "ASSET_RATING": 1, "ASSET_RATING_BAND": 1}


def test_a_cell_over_4000_characters_builds_and_one_over_the_width_fails(tmp_path):
    manifest = _build(tmp_path)
    saved = _saved(tmp_path)
    assert len(saved.loc[7, "IMPROVEMENT_RECOMMENDATIONS"]) == 4451 and saved.loc[7, "IMPROVEMENT_RECOMMENDATIONS"].endswith("x ")
    assert manifest["observations"]["table"]["cells_over_sql_bounded_width"] == {"IMPROVEMENT_RECOMMENDATIONS": 1}
    rows = default_rows()
    rows[0]["IMPROVEMENT_RECOMMENDATIONS"] = "x" * 8001
    failures = _failing_check(tmp_path / "long", rows)
    assert failures["extract.text_within_width"] == "longest value per column over its width"
    rows = default_rows()
    rows[0]["PROPERTY_TYPE_SHORT"] = "x" * 101   # one character over a bounded column
    assert "extract.text_within_width" in _failing_check(tmp_path / "bounded", rows)


BUILDING = "\U0001F3E2"   # a character outside the Basic Multilingual Plane: two UTF-16 code units


def test_a_supplementary_character_counts_as_two_at_the_edge_of_a_bounded_column(tmp_path):
    """SQL Server counts an nvarchar in UTF-16 code units, and so does the width check. ADDRESS1
    is nvarchar(100): 98 letters and one supplementary character fill it, 99 and one do not,
    although that value has only 100 characters."""
    rows = default_rows()
    rows[0]["ADDRESS1"] = "A" * 98 + BUILDING
    manifest = _build(tmp_path / "fits", rows=rows)
    obs = manifest["observations"]["table"]
    assert obs["longest_text_per_column"]["ADDRESS1"] == 100 and obs["cells_with_supplementary_character"] == {"ADDRESS1": 1}
    assert _saved(tmp_path / "fits").loc[1, "ADDRESS1"] == "A" * 98 + BUILDING
    rows = default_rows()
    rows[0]["ADDRESS1"] = "A" * 99 + BUILDING
    assert len(rows[0]["ADDRESS1"]) == 100
    failures = _failing_check(tmp_path / "over", rows)
    assert failures == {"extract.text_within_width": "longest value per column over its width"}


def test_a_supplementary_character_counts_as_two_inside_the_max_column(tmp_path):
    rows = default_rows()
    rows[0]["IMPROVEMENT_RECOMMENDATIONS"] = "x" * 4450 + BUILDING
    obs = _build(tmp_path / "long", rows=rows)["observations"]["table"]
    assert obs["longest_text_per_column"]["IMPROVEMENT_RECOMMENDATIONS"] == 4452      # 4,451 characters
    assert obs["cells_over_sql_bounded_width"] == {"IMPROVEMENT_RECOMMENDATIONS": 2}
    # 3,999 characters and one supplementary character are 4,001 units: over the bounded limit, counted.
    rows = default_rows()
    rows[0]["IMPROVEMENT_RECOMMENDATIONS"] = "x" * 3999 + BUILDING
    assert _build(tmp_path / "edge", rows=rows)["observations"]["table"]["cells_over_sql_bounded_width"] == {"IMPROVEMENT_RECOMMENDATIONS": 2}
    # The width of 8,000 is in the same units: 7,998 and one fit, 7,999 and one do not.
    rows = default_rows()
    rows[0]["IMPROVEMENT_RECOMMENDATIONS"] = "x" * 7998 + BUILDING
    assert _build(tmp_path / "full", rows=rows)["summary"]["blocking_failed"] == 0
    rows = default_rows()
    rows[0]["IMPROVEMENT_RECOMMENDATIONS"] = "x" * 7999 + BUILDING
    assert "extract.text_within_width" in _failing_check(tmp_path / "over", rows)


def test_build_report_and_manifest_hold_no_address(tmp_path):
    _build(tmp_path)
    report = (tmp_path / "results" / "BUILD_REPORT.md").read_text()
    assert "(withheld)" in report
    for name in ("manifest.json", "BUILD_REPORT.md"):
        text = (tmp_path / "results" / name).read_text()
        assert "TEST HOUSE" not in text and "THE OLD MILL" not in text and "TEST STREET" not in text and "FK10" not in text and "ALLOA" not in text


def _read(tmp_path, spec, zones=None, **release):
    tmp_path.mkdir(parents=True, exist_ok=True)
    registry = make_release(tmp_path, rows=spec, **release)
    reg = load_registry(registry, tmp_path / "sources")
    report = Report()
    quarter_end = dt.date.fromisoformat(str(reg.release["quarter_end"]))
    return reg, report, lambda: read_member(reg.root / reg.member["file"], reg.member, col.load_published(), output.load_schema(col.SCHEMA),
                                            zones or {2001: {"S01000416"}, 2011: {"S01006982"}}, "TEST", quarter_end, report)


def _failing_check(tmp_path, spec, **release):
    reg, report, read = _read(tmp_path, spec, **release)
    with pytest.raises(BuildStopped):
        read()
    return {c.name: c.detail for c in report.blocking_failures}


def test_the_domestic_header_fails(tmp_path):
    """The domestic extract calls the third address line ADDRESS3. A file with that header is
    not this extract."""
    names = list(NAMES)
    names[names.index("POST_TOWN")] = "ADDRESS3"
    rows = [[r[n] for n in NAMES] for r in default_rows()]
    failures = _failing_check(tmp_path, dict(rows=rows, names=names))
    assert list(failures) == ["extract.header_names"]


def test_wrong_label_row_fails(tmp_path):
    labels = list(LABELS)
    labels[5] = "POST_TOWN"
    failures = _failing_check(tmp_path, dict(rows=default_rows(), labels=labels))
    assert list(failures) == ["extract.header_labels"]


def test_37_fields_fails(tmp_path):
    names = NAMES[:-1]
    rows = [[r[n] for n in names] for r in default_rows()]
    failures = _failing_check(tmp_path, dict(rows=rows, names=names))
    assert "extract.header_names" in failures


def test_non_utf8_byte_fails(tmp_path):
    good = default_rows()
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(NAMES); w.writerow(LABELS)
    for r in good:
        w.writerow([r[n] for n in NAMES])
    raw = b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8").replace(b"ALLOA", b"ALL\xd3A")
    failures = _failing_check(tmp_path, dict(rows=good, raw_bytes=raw))
    assert list(failures) == ["extract.utf8"]


def test_created_at_after_the_release_quarter_fails(tmp_path):
    rows = default_rows()
    rows[2]["CREATED_AT"] = "01/01/2025 00:00:00"
    failures = _failing_check(tmp_path, rows)
    assert "extract.created_at_within_release" in failures and "row 3" in failures["extract.created_at_within_release"]
    # The last second of the quarter is inside it.
    rows[2]["CREATED_AT"] = "31/12/2024 23:59:59"
    reg, report, read = _read(tmp_path / "edge", rows)
    read()
    assert not report.blocking_failures


def test_historic_in_capitals_fails(tmp_path):
    rows = default_rows()
    rows[0]["HISTORIC"] = "TRUE"
    failures = _failing_check(tmp_path, rows)
    assert "extract.derived_values_parse" in failures and "HISTORIC" in failures["extract.derived_values_parse"]


def test_repeated_rrn_fails(tmp_path):
    rows = default_rows()
    rows[3]["REPORT_REFERENCE_NUMBER"] = rows[0]["REPORT_REFERENCE_NUMBER"]
    assert "extract.rrn_unique_in_file" in _failing_check(tmp_path, rows)


def test_malformed_date_and_non_integer_floor_area_stop_the_build(tmp_path):
    rows = default_rows()
    rows[0]["LODGEMENT_DATE"] = "2024-3-1"
    rows[1]["FLOOR_AREA"] = "85.5"
    rows[2]["INSPECTION_DATE"] = "01/03/2024"
    detail = _failing_check(tmp_path, rows)["extract.derived_values_parse"]
    assert "LODGEMENT_DATE row 1" in detail and "FLOOR_AREA row 2" in detail and "INSPECTION_DATE row 3" in detail


@pytest.mark.parametrize("column", ["POTENTIAL_ENERGY_PERFORMANCE_RATING", "ASSET_RATING"])
def test_data_removed_in_other_capitals_stops_the_build(tmp_path, column):
    rows = default_rows()
    rows[0][column] = "Data Removed"
    failures = _failing_check(tmp_path, rows)
    assert "extract.data_removed_ratings" in failures and f"{column} row 1" in failures["extract.data_removed_ratings"]


@pytest.mark.parametrize("rating, band", [("POTENTIAL_ENERGY_PERFORMANCE_RATING", "POTENTIAL_ENERGY_PERFORMANCE_BAND"), ("ASSET_RATING", "ASSET_RATING_BAND")])
def test_a_rating_and_its_band_must_agree_on_data_removed(tmp_path, rating, band):
    rows = default_rows()
    rows[0][rating] = "Data removed"            # the band stays a letter
    failures = _failing_check(tmp_path / "rating", rows)
    assert list(failures) == ["extract.data_removed_pairs"] and f"{rating} row 1" in failures["extract.data_removed_pairs"]
    rows = default_rows()
    rows[0][band] = "Data removed"              # the rating stays a number
    failures = _failing_check(tmp_path / "band", rows)
    assert list(failures) == ["extract.data_removed_pairs"]


def test_data_removed_in_a_required_number_stops_the_build(tmp_path):
    rows = default_rows()
    rows[0]["FLOOR_AREA"] = "Data removed"
    rows[1]["BUILDING_EMISSIONS"] = "Data removed"
    detail = _failing_check(tmp_path, rows)["extract.derived_values_parse"]
    assert "FLOOR_AREA row 1" in detail and "BUILDING_EMISSIONS row 2" in detail


def test_well_formed_zone_not_in_list_fails_the_build(tmp_path):
    rows = default_rows()
    rows[0]["DATA_ZONE"] = "S01999999 (Nowhere)"
    with pytest.raises(BuildStopped) as stop:
        _build(tmp_path, rows=rows)
    assert "datazone_2001_status.no_unknown_code" in str(stop.value)
    assert not (tmp_path / "results" / "manifest.json").exists()


def test_changed_member_byte_and_wrong_row_pin_fail(tmp_path):
    registry = make_release(tmp_path)
    path = tmp_path / "sources" / MEMBER
    data = path.read_bytes()
    path.write_bytes(data.replace(b"Natural Gas", b"natural Gas", 1))
    with pytest.raises(BuildStopped) as stop:
        pipeline.build(results=tmp_path / "results", registry_path=registry, source_root=tmp_path / "sources", log=lambda *a: None)
    assert f"source.{MEMBER}" in str(stop.value)
    tmp2 = tmp_path / "second"
    tmp2.mkdir()
    registry2 = make_release(tmp2, pin_rows=6)
    with pytest.raises(BuildStopped) as stop:
        pipeline.build(results=tmp2 / "results", registry_path=registry2, source_root=tmp2 / "sources", log=lambda *a: None)
    assert "extract.rows" in str(stop.value)


def test_verify_archive_hashes_the_archive(tmp_path):
    registry = make_release(tmp_path)
    (tmp_path / "sources" / "epc_test" / "archive.7z").write_bytes(b"changed")
    pipeline.build(results=tmp_path / "results", registry_path=registry, source_root=tmp_path / "sources", log=lambda *a: None)
    with pytest.raises(BuildStopped) as stop:
        pipeline.build(results=tmp_path / "results2", registry_path=registry, source_root=tmp_path / "sources", verify_archive=True, log=lambda *a: None)
    assert "archive.7z" in str(stop.value)


def test_a_registry_with_one_member_and_no_year_loads(tmp_path):
    registry = make_release(tmp_path)
    reg = load_registry(registry, tmp_path / "sources")
    assert "year" not in reg.member and reg.member["file"] == MEMBER and len(reg.members) == 1


def test_a_registry_with_two_members_or_no_quarter_end_is_refused(tmp_path):
    member = {"file": MEMBER, "sha256": "0" * 64, "bytes": 1, "rows": 1}
    two = make_release(tmp_path / "two", members=[member, dict(member, file="epc_test/extracted/second.csv")])
    with pytest.raises(ValueError, match="names 2 members"):
        load_registry(two, tmp_path / "two" / "sources")
    none = make_release(tmp_path / "none", members=[])
    with pytest.raises(ValueError, match="names 0 members"):
        load_registry(none, tmp_path / "none" / "sources")
    path = make_release(tmp_path / "quarter")
    raw = yaml.safe_load(path.read_text())
    del raw["release"]["quarter_end"]
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    with pytest.raises(ValueError, match="quarter_end"):
        load_registry(path, tmp_path / "quarter" / "sources")


def test_padded_uprn_gives_the_same_integer(tmp_path):
    rows = default_rows()
    rows[0]["OSG_REFERENCE_NUMBER"] = "000035000001"
    rows[1]["OSG_REFERENCE_NUMBER"] = "35000001"
    rows[1]["BUILDING_REFERENCE_NUMBER"] = rows[0]["BUILDING_REFERENCE_NUMBER"]   # one building, two certificates
    _build(tmp_path, rows=rows)
    saved = _saved(tmp_path)
    assert saved.loc[1, "uprn_osg"] == saved.loc[2, "uprn_osg"] == 35000001
    assert saved.loc[1, "OSG_REFERENCE_NUMBER"] == "000035000001"


def test_generated_schema_matches_the_file():
    assert col.schema(col.load_published()) == yaml.safe_load(col.SCHEMA.read_text())
    assert len(col.load_published()) == 38 and "POST_TOWN" in NAMES and "ADDRESS3" not in NAMES


def test_datazone_lists_read(tmp_path):
    registry = make_release(tmp_path)
    reg = load_registry(registry, tmp_path / "sources")
    assert read_zone_list(reg.root / reg.datazone_lists[2001]["file"], reg.datazone_lists[2001]) == ["S01000001", "S01000416", "S01006505"]
    assert read_zone_list(reg.root / reg.datazone_lists[2011]["file"], reg.datazone_lists[2011]) == ["S01006506", "S01006982", "S01013481"]


def test_uprn_not_one_to_one_fails_the_build(tmp_path):
    rows = default_rows()
    rows[1]["OSG_REFERENCE_NUMBER"] = rows[0]["OSG_REFERENCE_NUMBER"]   # one Gazetteer UPRN, two register numbers
    with pytest.raises(BuildStopped) as stop:
        _build(tmp_path, rows=rows)
    assert "table.uprn_one_to_one" in str(stop.value)


def test_a_nullable_column_missing_in_every_row_builds(tmp_path):
    rows = default_rows()
    for r in rows:
        r["REPORT_REFERENCE_NUMBER"] = ""
        r["POSTCODE"] = " \t"
        r["DATA_ZONE_2011"] = ""
        r["POTENTIAL_ENERGY_PERFORMANCE_RATING"] = r["POTENTIAL_ENERGY_PERFORMANCE_BAND"] = "Data removed"
    manifest = _build(tmp_path, rows=rows)
    assert manifest["summary"]["blocking_failed"] == 0
    saved = _saved(tmp_path)
    assert saved["rrn"].isna().all() and saved["pc_norm"].isna().all() and saved["datazone_2011"].isna().all()
    assert saved["potential_energy_performance_rating_num"].isna().all() and (saved["datazone_2011_status"] == "empty").all()


def test_observations_count_what_the_plan_says_the_build_counts(tmp_path):
    rows = default_rows()
    rows.append(make_row(8, BUILDING_REFERENCE_NUMBER=rows[0]["BUILDING_REFERENCE_NUMBER"], OSG_REFERENCE_NUMBER=rows[0]["OSG_REFERENCE_NUMBER"],
                         HISTORIC="True", POSTCODE="FK10 9ZZ", INSPECTION_DATE=rows[0]["INSPECTION_DATE"], LOCAL_AUTHORITY="00EM",
                         LODGEMENT_DATE="2024-02-01", CURRENT_ENERGY_PERFORMANCE_RATING="66"))
    obs = _build(tmp_path, rows=rows)["observations"]["table"]
    assert obs["uprn_sepcr_with_two_or_more_pc_norm"] == 1 and obs["same_uprn_sepcr_same_inspection_day_pairs"] == 1
    assert obs["same_uprn_osg_same_inspection_day_pairs"] == 1 and obs["local_authority_not_scottish_rows"] == 1
    assert obs["cells_with_tab"] == {"ADDRESS1": 1, "POSTCODE": 1} and obs["cells_with_replacement_character"] == {"ADDRESS2": 1}
    assert obs["postcode_with_tab_rows"] == 1 and obs["pc_norm_with_other_than_letters_and_digits"] == 0
    assert obs["uprn_osg_empty_rows"] == 1 and obs["rrn_empty_rows"] == 1 and obs["uprn_sepcr_all_historic"] == 2
    assert obs["lodgement_before_inspection_rows"] == 1 and obs["rating_differs_from_rounded_emissions_rows"] == 1
    assert obs["geography_columns_all_empty_rows"] == 1 and obs["meets_2002_standard_empty_rows"] == 1
    assert obs["band_differs_from_cut_of_rating_rows"] == 0 and obs["current_rating_negative_rows"] == 1
    assert obs["rows_per_created_year"] == {"2013": 1, "2015": 1, "2024": 6}


def test_a_failed_rebuild_keeps_the_last_accepted_build(tmp_path):
    results = tmp_path / "results"
    first = tmp_path / "first"
    first.mkdir()
    registry = make_release(first)
    manifest = pipeline.build(results=results, registry_path=registry, source_root=first / "sources", log=lambda *a: None)
    before = {p.name: p.read_bytes() for p in results.iterdir()}
    assert set(before) == OUTPUT_FILES
    # A late failure: the whole-table check on an unknown data zone, after both files are written.
    second = tmp_path / "second"
    second.mkdir()
    rows = default_rows()
    rows[0]["DATA_ZONE"] = "S01999999 (Nowhere)"
    registry2 = make_release(second, rows=rows)
    with pytest.raises(BuildStopped):
        pipeline.build(results=results, registry_path=registry2, source_root=second / "sources", log=lambda *a: None)
    after = {p.name: p.read_bytes() for p in results.iterdir()}
    assert after == before
    assert json.loads(after["manifest.json"])["parquet"]["sha256"] == manifest["parquet"]["sha256"]
    # An early failure: the reader stops before anything is written.
    third = tmp_path / "third"
    third.mkdir()
    bad = default_rows()
    bad[0]["HISTORIC"] = "TRUE"
    registry3 = make_release(third, rows=bad)
    with pytest.raises(BuildStopped):
        pipeline.build(results=results, registry_path=registry3, source_root=third / "sources", log=lambda *a: None)
    assert {p.name: p.read_bytes() for p in results.iterdir()} == before


def test_a_failed_promotion_rolls_back_to_the_accepted_build(tmp_path, monkeypatch):
    import os
    results = tmp_path / "results"
    first = tmp_path / "first"
    first.mkdir()
    registry = make_release(first)
    pipeline.build(results=results, registry_path=registry, source_root=first / "sources", log=lambda *a: None)
    before = {p.name: p.read_bytes() for p in results.iterdir()}
    second = tmp_path / "second"
    second.mkdir()
    rows = default_rows()
    rows[0]["MAIN_HEATING_FUEL"] = "Oil"
    registry2 = make_release(second, rows=rows)
    real_replace = os.replace
    failures = []

    def locked_csv(times):
        """The final CSV path refuses the first `times` moves onto it, as a file lock would."""
        def replace(src, dst):
            if str(dst).endswith(f"results/{TABLE}.csv.gz") and len(failures) < times:
                failures.append(dst)
                raise PermissionError("locked")
            return real_replace(src, dst)
        return replace

    # A lock that clears: the second move fails after the Parquet is in place, the rollback
    # succeeds, and results holds the accepted build exactly as before, with nothing left over.
    monkeypatch.setattr(pipeline.os, "replace", locked_csv(1))
    with pytest.raises(PermissionError):
        pipeline.build(results=results, registry_path=registry2, source_root=second / "sources", log=lambda *a: None)
    assert {p.name: p.read_bytes() for p in results.iterdir()} == before
    # A lock that persists: the rollback cannot restore the CSV either, so the accepted files
    # are left across results and the previous folder, nothing deleted, and the error names both.
    failures.clear()
    monkeypatch.setattr(pipeline.os, "replace", locked_csv(10))
    with pytest.raises(RuntimeError) as stop:
        pipeline.build(results=results, registry_path=registry2, source_root=second / "sources", log=lambda *a: None)
    previous = [p for p in results.iterdir() if p.name.startswith(".previous_")]
    assert len(previous) == 1 and str(previous[0]) in str(stop.value) and str(results) in str(stop.value)
    kept = {p.name: p.read_bytes() for p in previous[0].iterdir()}
    restored = {p.name: p.read_bytes() for p in results.iterdir() if p.is_file()}
    recoverable = dict(restored, **kept)
    assert {k: recoverable[k] for k in before} == before, "every accepted file is in one of the two folders"
    for name in kept:
        real_replace(previous[0] / name, results / name)
    previous[0].rmdir()
    # Without the fault the same build promotes, and the accepted generation changes as a whole.
    monkeypatch.setattr(pipeline.os, "replace", real_replace)
    manifest = pipeline.build(results=results, registry_path=registry2, source_root=second / "sources", log=lambda *a: None)
    now = {p.name: p.read_bytes() for p in results.iterdir()}
    assert set(now) == set(before) and now[f"{TABLE}.parquet"] != before[f"{TABLE}.parquet"]
    assert json.loads(now["manifest.json"])["parquet"]["sha256"] == manifest["parquet"]["sha256"]

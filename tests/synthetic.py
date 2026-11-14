"""A synthetic release: a few rows in the publisher's exact shape (one file, two header rows,
byte order mark, CRLF, 38 fields), plus the two reference lists and a registry that pins them by
hash. Every test that needs source files builds one of these in a temporary folder."""

from __future__ import annotations

import csv
import hashlib
import io
import struct
from pathlib import Path

import yaml

from epc_nd_ingest import columns as col
from epc_nd_ingest.core.sources import PACKAGE

PUBLISHED = col.load_published()
NAMES = [c["name"] for c in PUBLISHED]
LABELS = [c["label"] for c in PUBLISHED]
ZONES_2001 = ["S01000001", "S01000416", "S01006505"]
ZONES_2011 = ["S01006506", "S01006982", "S01013481"]
MEMBER = "epc_test/extracted/extract.csv"
YEAR = 2024


def make_row(n: int, year: int = YEAR, **overrides) -> dict:
    """One valid certificate row, every published column filled as the extract fills it, then
    overrides applied."""
    row = {name: "" for name in NAMES}
    row.update({
        "HISTORIC": "False", "BUILDING_REFERENCE_NUMBER": str(1000000000 + n), "OSG_REFERENCE_NUMBER": str(35000000 + n),
        "ADDRESS1": f"UNIT {n} TEST HOUSE", "ADDRESS2": "TEST STREET ", "POST_TOWN": "ALLOA", "POSTCODE": "FK10 1AA",
        "INSPECTION_DATE": f"{year}-03-0{1 + n % 9}", "LODGEMENT_DATE": f"{year}-03-1{n % 10}",
        "PROPERTY_TYPE_SHORT": "Office/Workshop", "PROPERTY_TYPE": "Offices and Workshop businesses",
        "FLOOR_AREA": "250", "CURRENT_ENERGY_PERFORMANCE_RATING": "65", "CURRENT_ENERGY_PERFORMANCE_BAND": "E+",
        "POTENTIAL_ENERGY_PERFORMANCE_RATING": "40.00", "POTENTIAL_ENERGY_PERFORMANCE_BAND": "C",
        "NEW_BUILD_ENERGY_PERFORMANCE_RATING": "20", "NEW_BUILD_ENERGY_PERFORMANCE_BAND": "B+", "MEETS_2002_STANDARD": "N",
        "ASSET_RATING": "70", "ASSET_RATING_BAND": "C", "BUILDING_EMISSIONS": "65.21", "RENEWABLE_SOURCES": "None",
        "ELECTRICITY_SOURCE": "Grid supplied", "MAIN_HEATING_FUEL": "Natural Gas",
        "BUILDING_ENVIRONMENT": "Heating and Natural Ventilation", "PRIMARY_ENERGY_VALUE": "380",
        "APPROXIMATE_ENERGY_USE": "210", "IMPROVEMENT_RECOMMENDATIONS": "EPC-L5; LOW; SHORT; Consider replacing T8 lamps with retrofit T5 conversion kit. ",
        "LOCAL_AUTHORITY": "00QF", "DATA_ZONE": "S01000416 (Ythsie)", "CONSTITUENCY": "00QFMB", "CONSTITUENCY_LABEL": "Clackmannanshire South",
        "TRANSACTION_TYPE": "Mandatory issue (Property to let)", "TARGET_EMISSIONS": "20.05",
        "DATA_ZONE_2011": "S01006982 (Ythsie - 05)", "CREATED_AT": f"1{n % 10}/03/{year} 10:{n % 60:02d}:00",
        "REPORT_REFERENCE_NUMBER": f"{year}-{n:04d}-0000-0000-0001",
    })
    row.update(overrides)
    return row


def default_rows() -> list:
    """Seven rows that between them carry the awkward cells of the real extract: a superseded
    certificate with no RRN, a tab inside an address and around a postcode, the replacement
    character, an empty UPRN, values that are not data zones, 'Data removed' in both rating
    pairs, a cut band, a minus zero, a negative rating, a cell longer than 4,000 characters."""
    return [
        make_row(1),
        make_row(2, HISTORIC="True", REPORT_REFERENCE_NUMBER=""),
        make_row(3, OSG_REFERENCE_NUMBER="", ADDRESS1="THE OLD MILL\t", ADDRESS2="CAF� ROW", POSTCODE=" \tFK10 1AB",
                 DATA_ZONE="00QQMB ()", DATA_ZONE_2011="NA (NA)"),
        make_row(4, OSG_REFERENCE_NUMBER="906700556768", LOCAL_AUTHORITY="", DATA_ZONE="", CONSTITUENCY="", CONSTITUENCY_LABEL="",
                 DATA_ZONE_2011="", POSTCODE="g12 8qq ", MEETS_2002_STANDARD="", year=2015),
        make_row(5, HISTORIC="True", POTENTIAL_ENERGY_PERFORMANCE_RATING="Data removed", POTENTIAL_ENERGY_PERFORMANCE_BAND="Data removed",
                 ASSET_RATING="Data removed", ASSET_RATING_BAND="Data removed", year=2013),
        make_row(6, CURRENT_ENERGY_PERFORMANCE_RATING="-12", CURRENT_ENERGY_PERFORMANCE_BAND="Carbon Neu", BUILDING_EMISSIONS="-12.4",
                 PRIMARY_ENERGY_VALUE="-55", NEW_BUILD_ENERGY_PERFORMANCE_RATING="-0", POTENTIAL_ENERGY_PERFORMANCE_RATING="-20.00",
                 POTENTIAL_ENERGY_PERFORMANCE_BAND="Carbon Neu", FLOOR_AREA="138037"),
        make_row(7, IMPROVEMENT_RECOMMENDATIONS="EPC-H1; HIGH; LONG; " + "x" * 4430 + " ", CONSTITUENCY_LABEL="Steòrnabhagh a Deas"),
    ]


def write_extract(path: Path, rows: list, names: list = None, labels: list = None, raw_bytes: bytes = None) -> None:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(names if names is not None else NAMES)
    writer.writerow(labels if labels is not None else LABELS)
    for r in rows:
        writer.writerow([r[n] for n in (names if names is not None else NAMES)] if isinstance(r, dict) else r)
    body = b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")
    if raw_bytes is not None:
        body = raw_bytes
    path.write_bytes(body)


def write_dbf(path: Path, codes: list, column: str = "DataZone") -> None:
    """A minimal dBASE III file with one character field."""
    width = 9
    header_length = 32 + 32 + 1
    record_length = 1 + width
    header = bytearray(32)
    header[0] = 0x03
    struct.pack_into("<IHH", header, 4, len(codes), header_length, record_length)
    field = bytearray(32)
    field[0:len(column)] = column.encode("ascii")
    field[11] = ord("C")
    field[16] = width
    body = b"".join(b" " + code.encode("ascii").ljust(width) for code in codes)
    path.write_bytes(bytes(header) + bytes(field) + b"\x0d" + body + b"\x1a")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_release(root: Path, rows=None, zones_2001: list = ZONES_2001, zones_2011: list = ZONES_2011,
                 pin_rows: int = None, quarter_end: str = "2024-12-31", members: list = None) -> Path:
    """Write a synthetic source tree under `root` and return the path of its registry. `rows` is
    a list of rows (dict or raw list), or a dict with `rows` and any of `names`, `labels`,
    `raw_bytes` for a deliberately broken file. `members` replaces the registry's member list,
    for a registry the loader must refuse."""
    spec = rows if isinstance(rows, dict) else {"rows": rows if rows is not None else default_rows()}
    source = root / "sources"
    (source / "epc_test" / "extracted").mkdir(parents=True)
    (source / "datazones").mkdir()
    path = source / MEMBER
    write_extract(path, spec["rows"], spec.get("names"), spec.get("labels"), spec.get("raw_bytes"))
    member = {"file": MEMBER, "sha256": sha256_file(path), "bytes": path.stat().st_size,
              "rows": pin_rows if pin_rows is not None else len(spec["rows"])}
    archive = source / "epc_test" / "archive.7z"
    archive.write_bytes(b"not a real archive")
    note = source / "epc_test" / "publication_note.pdf"
    note.write_bytes(b"%PDF-1.4 test")
    dbf = source / "datazones" / "SG_SIMD_2012.dbf"
    write_dbf(dbf, zones_2001)
    lookup = source / "datazones" / "DataZone2011_lookup.csv"
    lookup.write_text("DZ2011_Code,DZ2011_Name\n" + "".join(f"{c},Zone {c}\n" for c in zones_2011), encoding="cp1252")
    base = yaml.safe_load((PACKAGE / "sources.yaml").read_text())
    registry = dict(base)
    registry["release"] = {"epc_release": "TEST", "extracted_from_register": "2025-01-15", "downloaded": "2025-02-01",
                           "quarter_end": quarter_end,
                           "archive": {"file": "epc_test/archive.7z", "sha256": sha256_file(archive), "bytes": archive.stat().st_size},
                           "note": {"file": "epc_test/publication_note.pdf", "sha256": sha256_file(note), "bytes": note.stat().st_size},
                           "members": members if members is not None else [member]}
    registry["datazone_lists"] = {
        2001: dict(base["datazone_lists"][2001], file="datazones/SG_SIMD_2012.dbf", sha256=sha256_file(dbf), zones=len(zones_2001)),
        2011: dict(base["datazone_lists"][2011], file="datazones/DataZone2011_lookup.csv", sha256=sha256_file(lookup), zones=len(zones_2011)),
    }
    out = root / "sources.yaml"
    out.write_text(yaml.safe_dump(registry, sort_keys=False, allow_unicode=True))
    return out

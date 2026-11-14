"""Read the extract as text, check its shape, derive the typed columns.

Every published value is kept exactly as the file holds it, trailing spaces and tabs included.
Nothing is read through a float.
"""

from __future__ import annotations

import csv
import datetime as dt
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

from . import columns as col
from .core.checks import Report
from .core.dbf import read_dbf
from .core.text_output import DATE_FORMAT, DecimalDoesNotFit, parse_date, parse_datetime, render_decimal

CREATED_AT_FORMAT = "%d/%m/%Y %H:%M:%S"
DATAZONE = re.compile(r"^S01\d{6}(?=\s|$)")
INTEGER = re.compile(r"^-?\d+$")
NUMBER = re.compile(r"^-?\d+(\.\d+)?$")
RRN = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{4}-\d{4}$")
HISTORIC_VALUES = {"True": True, "False": False}
SAMPLE_ROWS = 3
# The prefix of every check the reader emits. The extract is one file.
LABEL = "extract"
# A character outside the Basic Multilingual Plane, such as an emoji. SQL Server stores it as two
# UTF-16 code units, and an nvarchar(n) holds n units.
SUPPLEMENTARY = "[\U00010000-\U0010FFFF]"

csv.field_size_limit(1 << 24)


def derive_datazone(text: str, zones: set) -> tuple:
    """The code and the status of one DATA_ZONE cell."""
    m = DATAZONE.match(text)
    if m:
        code = m.group(0)
        return code, ("code" if code in zones else "unknown_code")
    if text.strip() == "":
        return None, "empty"
    return None, "not_a_datazone"


def sql_length(values: pd.Series) -> pd.Series:
    """The length of each text as SQL Server counts it for nvarchar: UTF-16 code units. It is the
    number of characters, plus one for each supplementary character. A column's width is in
    these units, so a value that passes the width check fits its column."""
    return values.str.len() + values.str.count(SUPPLEMENTARY)


def norm_postcode(text: str):
    """Upper case, every space (U+0020) and tab (U+0009) removed. None where nothing is left.
    The postcode join applies the same rule to the cohort postcode."""
    cleaned = text.upper().replace(" ", "").replace("\t", "")
    return cleaned or None


def _integer(text: str, what: str) -> int:
    if not INTEGER.match(text.strip()):
        raise ValueError(f"{what}: {text!r} is not an integer")
    return int(text.strip())


def _decimal(text: str, what: str) -> Decimal:
    try:
        value = Decimal(text.strip())
    except InvalidOperation as e:
        raise ValueError(f"{what}: {text!r} is not a number") from e
    if not value.is_finite():
        raise ValueError(f"{what}: {text!r} is not a finite number")
    render_decimal(value)   # raises DecimalDoesNotFit when it does not fit decimal(19,4)
    return value


def _decimal_or_removed(text: str, what: str):
    """A number, or None for the publisher's missing value, spelled exactly."""
    return None if text == col.DATA_REMOVED else _decimal(text, what)


def read_header(path: Path) -> tuple:
    """The two header rows, the byte order mark stripped."""
    with open(path, encoding="utf-8-sig", errors="strict", newline="") as fh:
        reader = csv.reader(fh)
        names = next(reader)
        labels = next(reader)
    return names, labels


def read_member(path: Path, member: dict, published: list, schema: dict, zones: dict, epc_release: str,
                quarter_end: dt.date, report: Report) -> tuple:
    """The extract as a frame with the table's columns, every value typed, plus the raw text of
    three rows (first, middle, last) for the cell-for-cell comparison after read-back.

    Checks, each blocking and named `extract.<check>`: the file decodes as UTF-8; the two header
    rows equal the pinned names and labels; every row has the pinned number of fields; the row
    count equals the pin; no CREATED_AT is later than the last day of the release quarter; the
    dates, flags, integers and decimals the derived columns need all parse; the two rating
    columns that can hold 'Data removed' hold a number or exactly that text, and each agrees with
    its band; no text is longer than its column width; the report reference numbers that are
    present have the published shape and do not repeat.
    """
    label = LABEL
    names = [c["name"] for c in published]
    labels = [c["label"] for c in published]
    try:
        with open(path, encoding="utf-8-sig", errors="strict", newline="") as fh:
            reader = csv.reader(fh)
            header = next(reader)
            label_row = next(reader)
            rows = list(reader)
    except UnicodeDecodeError as e:
        report.add(f"{label}.utf8", False, f"not UTF-8: {e}")
        report.require()
    report.add(f"{label}.utf8", True, "decoded as UTF-8")
    report.equal(f"{label}.header_names", header, names,
                 detail=f"{len(header)} columns as pinned" if header == names else "the first header row differs from the pin")
    report.equal(f"{label}.header_labels", label_row, labels,
                 detail="labels as pinned" if label_row == labels else "the second header row differs from the pin")
    report.require()
    widths = {len(r) for r in rows}
    report.equal(f"{label}.row_width", sorted(widths), [len(names)], detail=f"{len(rows)} rows of {len(names)} fields" if widths == {len(names)} else f"field counts seen: {sorted(widths)}")
    report.equal(f"{label}.rows", len(rows), int(member["rows"]))
    report.require()

    n = len(rows)
    at = {name: i for i, name in enumerate(names)}
    out = {"epc_release": pd.Series([epc_release] * n, dtype="string"),
           "source_row": pd.Series(range(1, n + 1), dtype="Int64")}
    for i, name in enumerate(names):
        out[name] = pd.Series([r[i] for r in rows], dtype="string")

    errors = []

    def attempt(what, fn, values):
        result = []
        for k, v in enumerate(values):
            try:
                result.append(fn(v))
            except (ValueError, DecimalDoesNotFit) as e:
                if len(errors) < 20:
                    errors.append(f"{what} row {k + 1}: {e}")
                result.append(None)
        return result

    # Identifiers.
    rrn_raw = [r[at["REPORT_REFERENCE_NUMBER"]] for r in rows]
    out["rrn"] = pd.Series([v if v != "" else None for v in rrn_raw], dtype="string")
    present = [v for v in rrn_raw if v != ""]
    report.equal(f"{label}.rrn_shape", sum(1 for v in present if not RRN.match(v)), 0,
                 detail=f"{len(present)} present, all 9999-9999-9999-9999-9999" if all(RRN.match(v) for v in present) else "a present RRN has another shape")
    report.equal(f"{label}.rrn_unique_in_file", len(present) - len(set(present)), 0)
    out["uprn_sepcr"] = pd.Series(attempt("BUILDING_REFERENCE_NUMBER", lambda v: _integer(v, "BUILDING_REFERENCE_NUMBER"),
                                          [r[at["BUILDING_REFERENCE_NUMBER"]] for r in rows]), dtype="Int64")
    out["uprn_osg"] = pd.Series(attempt("OSG_REFERENCE_NUMBER", lambda v: None if v.strip() == "" else _integer(v, "OSG_REFERENCE_NUMBER"),
                                        [r[at["OSG_REFERENCE_NUMBER"]] for r in rows]), dtype="Int64")
    out["pc_norm"] = pd.Series([norm_postcode(r[at["POSTCODE"]]) for r in rows], dtype="string")

    # Data zones.
    for source, (code_col, status_col, vintage) in col.DATAZONE_COLUMNS.items():
        pairs = [derive_datazone(r[at[source]], zones[vintage]) for r in rows]
        out[code_col] = pd.Series([p[0] for p in pairs], dtype="string")
        out[status_col] = pd.Series([p[1] for p in pairs], dtype="string")

    # Dates and the flag.
    for source, target in col.DATE_COLUMNS.items():
        out[target] = pd.Series(attempt(source, lambda v: parse_date(v, DATE_FORMAT), [r[at[source]] for r in rows]), dtype=object)
    source, target = col.DATETIME_COLUMN
    created = attempt(source, lambda v: parse_datetime(v, CREATED_AT_FORMAT), [r[at[source]] for r in rows])
    out[target] = pd.Series(created, dtype=object)
    late = [k + 1 for k, v in enumerate(created) if v is not None and v.date() > quarter_end]
    report.equal(f"{label}.created_at_within_release", len(late), 0,
                 detail=f"no CREATED_AT is later than {quarter_end}, the last day of the release quarter" if not late else
                 f"{len(late)} rows have a CREATED_AT later than {quarter_end}; first at row {late[0]}")
    out["historic_flag"] = pd.Series(attempt("HISTORIC", lambda v: HISTORIC_VALUES[v] if v in HISTORIC_VALUES else (_ for _ in ()).throw(ValueError(f"HISTORIC: {v!r} is not True or False")),
                                             [r[at["HISTORIC"]] for r in rows]), dtype="boolean")

    # The publisher's missing value, in the two rating columns that can hold it and their bands.
    # Checked whether or not the column has a typed copy.
    not_a_rating, disagree = [], []
    for rating, band in col.DATA_REMOVED_PAIRS.items():
        for k, r in enumerate(rows):
            value, band_value = r[at[rating]], r[at[band]]
            if value != col.DATA_REMOVED and not NUMBER.match(value):
                if len(not_a_rating) < 20:
                    not_a_rating.append(f"{rating} row {k + 1}: {value!r}")
            if (value == col.DATA_REMOVED) != (band_value == col.DATA_REMOVED):
                if len(disagree) < 20:
                    disagree.append(f"{rating} row {k + 1}: {value!r} with {band} {band_value!r}")
    report.equal(f"{label}.data_removed_ratings", not_a_rating, [],
                 detail=f"every {' and '.join(col.DATA_REMOVED_PAIRS)} cell is a number or exactly '{col.DATA_REMOVED}'" if not not_a_rating else
                 f"cells that are neither a number nor '{col.DATA_REMOVED}' (first {min(len(not_a_rating), 5)} of at most 20 kept): " + "; ".join(not_a_rating[:5]))
    report.equal(f"{label}.data_removed_pairs", disagree, [],
                 detail=f"a rating is '{col.DATA_REMOVED}' exactly when its band is" if not disagree else
                 f"a rating and its band disagree (first {min(len(disagree), 5)} of at most 20 kept): " + "; ".join(disagree[:5]))

    # Numbers.
    for source, target in col.INT_COLUMNS.items():
        out[target] = pd.Series(attempt(source, lambda v, s=source: _integer(v, s), [r[at[source]] for r in rows]), dtype="Int64")
    for source, target in col.DECIMAL_COLUMNS.items():
        out[target] = pd.Series(attempt(source, lambda v, s=source: _decimal(v, s), [r[at[source]] for r in rows]), dtype=object)
    for source, target in col.NULLABLE_DECIMAL_COLUMNS.items():
        out[target] = pd.Series(attempt(source, lambda v, s=source: _decimal_or_removed(v, s), [r[at[source]] for r in rows]), dtype=object)

    report.equal(f"{label}.derived_values_parse", errors, [],
                 detail="every date, flag, integer and decimal the derived columns need parses" if not errors else
                 f"values that do not parse (first {min(len(errors), 5)} of at most 20 kept): " + "; ".join(errors[:5]))
    report.require()

    frame = pd.DataFrame(out)[[f["name"] for f in schema["fields"]]]

    # Widths: no text longer than the width the schema accepts, counted as SQL Server counts it.
    too_long = {}
    for f in schema["fields"]:
        if f["type"] == "string":
            longest = sql_length(frame[f["name"]]).max() if n else 0
            longest = 0 if pd.isna(longest) else int(longest)   # a nullable column can be missing in every row
            if longest > f["width"]:
                too_long[f["name"]] = longest
    report.equal(f"{label}.text_within_width", too_long, {}, detail="every text value fits the width its column accepts, in UTF-16 code units" if not too_long else "longest value per column over its width")
    report.require()

    picks = sorted({1, (n + 1) // 2, n}) if n else []
    samples = [{"source_row": k, "cells": dict(zip(names, rows[k - 1]))} for k in picks]
    return frame, samples


def read_zone_list(path: Path, spec: dict) -> list:
    """The codes of one vintage's reference list."""
    if spec["format"] == "dbf":
        return [r[spec["code_column"]] for r in read_dbf(path)]
    with open(path, encoding=spec["encoding"], newline="") as fh:
        return [r[spec["code_column"]] for r in csv.DictReader(fh)]

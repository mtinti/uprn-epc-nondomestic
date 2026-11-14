"""Draft epc_nd_ingest/column_descriptions.yaml from the pinned publication note.

    python3 -P tools/extract_note_dictionary.py <publication_note.pdf> <out.yaml>

The note's data dictionary (pages 7 to 12 of the Q3 2026 note) defines all 38 published fields,
each as a label, the machine name (`*` marks a Scotland-only field) and a description. This
script finds each machine name in published order, takes the text up to the next entry as its
description, strips the next entry's label and the page headers, and writes one YAML entry per
published column with attribution `note`, the page and the note's hash. The key and derived
columns get their schema description with attribution `project`. The draft is reviewed by eye
against the PDF before it is committed, and the review is recorded in docs/reviews/. Run with
-P: the PDF is a download.

    python3 -P tools/extract_note_dictionary.py <publication_note.pdf> --check

compares the committed file with what the script would write and exits 1 on a difference, so a
description edited away from the note's wording is noticed.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import yaml
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from epc_nd_ingest import columns as col  # noqa: E402

OUT = ROOT / "epc_nd_ingest" / "column_descriptions.yaml"
FIRST_PAGE, LAST_PAGE = 7, 12
PAGE_HEADER = re.compile(r"^\d+ Data element UK descriptor Description ")
END = "Further information"
# The note's own label for each entry, typed from the PDF. ADDRESS2 and POST_TOWN have none: they
# stand under the label of ADDRESS1. The text between two entries is cut at these exact phrases.
NOTE_LABELS = {
    "HISTORIC": "Historical", "BUILDING_REFERENCE_NUMBER": "Property UPRN", "OSG_REFERENCE_NUMBER": "OSG UPRN",
    "ADDRESS1": "Property Address", "POSTCODE": "Postcode", "INSPECTION_DATE": "Date of Assessment",
    "LODGEMENT_DATE": "Date of Certificate", "PROPERTY_TYPE_SHORT": "Property Short Description", "PROPERTY_TYPE": "Property Type",
    "FLOOR_AREA": "Total floor area", "CURRENT_ENERGY_PERFORMANCE_RATING": "Current Energy Performance Rating",
    "CURRENT_ENERGY_PERFORMANCE_BAND": "Energy Band", "POTENTIAL_ENERGY_PERFORMANCE_RATING": "Potential Energy Performance Rating",
    "POTENTIAL_ENERGY_PERFORMANCE_BAND": "Potential Band", "NEW_BUILD_ENERGY_PERFORMANCE_RATING": "New Build Benchmark Rating",
    "NEW_BUILD_ENERGY_PERFORMANCE_BAND": "New Build Benchmark Band", "MEETS_2002_STANDARD": "Compliant 2002",
    "ASSET_RATING": "Comparative Asset Rating", "ASSET_RATING_BAND": "Comparative Energy Band", "BUILDING_EMISSIONS": "EPC Rating BER",
    "RENEWABLE_SOURCES": "Renewable Energy Source", "ELECTRICITY_SOURCE": "Electricity_Source", "MAIN_HEATING_FUEL": "Main Heating Fuel",
    "BUILDING_ENVIRONMENT": "Building Environment", "PRIMARY_ENERGY_VALUE": "Actual Building Data Primary Energy Indicator",
    "APPROXIMATE_ENERGY_USE": "Actual Building Data Approx Energy Use", "IMPROVEMENT_RECOMMENDATIONS": "Recommendations",
    "LOCAL_AUTHORITY": "Local Authority Identifier", "DATA_ZONE": "Data Zone", "CONSTITUENCY": "Ward Code", "CONSTITUENCY_LABEL": "Ward Name",
    "TRANSACTION_TYPE": "Transaction Type", "TARGET_EMISSIONS": "EPC Rating TER", "DATA_ZONE_2011": "Data Zone 2011",
    "CREATED_AT": "Lodgement Date", "REPORT_REFERENCE_NUMBER": "RRN",
}
REVIEW = {
    "date": "2026-11-14",
    "by": "Michele Tinti with Claude Fable 5.2 (AI-assisted)",
    "record": "docs/reviews/2026-11-14-column-descriptions.md",
    "method": "Every note entry compared with the extracted text of the pinned PDF, page by page. Labels cut at the seams by "
              "the exact phrases typed from the PDF. The committed file is compared with a fresh extraction by --check.",
    "notes": {
        "MEETS_2002_STANDARD": "The entry starts on page 8 and ends on page 9. The page given is where it starts.",
        "OSG_REFERENCE_NUMBER": "The note says 9 to 12 digits. The file holds 8-digit values too.",
        "CURRENT_ENERGY_PERFORMANCE_BAND": "The note says A+ is 0 or lower. In the file a rating below 0 has the band 'Carbon Neu', a value the note does not list.",
        "POTENTIAL_ENERGY_PERFORMANCE_RATING": "The note's section on 'data removed' says when this field holds that text.",
        "CONSTITUENCY": "The entry's wording is the publisher's: the field holds the ward code.",
        "REPORT_REFERENCE_NUMBER": "'of and EPC' is the note's text.",
        "INSPECTION_DATE": "'energy performance of the building was undertaken' is the note's text.",
    },
}


def dictionary_text(pdf: Path) -> tuple:
    """The dictionary pages as one text with single spaces, the page headers removed, and the
    character offset at which each page starts."""
    reader = PdfReader(str(pdf))
    text, starts = "", {}
    for number in range(FIRST_PAGE, LAST_PAGE + 1):
        page = re.sub(r"\s+", " ", reader.pages[number - 1].extract_text() or "").strip()
        if not PAGE_HEADER.match(page + " "):
            raise ValueError(f"page {number} does not start with the dictionary's header")
        page = PAGE_HEADER.sub("", page + " ")
        starts[number] = len(text)
        text += page
    return text, starts


def entries(pdf: Path) -> list:
    names = [c["name"] for c in col.load_published()]
    text, starts = dictionary_text(pdf)
    found, cursor = [], 0
    for name in names:
        m = re.compile(r"(?<![A-Z_0-9])" + re.escape(name) + r"(\*?) ").search(text, cursor)
        if not m:
            raise ValueError(f"{name} is not in the note's dictionary after position {cursor}")
        found.append((name, m.start(), m.end(), bool(m.group(1))))
        cursor = m.end()
    end = text.index(END, cursor)
    out = []
    for k, (name, start, body, starred) in enumerate(found):
        stop = found[k + 1][1] if k + 1 < len(found) else end
        description = text[body:stop].strip()
        nxt = NOTE_LABELS.get(found[k + 1][0]) if k + 1 < len(found) else None
        if nxt:
            if not description.endswith(nxt):
                raise ValueError(f"{name}: the text before {found[k + 1][0]} does not end with its label {nxt!r}")
            description = description[: -len(nxt)].strip()
        page = max(n for n, offset in starts.items() if offset <= start)
        entry = {"name": name, "attribution": "note", "note_name": name, "scotland_only": starred, "page": page, "text": description}
        if name in NOTE_LABELS:
            entry["note_label"] = NOTE_LABELS[name]
        out.append(entry)
    return out


def document(pdf: Path) -> dict:
    registry_note = yaml.safe_load((ROOT / "epc_nd_ingest" / "sources.yaml").read_text())["release"]["note"]
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    if sha != registry_note["sha256"]:
        raise ValueError("the PDF is not the note the registry pins")
    project = [{"name": f["name"], "attribution": "project", "text": f["description"]} for f in col.KEY_FIELDS]
    derived = [{"name": f["name"], "attribution": "project", "text": f["description"]} for f in col.DERIVED_FIELDS]
    return {"version": 1,
            "note": {"file": registry_note["file"], "sha256": sha,
                     "title": "Non-domestic EPC extended historic data publication note, Q3 2026 extract, Scottish Government",
                     "licence": "Open Government Licence v3.0; quoted with attribution"},
            "review": REVIEW, "columns": project + entries(pdf) + derived}


HEADER = """# What each column is, for the data dictionary and the provenance site. Generated by
# tools/extract_note_dictionary.py from the pinned publication note (attribution: note, with the
# page), then reviewed by eye (the `review` block). The key and derived columns are described by
# the project (attribution: project), with the text of epc_nd_ingest/columns.py. Regenerate for a
# new note or a changed column description, then review again.
"""


def render(pdf: Path) -> str:
    return HEADER + yaml.safe_dump(document(pdf), sort_keys=False, allow_unicode=True, width=110)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    pdf = Path(argv[0])
    if argv[1:] == ["--check"]:
        if OUT.read_text() != render(pdf):
            print(f"{OUT} differs from what the note and columns.py give", file=sys.stderr)
            return 1
        print(f"{OUT} is what the note and columns.py give")
        return 0
    Path(argv[1]).write_text(render(pdf))
    print(f"wrote {argv[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

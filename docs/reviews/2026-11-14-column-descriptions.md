# Column descriptions drafted from the publication note, reviewed 14 November 2026

`epc_nd_ingest/column_descriptions.yaml` holds one description per column. The 38 published
columns quote the data dictionary of the pinned publication note (pages 7 to 12, SHA256
`123fcfc73ecf79d3f7d16ddf78aad87167f81865dc6116cb3566b9f44b7d4e24`). The 19 key and derived
columns carry the description written for this build in `epc_nd_ingest/columns.py`.

## How it was made

`tools/extract_note_dictionary.py` reads the six dictionary pages with pypdf, removes the page
headers, finds each machine name in published order and takes the text up to the next entry. The
next entry's label is cut off by the exact phrase typed from the PDF. A name that is not found,
or a text that does not end with the next label, stops the script.

## What was checked by eye

Every one of the 38 entries was compared with the text of its page.

- All 38 fields have an entry. The note's text says "36 data elements" in two places. Its
  dictionary lists 38, the same 38 as the file's header, in the same order.
- `ADDRESS2` and `POST_TOWN` have no label of their own. They stand under "Property Address".
- `OSG_REFERENCE_NUMBER` is the one field the note marks with `*`.
- The entry of `MEETS_2002_STANDARD` starts on page 8 and ends on page 9. The page recorded is 8.
- The bullet list of `TRANSACTION_TYPE` is kept in the text as the PDF gives it.

## Where the note and the file differ

Recorded in the `review.notes` of the file, and kept as the publisher wrote them:

- The note gives a UPRN 9 to 12 digits. The file holds 8-digit values too.
- The note says band A+ is a rating of 0 or lower. In the file a rating below 0 has the band
  `Carbon Neu`, which the note does not list.
- The note calls `CONSTITUENCY` a code for the Parliamentary constituency and adds that the
  Scottish area is the ward. The label row calls it "Ward Code".
- "of and EPC" (`REPORT_REFERENCE_NUMBER`) and "energy performance of the building was
  undertaken" (`INSPECTION_DATE`) are the note's own wording.

## What keeps it true

`python3 -P tools/extract_note_dictionary.py <note.pdf> --check` compares the committed file with a
fresh extraction and exits 1 on a difference. `tests/test_provenance.py` holds the file to the
schema: every column has an entry, a note entry has a page from 7 to 12, and the note's hash is
the pinned one.

## What this review does not cover

- The comparison is with the text pypdf extracts, not with the rendered page. A character the
  extraction changes would be the same in both.
- The descriptions of the derived columns quote counts of release 2026Q3. A later release needs
  them read again.

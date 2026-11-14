# Taking a new quarterly release

The Scottish Government overwrites the same download URL every quarter. A new release is a new
build with a new `epc_release`, never an update of the old table.

1. Download the archive into a new folder `data/sources/epc_nondomestic_<release>/` with a
   `SOURCES.md` like the one for 2026Q3. Hash the archive and the note. Extract the CSV into
   `extracted/` and hash it. Check that the member read straight from the archive has the same
   hash.
2. Profile the file with `tools/profile_nondomestic.py` and compare the output with
   `docs/profile_2026-11-14.txt`. A new column, a changed label, a longer value, a new band or a
   new missing-value text is a change to `epc_nd_ingest/published_columns.yaml` or to
   `epc_nd_ingest/columns.py`, and a decision to record.
3. Replace the `release` block of `epc_nd_ingest/sources.yaml` with the new archive, note, member
   and row count, and set `quarter_end` to the last day of the quarter the release covers. The
   registry must name exactly one member. The pins of the old release stay in git history and in
   the old release's `SOURCES.md`.
4. If the header or a longest value changed, edit `published_columns.yaml`, regenerate the schema
   with `python -m epc_nd_ingest.columns` and bump `SCHEMA_VERSION` in
   `epc_nd_ingest/columns.py`. The tests compare the file with the generator.
5. `python -m epc_nd_ingest.pipeline --verify-archive`. Read `results/BUILD_REPORT.md`. The counts
   that observe will have moved. A check that fails is either a real change in the data or a pin
   to correct, and either is a decision to record in `epc_nd_ingest/decisions.yaml`. Three checks
   are the likely ones:
   - `extract.text_within_width`: a value longer than its column accepts. A recommendations cell
     over 8,000 characters needs a new width bucket.
   - `extract.data_removed_ratings` or `extract.data_removed_pairs`: the publisher's missing value
     is spelled another way, or stands in a rating without its band.
   - `extract.created_at_within_release`: `quarter_end` was not updated, or the file is a later
     release than the registry says.
6. `python -m epc_nd_ingest.sql_check`, `python -m epc_nd_ingest.dictionary` and
   `python loader/make_notebook.py` (the notebook carries the build's hash and digest), then
   `python -m pytest`.
7. If the publication note changed, write the column descriptions again with
   `python3 -P tools/extract_note_dictionary.py <note.pdf> epc_nd_ingest/column_descriptions.yaml`.
   Retype the note's labels in the script if they moved, review the result against the PDF, and
   record the review in `docs/reviews/`. The descriptions of the derived columns in
   `epc_nd_ingest/columns.py` and the list of observed codes in `epc_nd_ingest/dictionary.py`
   quote counts of the release: read them again.
8. With docker: `sh loader/sqlserver_probe.sh` for the import and check scripts on the full build,
   and `sh loader/notebook_probe.sh` for the notebook's cells on a fixture. Write a dated record of
   each in `docs/sql/`.
9. Copy the archive to `onedrive:dataset_healscot/EPC_nondomestic/` and compare sizes. If the
   restricted Zenodo record is in use, add the new archive as a new version of it. Copy the files
   of the load to `onedrive:dataset_healscot/EPC_nondomestic/load_<release>/` and compare again:
   `results/epc_nondomestic.csv.gz`, `results/manifest.json`, the two scripts of `docs/sql/`,
   `loader/load_epc_nondomestic_to_sqlserver.py`, `loader/upload_epc_nondomestic.ipynb` and
   `docs/DATA_DICTIONARY.md`. Copy them after the last rebuild: the notebook and the manifest
   carry the build's hash and digest.
10. Load with `loader/load_epc_nondomestic_to_sqlserver.py` and the new `results/manifest.json`,
    into a table of its own or alongside the old release. The key carries `epc_release`, so both
    can share one table if a project wants to compare releases. `source_row` does not carry over
    from one release to the next: match certificates across releases by `rrn`.

After step 9, show that the release can be rebuilt without the publisher: in a copy of the
repository with an empty `data/sources/`, run `python tools/restore_sources.py --token-file <file>`
and the build, and compare the CSV hash with the manifest.

The provenance site (`python -m epc_nd_ingest.provenance_site && mkdocs build`) is published by
`.github/workflows/pages.yml` on every push. Nothing to do by hand.

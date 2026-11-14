# Scottish non-domestic EPC extended historic dataset, release Q3 2026

Downloaded on 11 November 2026 from the Scottish Government's open data site,
https://data.gov.scot/dataset/non_domestic_energy_performance_certificates___extended_historic_dataset_to_q1_2026
(the catalogue slug says Q1; the linked file is the Q3 2026 release; the same URL is overwritten at
every quarterly release). Resource:
`/resource/c7873ae4-d19a-43ee-8d9f-415e7d0f05d7/download`. Publisher: Scottish Government,
EPCenquiries@gov.scot. The publication note says the data was extracted from the register on
21 October 2026 and is issued October 2026. Copied into this project on 14 November 2026 from the
folder of the session that downloaded it.

Licence, from the publication note (page 2): Open Government Licence v3.0 for every field except
`ADDRESS1`, `ADDRESS2`, `POST_TOWN` and `POSTCODE`, which carry a Royal Mail copyright notice. The
notice permits use for energy-efficiency purposes and must accompany any sharing.

| File | SHA256 | Bytes | What it is |
| --- | --- | ---: | --- |
| `nondomestic_epc_extended_historic_Q3_2026.7z` | `388d7d40438971c051515676827840df4f461fcc73b8fabe0d033b07cbc39c06` | 9,301,781 | The download: one CSV and the publication note |
| `extracted/AltHistoricExtract2013to2026ND.csv` | `304c03a6217d4d220c0595e00fa6c4c096e619dc14b6b26ac5af017fbb2f712d` | 141,193,680 | The extract, 95,719 certificates, extracted with bsdtar |
| `publication_note.pdf` | `123fcfc73ecf79d3f7d16ddf78aad87167f81865dc6116cb3566b9f44b7d4e24` | 264,448 | The note, 12 pages, with the data dictionary (copy of the archive member `EPC Data - Q3 2026 Extract - EPD Extended Historic Data Publication Note - Non-domestic Buildings.pdf`) |

Checked on 14 November 2026: the two members read straight from the archive give the same two
hashes as the copies in this folder.

One thing to know about the dates. The archive records 8 October 2026 as the modification time of
the CSV and 21 October 2026 as that of the note. The note gives 21 October 2026 as the extraction
date. The latest `CREATED_AT` in the file is 30 September 2026. The registry records the note's
date and points here for the difference.

Off-site copies, both made on 14 November 2026:

- Restricted Zenodo deposition 24224180 (draft, unpublished; reserved DOI
  10.5281/zenodo.24224180; files on request), holding the archive, the note and `SHA256SUMS`,
  each MD5-verified against this folder.
- `onedrive:dataset_healscot/EPC_nondomestic/`, holding the same three files and this note. Sizes
  and hashes compared with `rclone check`.

Profile of 14 November 2026: `docs/profile_2026-11-14.txt`, written by
`tools/profile_nondomestic.py`.

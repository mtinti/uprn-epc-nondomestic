# Response to the follow-up review of the non-domestic plan, 14 November 2026

Review: `2026-11-14-nondomestic-ingestion-plan-follow-up-review.md`. Both findings hold.
`docs/EPC_NonDomestic_Plan.md` was revised the same day. The first finding was reproduced by
running the three join queries of uprn-epc at commit `d3d1ea4`. The probe is
`2026-11-14-nondomestic-ingestion-plan-follow-up-review-response-probe.py`, with its `.out` beside
it. The second finding is about wording, and its three counts are already in the output of the
first response's probe.

| # | Finding | Holds | Change |
| --- | --- | --- | --- |
| 1 | The shared output list gave the undated query columns it cannot fill | yes. uprn-epc's undated query takes no date and returns 14 columns. It returns no `cohort_date`, `epc_inspection_date`, `epc_age_days`, `epc_lodged_before_inspection`, `historic_flag`, `epc_tie_candidates` or `epc_tie_rule`. None of the three queries reads the clock | Section 7 now gives each query its own output, in one table with a column per query: 22 columns for the dated query, 17 for the undated, 25 for the postcode query. A column that does not apply is not returned, so no typed NULL stands in for it. The undated query has no `cohort_date`, no `epc_age_days`, no `historic_flag` and no tie columns, and the plan says why for each. It does return both certificate dates and `epc_lodged_before_inspection`, which uprn-epc's undated query leaves out, because they describe the certificate and need no cohort date. The plan states that no query reads the clock. It also states which rows carry values and how the tie columns are filled. The test now checks names, order and these values. |
| 2 | The plan stated conversion to dwellings as a cause | yes. The probe measures three counts and nothing about why | The fact in the plan now gives the counts and the limit: of the 1,243 UPRNs without a current non-domestic certificate, 1,162 occur in the domestic table, 1,154 have a later domestic lodgement and 1,156 a current domestic certificate. It says this suggests a move between registers, that the extracts do not establish why, and that the two tables are extracts of different days. The undated join's text no longer explains `no_current_certificate`. It says the status reports what the file holds. The section on the view keeps the counts and leaves the question of replacement to that plan. The first response was corrected in place, with a sentence saying so. |

## What the added test does not cover

- The value rules are checked on fixtures in DuckDB and in the container probe. Neither exists
  yet, so the rules are a contract in the plan, not a tested behaviour.
- The check that no query names a clock function reads the query text. It would not see a clock
  read hidden in a view or a function the query calls. The three queries call none.
- Writing this list showed one gap, now closed in the plan: it did not say what `uprn_osg` holds
  for a building returned as `ambiguous_as_of`. The plan now says it is filled for every building
  listed, because the build allows one UPRN per register number, and the fixture expects it.

My findings from this review are closed in the plan. Nothing is implemented, so none is closed in
code.

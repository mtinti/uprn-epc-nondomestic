# Scottish non-domestic EPC plan review round 3

14 November 2026. Reviewed the latest plan, the follow-up response and its probe, and the corrected first response.

**Verdict: no new findings. Both outstanding P2 findings are closed in the plan. The plan is ready for implementation.**

| Outstanding finding | Resolution |
| --- | --- |
| Undated query output was undefined | [Section 7](../../docs/EPC_NonDomestic_Plan.md#L297) now defines separate ordered outputs for the three queries. The undated route excludes cohort date, age, historic flag and tie fields, while retaining both certificate dates and the chronology flag. The plan specifies when certificate values are NULL, preserves tie diagnostics for ambiguous dated matches, and requires tests of names, order and values. No query reads the clock. |
| Conversion to dwellings was asserted as a cause | [The profile interpretation](../../docs/EPC_NonDomestic_Plan.md#L111) now retains the measured counts and labels the register transition as an inference. It acknowledges different extraction dates and the absence of evidence explaining the transition or identifying a replacement certificate. The undated-status explanation, future-view section and first response use the same qualified interpretation. |

Validation: reran `2026-11-14-nondomestic-ingestion-plan-follow-up-review-response-probe.py` with Python `-B -I` against the domestic checkout; all assertions passed. Independently expanded the revised output table and confirmed 22 dated-UPRN columns, 17 undated-UPRN columns and 25 postcode columns, with no duplicate names. The undated output excludes all five fields identified as inapplicable.

This closes the design-review findings, not implementation validation. The response probe runs the inherited domestic queries; the proposed non-domestic queries, generated schema, value fixtures and SQL Server loading probes still need to be implemented and run as the plan requires. The earlier corrections to MAX storage, source provenance, postcode selection and normalisation, missing-value handling and deterministic overlap counts remain in place. The plan and response files were not changed by this review.

# Scottish non-domestic EPC plan follow-up review

14 November 2026. Reviewed the revised plan, the response to the first review, its executable probe and the updated profile.

**Verdict: the earlier P1 blockers are addressed in the plan. Two P2 clarifications remain.** The MAX design now separates the accepted text length from SQL storage, the port identifies annual-file assumptions, and the postcode and missing-value rules have concrete acceptance cases. No implementation or SQL Server load exists yet to validate those changes in production code.

| Original finding | Status in the revised plan |
| --- | --- |
| 1. Domestic query columns and source-year key | Measurement names and the join-back key are fixed. The shared output list still needs an undated-query rule, below. |
| 2. Incomplete MAX and source migration | Resolved: integer width 8,000, MAX storage, file-based member identity, affected modules and notebook parsing checks are specified. |
| 3. Obsolete postcode matches | Resolved: select over all eligible certificates before comparing postcode; residual ties and the new no-building status are described. |
| 4. Asymmetric postcode normalisation | Resolved: spaces, tabs and an empty result have the same treatment on both sides. |
| 5. Missing-value test without a typed target | Resolved: nullable potential rating is named, with validation of the two numeric source columns and their sentinel/band agreement. |
| 6. File-order-dependent property types | Resolved: the current-certificate breakdown is explicit, UPRNs without a current certificate are separate, and the shuffle check passes. The new causal interpretation needs correction, below. |

1. **[P2] Specify which output fields apply to the undated query.**

   Location: [plan line 296](../../docs/EPC_NonDomestic_Plan.md#L296), line 301 and the exact-output acceptance check at line 403.

   The plan requires all three queries to return the listed common columns with the same meanings. That list includes `cohort_date` and `epc_age_days`, but the inherited undated route accepts only `cohort_row_id`, `pseudo_id` and `uprn`. It has no cohort date from which to calculate certificate age. Its selection also counts current certificates rather than applying the dated route's inspection-day tie rule, so the common tie fields need an explicit applicability rule.

   Define the output per query, or retain a uniform schema and specify typed NULLs for fields that do not apply. In particular, make `cohort_date` and `epc_age_days` NULL in the undated route if there is no date input, and state how its tie fields behave. Using today's date would change the stated meaning of age and make results depend on execution time. Update the exact-output tests to check these values as well as column names. This is a remaining detail of original finding 1; the missing domestic measurement columns and obsolete key are already resolved.

   Evidence: [the inherited undated cohort contract](https://github.com/mtinti/uprn-epc/blob/04bbbda/docs/sql/join_latest_by_uprn.sql#L4) and [its current-certificate selection](https://github.com/mtinti/uprn-epc/blob/04bbbda/docs/sql/join_latest_by_uprn.sql#L23).

2. **[P2] State conversion to dwellings as an inference, not an established cause.**

   Location: [plan line 110](../../docs/EPC_NonDomestic_Plan.md#L110), line 310 and [line 372](../../docs/EPC_NonDomestic_Plan.md#L372). The response repeats the claim under “Found while reproducing”.

   The probe reproduces three observations: 1,162 shared UPRNs have no current non-domestic certificate, 1,154 have a later domestic lodgement, and 1,156 have a current domestic certificate. It does not establish a physical conversion or identify which domestic certificate superseded which non-domestic certificate. The plan nevertheless says these buildings were converted to dwellings and attributes all 1,162 missing current certificates to domestic replacement. That causal statement is stronger than the comparison of identifiers, timestamps and flags supports, particularly across two different release snapshots.

   Keep the measured counts and qualify the interpretation. Suitable wording is: “Of the 1,243 UPRNs without a current non-domestic certificate, 1,162 also occur in the domestic table; 1,154 have a domestic lodgement later than their last non-domestic lodgement. This suggests a transition between register categories, but the extracts do not establish why it occurred.” Apply the same qualification in the undated-join explanation, the future-view section and the response. Keep `no_current_certificate` as an observation rather than treating it as a conversion classification.

**Validation.** Reran `2026-11-14-nondomestic-ingestion-plan-review-response-probe.py` with Python `-B -I`, the local domestic checkout at `d3d1ea40a4269e9a6d3dbd63bd2b54e677fdfac4`, the pinned non-domestic CSV and domestic Parquet. It completed with `all assertions passed` and reproduced the stored output's numerical results, including 262 historical postcode pairs, symmetric tab handling and the 46/84 current/any-certificate hospital-or-care-home counts. Those probes reproduce the evidence and inherited behaviours; they do not execute the future port or its SQL Server loads. The plan, response, scripts and source data were not changed by this follow-up review.

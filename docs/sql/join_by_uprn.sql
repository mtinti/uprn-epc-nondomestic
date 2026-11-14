-- Join a cohort to its building's non-domestic certificate by UPRN: the certificate with the
-- latest inspection on or before the cohort date. A left join, so no cohort row disappears. One
-- output row per cohort row. The choice of certificate is explicit, never a default.
--
-- The inspection date is when the assessor saw the building, so it is the date that says what
-- the building was like. The lodgement date is the administrative date of the certificate. In
-- release 2026Q3 it follows the inspection by a median of 8 days, by 31 to 365 days in 17,125
-- certificates and by more than a year in 1,411. Both dates are returned: the ten-year validity
-- runs from lodgement. In 195 rows the lodgement date is before the inspection date, a typo in
-- one or the other. epc_lodged_before_inspection flags them.
--
-- Cohort: #cohort (cohort_row_id int NOT NULL PRIMARY KEY, pseudo_id int, uprn nvarchar(20), cohort_date date).
-- cohort_row_id identifies the cohort row and must be unique and not NULL: a person (pseudo_id) can appear
-- many times, at different dates or addresses, and each row gets its own certificate. The
-- query stops if cohort_row_id repeats. The UPRN may be padded with zeros or carry spaces: it
-- is compared as a bigint, never as text.
--
-- Status per cohort row:
--   no_uprn                  the cohort UPRN is empty or not an integer
--   uprn_not_in_epc          no non-domestic certificate for that UPRN in the release. This is the
--                            usual result: a certificate is required only on construction, sale or
--                            let, and for display in a public building over 250 square metres
--   no_certificate_by_date   certificates exist, none inspected on or before the date
--   ambiguous_as_of          two or more certificates inspected on the latest eligible day that
--                            the tie rule below cannot separate
--   matched                  one certificate. Its columns and its age in days are returned
-- The query does not decide whether the certificate has expired (ten years from lodgement).
-- epc_age_days is the days from the inspection to the cohort date, so the project can apply that
-- rule or another. The query does not read the clock.
--
-- Output, 22 columns. Every column from epc_inspection_date to rrn is NULL unless the row is
-- matched. The measurements keep their non-domestic names: CURRENT_ENERGY_PERFORMANCE_BAND and
-- current_energy_performance_rating_int rate emissions (kg of CO2 per square metre per year, lower
-- is better) and are not the domestic band and rating, which score energy cost. floor_area_int,
-- building_emissions_num and primary_energy_value_int are the three quantities the domestic
-- register also publishes in the same unit.
--
-- Ties. Two or more certificates of one building inspected on the latest eligible day are
-- separated by the rule of uprn-epc: prefer the certificate the register holds as current
-- (HISTORIC = False). If that leaves two or more, prefer the one lodged on the register last
-- (created_at_parsed). If still tied, ambiguous_as_of and no values. In 2026Q3 one UPRN has such
-- a pair. Two columns say what happened: epc_tie_candidates (how many certificates shared the
-- day. 1 means no tie. NULL means no certificate was eligible) and epc_tie_rule (NULL for no
-- tie, 'current', 'latest_lodged' or 'unresolved'). HISTORIC describes the register at extract
-- time, after the cohort date: for a same-day pair that is the same visit, so the as-of meaning
-- of the result is unchanged.

IF EXISTS (SELECT 1 FROM #cohort WHERE cohort_row_id IS NULL)
    THROW 51000, 'cohort_row_id must not be NULL: a NULL key cannot be joined back to its result.', 1;
IF EXISTS (SELECT 1 FROM #cohort GROUP BY cohort_row_id HAVING COUNT(*) > 1)
    THROW 51000, 'cohort_row_id must be unique: one row per cohort observation.', 1;

WITH cohort AS (
    SELECT c.cohort_row_id, c.pseudo_id, c.cohort_date,
           TRY_CONVERT(bigint, NULLIF(LTRIM(RTRIM(c.uprn)), N'')) AS uprn_int
    FROM #cohort AS c
),
eligible AS (
    -- Three rankings: by inspection day; then current first within the day; then the latest
    -- register lodgement within that. A certificate at rank 1 of the last is the pick when alone.
    SELECT c.cohort_row_id, e.epc_release, e.source_row,
           RANK() OVER (PARTITION BY c.cohort_row_id ORDER BY e.inspection_date_parsed DESC) AS rk_day,
           RANK() OVER (PARTITION BY c.cohort_row_id ORDER BY e.inspection_date_parsed DESC,
                        CASE WHEN e.historic_flag = 0 THEN 0 ELSE 1 END) AS rk_current,
           RANK() OVER (PARTITION BY c.cohort_row_id ORDER BY e.inspection_date_parsed DESC,
                        CASE WHEN e.historic_flag = 0 THEN 0 ELSE 1 END, e.created_at_parsed DESC) AS rk_final
    FROM cohort AS c
    JOIN epc_nondomestic AS e
      ON e.uprn_osg = c.uprn_int
     AND e.inspection_date_parsed <= c.cohort_date
),
latest AS (
    -- One row per cohort row: how many certificates shared the latest eligible day, how many
    -- survived each step of the tie rule, and the key of the one certificate when one is left.
    SELECT cohort_row_id,
           SUM(CASE WHEN rk_day = 1 THEN 1 ELSE 0 END) AS n_day,
           SUM(CASE WHEN rk_current = 1 THEN 1 ELSE 0 END) AS n_current,
           SUM(CASE WHEN rk_final = 1 THEN 1 ELSE 0 END) AS n,
           MIN(CASE WHEN rk_final = 1 THEN epc_release END) AS epc_release,
           MIN(CASE WHEN rk_final = 1 THEN source_row END) AS source_row
    FROM eligible
    GROUP BY cohort_row_id
),
known AS (
    SELECT DISTINCT uprn_osg FROM epc_nondomestic WHERE uprn_osg IS NOT NULL
)
SELECT c.cohort_row_id, c.pseudo_id,
       CASE WHEN c.uprn_int IS NULL THEN 'no_uprn'
            WHEN k.uprn_osg IS NULL THEN 'uprn_not_in_epc'
            WHEN l.cohort_row_id IS NULL THEN 'no_certificate_by_date'
            WHEN l.n > 1 THEN 'ambiguous_as_of'
            ELSE 'matched' END AS epc_status,
       c.cohort_date,
       e.inspection_date_parsed AS epc_inspection_date, e.lodgement_date_parsed AS epc_lodgement_date,
       CASE WHEN e.lodgement_date_parsed < e.inspection_date_parsed THEN 1
            WHEN e.inspection_date_parsed IS NOT NULL THEN 0 END AS epc_lodged_before_inspection,
       DATEDIFF(day, e.inspection_date_parsed, c.cohort_date) AS epc_age_days,
       e.CURRENT_ENERGY_PERFORMANCE_BAND, e.current_energy_performance_rating_int,
       e.POTENTIAL_ENERGY_PERFORMANCE_BAND, e.potential_energy_performance_rating_num,
       e.PROPERTY_TYPE_SHORT, e.PROPERTY_TYPE, e.MAIN_HEATING_FUEL,
       e.floor_area_int, e.building_emissions_num, e.primary_energy_value_int,
       e.historic_flag, e.rrn,
       l.n_day AS epc_tie_candidates,
       CASE WHEN l.n_day IS NULL OR l.n_day = 1 THEN NULL
            WHEN l.n > 1 THEN 'unresolved'
            WHEN l.n_current = 1 THEN 'current'
            ELSE 'latest_lodged' END AS epc_tie_rule
FROM cohort AS c
LEFT JOIN known AS k ON k.uprn_osg = c.uprn_int
LEFT JOIN latest AS l ON l.cohort_row_id = c.cohort_row_id
LEFT JOIN epc_nondomestic AS e
       ON l.n = 1 AND e.epc_release = l.epc_release AND e.source_row = l.source_row
ORDER BY c.cohort_row_id;

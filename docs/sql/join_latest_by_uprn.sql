-- Join a cohort to its building's current non-domestic certificate by UPRN, without a date: the
-- one certificate with HISTORIC = False. A left join. One output row per cohort row.
--
-- Cohort: #cohort (cohort_row_id int NOT NULL PRIMARY KEY, pseudo_id int, uprn nvarchar(20)). cohort_row_id
-- identifies the cohort row and must be unique and not NULL. A person (pseudo_id) can appear many times.
--
-- Status per cohort row:
--   no_uprn                  the cohort UPRN is empty or not an integer
--   uprn_not_in_epc          no non-domestic certificate for that UPRN in the release
--   no_current_certificate   certificates exist and every one is HISTORIC = True (1,243 UPRNs in
--                            2026Q3). The status reports what the file holds. It does not say why
--   ambiguous_latest         two or more HISTORIC = False certificates (no UPRN in 2026Q3)
--   matched                  one current certificate. Its columns are returned
--
-- Output, 17 columns. Every column from epc_inspection_date to rrn is NULL unless the row is
-- matched. This query returns fewer columns than join_by_uprn.sql, each for a reason:
--   no cohort_date and no epc_age_days   the query takes no date and does not read the clock.
--                                        An age counted from the day the query runs would change
--                                        with every run
--   no historic_flag                     a matched certificate is always the current one
--   no epc_tie_candidates, epc_tie_rule  there is no tie rule. Two current certificates are
--                                        ambiguous_latest and return no values
-- The measurements keep their non-domestic names, as in join_by_uprn.sql.

IF EXISTS (SELECT 1 FROM #cohort WHERE cohort_row_id IS NULL)
    THROW 51000, 'cohort_row_id must not be NULL: a NULL key cannot be joined back to its result.', 1;
IF EXISTS (SELECT 1 FROM #cohort GROUP BY cohort_row_id HAVING COUNT(*) > 1)
    THROW 51000, 'cohort_row_id must be unique: one row per cohort observation.', 1;

WITH cohort AS (
    SELECT c.cohort_row_id, c.pseudo_id, TRY_CONVERT(bigint, NULLIF(LTRIM(RTRIM(c.uprn)), N'')) AS uprn_int
    FROM #cohort AS c
),
current_certs AS (
    SELECT uprn_osg, COUNT(*) AS n,
           MIN(epc_release) AS epc_release, MIN(source_row) AS source_row
    FROM epc_nondomestic
    WHERE uprn_osg IS NOT NULL AND historic_flag = 0
    GROUP BY uprn_osg
),
known AS (
    SELECT DISTINCT uprn_osg FROM epc_nondomestic WHERE uprn_osg IS NOT NULL
)
SELECT c.cohort_row_id, c.pseudo_id,
       CASE WHEN c.uprn_int IS NULL THEN 'no_uprn'
            WHEN k.uprn_osg IS NULL THEN 'uprn_not_in_epc'
            WHEN cc.uprn_osg IS NULL THEN 'no_current_certificate'
            WHEN cc.n > 1 THEN 'ambiguous_latest'
            ELSE 'matched' END AS epc_status,
       e.inspection_date_parsed AS epc_inspection_date, e.lodgement_date_parsed AS epc_lodgement_date,
       CASE WHEN e.lodgement_date_parsed < e.inspection_date_parsed THEN 1
            WHEN e.inspection_date_parsed IS NOT NULL THEN 0 END AS epc_lodged_before_inspection,
       e.CURRENT_ENERGY_PERFORMANCE_BAND, e.current_energy_performance_rating_int,
       e.POTENTIAL_ENERGY_PERFORMANCE_BAND, e.potential_energy_performance_rating_num,
       e.PROPERTY_TYPE_SHORT, e.PROPERTY_TYPE, e.MAIN_HEATING_FUEL,
       e.floor_area_int, e.building_emissions_num, e.primary_energy_value_int,
       e.rrn
FROM cohort AS c
LEFT JOIN known AS k ON k.uprn_osg = c.uprn_int
LEFT JOIN current_certs AS cc ON cc.uprn_osg = c.uprn_int
LEFT JOIN epc_nondomestic AS e
       ON cc.n = 1 AND e.epc_release = cc.epc_release AND e.source_row = cc.source_row
ORDER BY c.cohort_row_id;

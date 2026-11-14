-- The fallback for a cohort row without a UPRN: the non-domestic buildings that were at the
-- postcode as of the cohort date, each with its certificate of the latest inspection on or before
-- that date (see join_by_uprn.sql for why the inspection date and not the lodgement date). A
-- postcode has many buildings, so this returns many rows per cohort row, and the project decides
-- what to do with them. What it gives is a list of candidate buildings, not a property of the
-- person's home: the buildings of one postcode can be a shop, an office and a care home.
-- PROPERTY_TYPE_SHORT is returned with each building for that reason.
--
-- Cohort: #cohort (cohort_row_id int NOT NULL PRIMARY KEY, pseudo_id int, postcode nvarchar(10), cohort_date date).
-- cohort_row_id identifies the cohort row and must be unique and not NULL. A person (pseudo_id) can appear
-- many times, at different dates or postcodes, and each row gets its own buildings. The cohort
-- postcode is normalised by the rule that built pc_norm: upper case, every space and every tab
-- removed. A postcode with nothing left is no_postcode.
--
-- The building is uprn_sepcr, the register's own number, present in every row and one to one
-- with the Gazetteer UPRN where that exists, so a building without a Gazetteer UPRN still
-- counts once.
--
-- Which certificate, and why the postcode is compared last. A building's postcode can change
-- between certificates: 258 register numbers of 2026Q3 carry two or more. The query therefore
-- works in three steps.
--   1. Candidate buildings are the register numbers with any certificate at the cohort postcode.
--   2. For each candidate, the latest eligible certificate is chosen over all the building's
--      certificates, whatever their postcode, with the tie rule of join_by_uprn.sql.
--   3. The building is returned only if the chosen certificate carries the cohort postcode. Where
--      the tie rule leaves two or more, the building is returned as ambiguous_as_of, without
--      certificate values, if any of them carries it.
-- Filtering by postcode first and ranking after would return a building at its old postcode
-- with its older certificate.
--
-- Status per cohort row (repeated on each of its rows):
--   no_postcode                       the cohort postcode is empty
--   postcode_not_in_epc               no certificate in the release has that pc_norm
--   no_certificate_by_date            certificates at the postcode exist, none inspected on or
--                                     before the date
--   no_building_at_postcode_by_date   certificates at the postcode were inspected on or before
--                                     the date, and every such building's latest certificate by
--                                     the date carries another postcode
--   matched                           one row per building at the postcode as of the date
-- building_status per building: matched, or ambiguous_as_of when the tie rule cannot separate
-- two or more certificates.
--
-- Output, 25 columns. uprn_osg is filled for every building listed, matched or not, where any
-- of its eligible certificates carries one: it belongs to the building, not to the chosen
-- certificate. Every column from epc_inspection_date to rrn is NULL unless building_status is
-- matched. The query does not return the address lines. A project that may see them adds
-- e.ADDRESS1, e.ADDRESS2 and e.POST_TOWN to tell the candidate buildings apart by name.
--
-- SQL Server prints "Warning: Null value is eliminated by an aggregate or other SET operation"
-- when a candidate building has a certificate without a UPRN. It is a message, not an error:
-- MAX(uprn_osg) skips those certificates, which is what is wanted.

IF EXISTS (SELECT 1 FROM #cohort WHERE cohort_row_id IS NULL)
    THROW 51000, 'cohort_row_id must not be NULL: a NULL key cannot be joined back to its result.', 1;
IF EXISTS (SELECT 1 FROM #cohort GROUP BY cohort_row_id HAVING COUNT(*) > 1)
    THROW 51000, 'cohort_row_id must be unique: one row per cohort observation.', 1;

WITH cohort AS (
    SELECT c.cohort_row_id, c.pseudo_id, c.cohort_date,
           NULLIF(UPPER(REPLACE(REPLACE(c.postcode, N' ', N''), NCHAR(9), N'')), N'') AS pc_norm
    FROM #cohort AS c
),
candidates AS (
    -- Step 1: every building that has a certificate at the cohort postcode, at any date.
    SELECT DISTINCT c.cohort_row_id, c.cohort_date, c.pc_norm AS cohort_pc, e.uprn_sepcr
    FROM cohort AS c
    JOIN epc_nondomestic AS e ON e.pc_norm = c.pc_norm
),
eligible AS (
    -- Step 2: every certificate of a candidate building inspected on or before the date, at any
    -- postcode, ranked as in join_by_uprn.sql.
    SELECT k.cohort_row_id, k.uprn_sepcr, k.cohort_pc, e.pc_norm, e.uprn_osg, e.epc_release, e.source_row,
           RANK() OVER (PARTITION BY k.cohort_row_id, k.uprn_sepcr ORDER BY e.inspection_date_parsed DESC) AS rk_day,
           RANK() OVER (PARTITION BY k.cohort_row_id, k.uprn_sepcr ORDER BY e.inspection_date_parsed DESC,
                        CASE WHEN e.historic_flag = 0 THEN 0 ELSE 1 END) AS rk_current,
           RANK() OVER (PARTITION BY k.cohort_row_id, k.uprn_sepcr ORDER BY e.inspection_date_parsed DESC,
                        CASE WHEN e.historic_flag = 0 THEN 0 ELSE 1 END, e.created_at_parsed DESC) AS rk_final
    FROM candidates AS k
    JOIN epc_nondomestic AS e
      ON e.uprn_sepcr = k.uprn_sepcr
     AND e.inspection_date_parsed <= k.cohort_date
),
per_building AS (
    SELECT cohort_row_id, uprn_sepcr,
           SUM(CASE WHEN rk_day = 1 THEN 1 ELSE 0 END) AS n_day,
           SUM(CASE WHEN rk_current = 1 THEN 1 ELSE 0 END) AS n_current,
           SUM(CASE WHEN rk_final = 1 THEN 1 ELSE 0 END) AS n,
           -- Step 3: does a chosen certificate carry the cohort postcode?
           SUM(CASE WHEN rk_final = 1 AND pc_norm = cohort_pc THEN 1 ELSE 0 END) AS n_at_postcode,
           -- Was any certificate at the cohort postcode inspected on or before the date?
           SUM(CASE WHEN pc_norm = cohort_pc THEN 1 ELSE 0 END) AS n_ever_at_postcode,
           MAX(uprn_osg) AS uprn_osg,
           MIN(CASE WHEN rk_final = 1 THEN epc_release END) AS epc_release,
           MIN(CASE WHEN rk_final = 1 THEN source_row END) AS source_row
    FROM eligible
    GROUP BY cohort_row_id, uprn_sepcr
),
by_date AS (
    -- One row per cohort row that has a certificate at its postcode inspected on or before the date.
    SELECT cohort_row_id FROM per_building GROUP BY cohort_row_id HAVING SUM(n_ever_at_postcode) > 0
),
known AS (
    SELECT DISTINCT pc_norm FROM epc_nondomestic WHERE pc_norm IS NOT NULL
)
SELECT c.cohort_row_id, c.pseudo_id,
       CASE WHEN c.pc_norm IS NULL THEN 'no_postcode'
            WHEN k.pc_norm IS NULL THEN 'postcode_not_in_epc'
            WHEN b.cohort_row_id IS NULL THEN 'no_certificate_by_date'
            WHEN d.cohort_row_id IS NULL THEN 'no_building_at_postcode_by_date'
            ELSE 'matched' END AS epc_status,
       c.cohort_date,
       d.uprn_sepcr AS building,
       CASE WHEN d.n > 1 THEN 'ambiguous_as_of' WHEN d.n = 1 THEN 'matched' END AS building_status,
       d.uprn_osg,
       e.inspection_date_parsed AS epc_inspection_date, e.lodgement_date_parsed AS epc_lodgement_date,
       CASE WHEN e.lodgement_date_parsed < e.inspection_date_parsed THEN 1
            WHEN e.inspection_date_parsed IS NOT NULL THEN 0 END AS epc_lodged_before_inspection,
       DATEDIFF(day, e.inspection_date_parsed, c.cohort_date) AS epc_age_days,
       e.CURRENT_ENERGY_PERFORMANCE_BAND, e.current_energy_performance_rating_int,
       e.POTENTIAL_ENERGY_PERFORMANCE_BAND, e.potential_energy_performance_rating_num,
       e.PROPERTY_TYPE_SHORT, e.PROPERTY_TYPE, e.MAIN_HEATING_FUEL,
       e.floor_area_int, e.building_emissions_num, e.primary_energy_value_int,
       e.historic_flag, e.rrn,
       d.n_day AS epc_tie_candidates,
       CASE WHEN d.n_day IS NULL OR d.n_day = 1 THEN NULL
            WHEN d.n > 1 THEN 'unresolved'
            WHEN d.n_current = 1 THEN 'current'
            ELSE 'latest_lodged' END AS epc_tie_rule
FROM cohort AS c
LEFT JOIN known AS k ON k.pc_norm = c.pc_norm
LEFT JOIN by_date AS b ON b.cohort_row_id = c.cohort_row_id
LEFT JOIN per_building AS d ON d.cohort_row_id = c.cohort_row_id AND d.n_at_postcode > 0
LEFT JOIN epc_nondomestic AS e
       ON d.n = 1 AND e.epc_release = d.epc_release AND e.source_row = d.source_row
ORDER BY c.cohort_row_id, d.uprn_sepcr;

WITH versions AS (
  SELECT dt_closing, uds_version,
         ROW_NUMBER() OVER (PARTITION BY dt_closing
                            ORDER BY CAST(REGEXP_EXTRACT(uds_version, 'v([0-9]+)x', 1) AS INT) DESC,
                                     CAST(REGEXP_EXTRACT(uds_version, 'x([0-9]+)$', 1) AS INT) DESC) AS rk
  FROM (SELECT DISTINCT dt_closing, uds_version FROM RDS_SRS_CAPITAL.uds_fac_arrime
        WHERE dt_closing IN ('2024q1','2024q2','2024q3','2024q4','2025q1','2025q2','2025q3','2025q4','2026q1','2026q2')) d
)
SELECT f.dt_closing, f.uds_version,
       SUM(CASE WHEN TRIM(CAST(f.cd_note_tiers_cal AS STRING)) IN ('11','12') THEN 1 ELSE 0 END)            AS n_douteux,
       SUM(CASE WHEN TRIM(CAST(f.cd_note_tiers_cal AS STRING)) IN ('11','12') THEN f.mt_cal_ead_tot END)    AS ead_douteux,
       SUM(CASE WHEN f.cd_note_tiers_cal IS NULL OR TRIM(CAST(f.cd_note_tiers_cal AS STRING)) = '' THEN 1 ELSE 0 END) AS n_null,
       COUNT(*) AS n_total
FROM RDS_SRS_CAPITAL.uds_fac_arrime f
JOIN versions v ON f.dt_closing = v.dt_closing AND f.uds_version = v.uds_version AND v.rk = 1
WHERE f.cd_tp_approche IS NOT NULL AND TRIM(f.cd_tp_approche) <> ''
GROUP BY f.dt_closing, f.uds_version
ORDER BY f.dt_closing;

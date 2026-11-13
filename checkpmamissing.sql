WITH v AS (
    SELECT dt_closing, MAX(uds_version) AS uds_version
    FROM rds_srs_capital_prod_uds_fac_arrime
    WHERE dt_closing IN ('2025q4', '2026q1')
    GROUP BY dt_closing
),
old AS (
    SELECT f.id_fem, SUM(f.mt_cal_expo_tot) AS expo_old
    FROM rds_srs_capital_prod_uds_fac_arrime f
    JOIN v ON f.dt_closing = v.dt_closing AND f.uds_version = v.uds_version
    WHERE f.dt_closing = '2025q4' AND TRIM(f.cd_pole_pmas_ap_acc) = 'PMA_12193'
    GROUP BY f.id_fem
),
new AS (
    SELECT f.id_fem, f.cd_pole_pmas_ap_acc, SUM(f.mt_cal_expo_tot) AS expo_new
    FROM rds_srs_capital_prod_uds_fac_arrime f
    JOIN v ON f.dt_closing = v.dt_closing AND f.uds_version = v.uds_version
    WHERE f.dt_closing = '2026q1'
    GROUP BY f.id_fem, f.cd_pole_pmas_ap_acc
)
SELECT COALESCE(new.cd_pole_pmas_ap_acc, '(not found in 2026q1)') AS pma_2026q1,
       COUNT(DISTINCT old.id_fem) AS n_facilities,
       SUM(old.expo_old) AS expo_2025q4_k_eur,
       SUM(new.expo_new) AS expo_2026q1_k_eur
FROM old
LEFT JOIN new ON new.id_fem = old.id_fem
GROUP BY COALESCE(new.cd_pole_pmas_ap_acc, '(not found in 2026q1)');

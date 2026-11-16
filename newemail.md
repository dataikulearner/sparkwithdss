Objet: RE: [DETECT] SRS ARRIMAGE workshop – answers to your 4 questions

Hi Fabrice,

Thank you for your feedback. Please find below our answers to your four questions, with the checks we ran and their results.


1. LAST LINE NOT FULLY DISPLAYED (Level 3 Business Lines)

This is a layout issue in the Tableau sheet (fixed height of the container), not a data issue. Anthony is looking into it.


2. PMA_12193 ABSENT FROM THE DASHBOARD

You are right: PMA_12193 has no exposure in the current period run (2026Q2), so it cannot be ranked and does not appear. We checked it directly in the source table, all versions.

a) Quarters in which PMA_12193 exists in the source:

    SELECT dt_closing, uds_version,
           COUNT(*) AS n_lines,
           SUM(CASE WHEN cd_tp_approche IS NULL OR TRIM(cd_tp_approche) = '' THEN 1 ELSE 0 END) AS n_no_approach,
           SUM(mt_cal_expo_tot) AS expo_k_eur
    FROM rds_srs_capital_prod_uds_fac_arrime
    WHERE TRIM(cd_pole_pmas_ap_acc) = 'PMA_12193'
    GROUP BY dt_closing, uds_version
    ORDER BY dt_closing, uds_version;

    Quarter    Lines (latest version)           Exposure (k EUR)
    2025Q2     108 (of which 18 w/o approach)   5,700,841.36
    2025Q3     3,403                            3,510,681.73
    2025Q4     3,846                            4,436,419.33
    2026Q1     no line                          -
    2026Q2     no line                          -

PMA_12193 only exists from 2025Q2 to 2025Q4. The DETECT figures match the source for each quarter (lines without approach code are excluded, as agreed; their amounts are 0).

b) Where did its facilities go in 2026Q1? We followed its facilities (ID_FEM) from 2025Q4 to 2026Q1, on the latest version of each quarter:

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

    PMA in 2026Q1            Facilities     Expo 2025Q4 (k EUR)   Expo 2026Q1 (k EUR)
    (not found in 2026Q1)    1,859 (92%)    4,431,750.33          -
    PMA_129                    164 (8%)         4,669.00          4,253.00
    Total                    2,023          4,436,419.33

So this is not a change of PMA code: 99.9% of the exposure of PMA_12193 is no longer present in the source from 2026Q1, under any PMA. Only 164 small facilities (EUR 4.7m) moved to PMA_129. This may come from maturities or disposals, a change of reporting scope, or new facility identifiers. Could you check on your side whether this is expected?

Note on the model: DETECT flags a segment that disappears (anomaly type "vanish") when it was present in the previous quarter and is absent in the period run. PMA_12193 was already absent in 2026Q1, one quarter before the period run, so it no longer appears at 2026Q2.


3. MATERIALITY DOES NOT FOLLOW THE SELECTED PERIMETER

The materiality is computed separately for each perimeter in our data; the issue is on the dashboard side. Example for PMA_07 (sgcp, 2026Q2, entity level, exposure):

    SELECT DISTINCT perimeters_list, seg_axes_value, seg_materiality, seg_materiality_4
    FROM SP_display_toplines
    WHERE id_set_parameters_clone = 'sgcp' AND seg_axes = 'entity' AND seg_axes_value = 'PMA_07'
      AND t_variable_clone = 'mt_cal_expo_tot' AND period_clone = '2026Q2'
    ORDER BY perimeters_list;

    Perimeter   Observed    Expected     Deviation   Materiality (Exposure total)
    N/A (all)   98,452.62   106,069.30   7.18%       7,069.73
    Sain         7,919.28    10,800.70   26.68%      2,112.71
    Douteux        547.13       541.55   1.03%           5.64

(Materiality "Exposure total" = exposure x deviation, in k EUR.)

The dashboard currently shows the N/A value whatever the perimeter selected. Anthony will make the Materiality column and the "Materiality Ordering" sort follow the User's Perimeter filter.


4. PMA_532, DOUTEUX: EXPECTED EXPOSURE FOR 2025Q1

The value 643,454.98 k EUR is consistent with the DETECT model. The difference with your 321,727.49 k EUR comes from how quarters without data are treated.

- In the DETECT core model (common to all DETECT flows: CCIRC, IFRS9, ICAAP, Arrimage), the expected value of a quarter is the median of the 4 previous available observations of the segment, not of the 4 previous calendar quarters.
- A quarter in which the segment has no line at all is not part of its series: it is skipped, not counted as 0.

For PMA_532 on the Douteux perimeter, 2024Q1 has Douteux lines with a total exposure of 0 (a real 0), while 2024Q2 has no Douteux line at all:

    SELECT period_clone, observed_value, expected_value, deviation, anomaly
    FROM SP_anomalies
    WHERE id_set_parameters_clone = 'arrimage_sgcp_latest_douteux'
      AND seg_axes = 'entity' AND seg_axes_value = 'PMA_532'
      AND t_variable_clone = 'mt_cal_expo_tot' AND model_type = 'basic'
    ORDER BY period_clone;

    Quarter   Observed (k EUR)   Quarters used for the median   Expected (k EUR)
    2024Q1           0.00        - (first observation)                    -
    2024Q2    no Douteux line    -                                        -
    2024Q3     643,454.98        2024Q1                                0.00
    2024Q4     693,929.86        2024Q1, 2024Q3                  321,727.49
    2025Q1     868,250.40        2024Q1, 2024Q3, 2024Q4          643,454.98
    2025Q2     436,687.04        2024Q1, 2024Q3, 2024Q4, 2025Q1  668,692.42

For 2025Q1: median(0; 643,454.98; 693,929.86) = 643,454.98 k EUR. Your figure counts 2024Q2 as 0: median(0; 0; 643,454.98; 693,929.86) = 321,727.49 k EUR.

We recomputed the expected values of all segments and quarters with this rule (2.1 million rows): they match the DETECT outputs for 100% of the amount targets (EAD, RWA, exposure, provisions).

This convention matters most on the Douteux perimeter, where a pole may have no defaulted line in some quarters. Would you prefer quarters without data to be counted as 0 for Arrimage? This would be a change of the model, which we can discuss.


SUMMARY OF NEXT STEPS

- Dashboard (Anthony): last line display, materiality following the perimeter filter.
- Your side: confirmation on PMA_12193 (facilities no longer in the source from 2026Q1).
- Your decision: keep the current rule for missing quarters, or count them as 0.

Don't hesitate to come back to us if you have any questions.

Best regards,
Canh-Hieu
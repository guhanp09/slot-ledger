-- Sequential bridge: baseline weights with current rates, then current traffic weights.
-- This is an exact descriptive identity on complete common support, not causal attribution.
CREATE OR REPLACE TABLE mix_bridge AS
WITH filter_keys AS (
    SELECT DISTINCT market, device, ad_unit FROM metrics
), strata AS (
    SELECT market, device, ad_unit,
        SUM(requests) FILTER (WHERE period = 'baseline') AS n0,
        SUM(requests) FILTER (WHERE period = 'current') AS n1,
        SUM(revenue_micros) FILTER (WHERE period = 'baseline') / 1000.0 AS v0,
        SUM(revenue_micros) FILTER (WHERE period = 'current') / 1000.0 AS v1
    FROM metrics WHERE grouping_id = 0 GROUP BY market, device, ad_unit
), expanded AS (
    SELECT f.market, f.device, f.ad_unit, s.n0, s.n1, s.v0, s.v1,
        SUM(COALESCE(s.n0, 0)) OVER w AS total0,
        SUM(COALESCE(s.n1, 0)) OVER w AS total1
    FROM filter_keys f JOIN strata s
        ON (f.market = '*' OR f.market = s.market)
        AND (f.device = '*' OR f.device = s.device)
        AND (f.ad_unit = '*' OR f.ad_unit = s.ad_unit)
    WINDOW w AS (PARTITION BY f.market, f.device, f.ad_unit)
), components AS (
    SELECT market, device, ad_unit,
        SUM(COALESCE(v0, 0)) / NULLIF(MAX(total0), 0) AS baseline_rpm,
        SUM(COALESCE(v1, 0)) / NULLIF(MAX(total1), 0) AS current_rpm,
        SUM(CASE WHEN n0 > 0 AND n1 > 0 THEN n0 ELSE 0 END)::DOUBLE
            / NULLIF(MAX(total0), 0) AS baseline_coverage,
        SUM(CASE WHEN n0 > 0 AND n1 > 0 THEN n1 ELSE 0 END)::DOUBLE
            / NULLIF(MAX(total1), 0) AS current_coverage,
        BOOL_AND(COALESCE(n0, 0) > 0 AND COALESCE(n1, 0) > 0) AS complete_support,
        SUM(n0::DOUBLE / NULLIF(total0, 0) * (v1 / NULLIF(n1, 0) - v0 / NULLIF(n0, 0))) AS within_change,
        SUM((n1::DOUBLE / NULLIF(total1, 0) - n0::DOUBLE / NULLIF(total0, 0))
            * v1 / NULLIF(n1, 0)) AS mix_change
    FROM expanded GROUP BY market, device, ad_unit
)
SELECT market, device, ad_unit, baseline_rpm, current_rpm,
    baseline_coverage, current_coverage, complete_support,
    current_rpm - baseline_rpm AS raw_change,
    CASE WHEN complete_support THEN within_change END AS within_change,
    CASE WHEN complete_support THEN mix_change END AS mix_change,
    CASE WHEN complete_support THEN baseline_rpm + within_change END AS fixed_mix_current_rpm,
    CASE WHEN complete_support THEN current_rpm - baseline_rpm - within_change - mix_change END AS residual
FROM components;

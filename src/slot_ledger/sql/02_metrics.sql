-- All filter combinations are calculated from request facts, including their own p95.
CREATE OR REPLACE TABLE metrics AS
SELECT period,
    COALESCE(market, '*') AS market, COALESCE(device, '*') AS device,
    COALESCE(ad_unit, '*') AS ad_unit, GROUPING_ID(market, device, ad_unit) AS grouping_id,
    COUNT(*) AS requests, SUM(bid) AS bids, SUM(win) AS wins,
    SUM(rendered) AS impressions, SUM(measurable) AS measurable, SUM(viewable) AS viewable,
    SUM(clicked) AS clicks, SUM(revenue_micros)::BIGINT AS revenue_micros,
    SUM(revenue_micros) / 1000000.0 AS revenue_usd,
    SUM(revenue_micros) / 1000.0 / COUNT(*) AS request_rpm_usd,
    SUM(revenue_micros) / 1000.0 / NULLIF(SUM(rendered), 0) AS impression_ecpm_usd,
    SUM(rendered)::DOUBLE / COUNT(*) AS render_fill_rate,
    SUM(clicked)::DOUBLE / NULLIF(SUM(rendered), 0) AS ctr,
    SUM(viewable)::DOUBLE / NULLIF(SUM(measurable), 0) AS viewability,
    QUANTILE_CONT(render_latency_ms, 0.95) AS p95_render_ms
FROM request_facts
GROUP BY period, CUBE (market, device, ad_unit);

CREATE OR REPLACE TABLE daily_metrics AS
SELECT day, period, COALESCE(market, '*') AS market, COALESCE(device, '*') AS device,
    COALESCE(ad_unit, '*') AS ad_unit, COUNT(*) AS requests,
    SUM(rendered) AS impressions, SUM(measurable) AS measurable,
    SUM(viewable) AS viewable, SUM(clicked) AS clicks,
    SUM(revenue_micros)::BIGINT AS revenue_micros,
    SUM(revenue_micros) / 1000.0 / COUNT(*) AS request_rpm_usd,
    QUANTILE_CONT(render_latency_ms, 0.95) AS p95_render_ms
FROM request_facts
GROUP BY day, period, CUBE (market, device, ad_unit);

CREATE OR REPLACE TABLE rolling_metrics AS
WITH dates AS (
    SELECT CAST(value AS DATE) AS day FROM GENERATE_SERIES(
        (SELECT baseline_start::DATE FROM config),
        (SELECT LEAST(current_end, as_of)::DATE - INTERVAL 1 DAY FROM config),
        INTERVAL 1 DAY
    ) AS days(value)
), dimensions AS (
    SELECT DISTINCT market, device, ad_unit FROM daily_metrics
), spine AS (
    SELECT d.day, x.market, x.device, x.ad_unit,
        COALESCE(m.requests, 0) AS requests, COALESCE(m.revenue_micros, 0) AS revenue_micros
    FROM dates d CROSS JOIN dimensions x
    LEFT JOIN daily_metrics m USING (day, market, device, ad_unit)
), rolling AS (
    SELECT *, SUM(requests) OVER w AS requests_7d,
        SUM(revenue_micros) OVER w AS revenue_micros_7d,
        COUNT(*) OVER w AS observed_days
    FROM spine WINDOW w AS (
        PARTITION BY market, device, ad_unit ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    )
)
SELECT *, CASE WHEN observed_days = 7 THEN
    revenue_micros_7d / 1000.0 / NULLIF(requests_7d, 0) END AS request_rpm_7d_usd,
    LAG(requests, 7) OVER (PARTITION BY market, device, ad_unit ORDER BY day) AS requests_week_ago
FROM rolling;

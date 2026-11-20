CREATE OR REPLACE TABLE segment_changes AS
WITH paired AS (
    SELECT market, device, ad_unit,
        MAX(render_fill_rate) FILTER (WHERE period = 'baseline') AS baseline_fill,
        MAX(render_fill_rate) FILTER (WHERE period = 'current') AS current_fill,
        MAX(p95_render_ms) FILTER (WHERE period = 'baseline') AS baseline_p95,
        MAX(p95_render_ms) FILTER (WHERE period = 'current') AS current_p95,
        MAX(viewability) FILTER (WHERE period = 'baseline') AS baseline_viewability,
        MAX(viewability) FILTER (WHERE period = 'current') AS current_viewability,
        SUM(requests) FILTER (WHERE period = 'current') AS current_requests
    FROM metrics WHERE grouping_id = 0 GROUP BY market, device, ad_unit
)
SELECT *, current_fill - baseline_fill AS fill_change,
    current_p95 - baseline_p95 AS p95_change_ms,
    current_viewability - baseline_viewability AS viewability_change,
    DENSE_RANK() OVER (ORDER BY current_fill - baseline_fill) AS fill_decline_rank
FROM paired;

CREATE OR REPLACE TABLE quality_summary AS
SELECT 'raw_deliveries' AS measure, COUNT(*) AS value FROM raw_events
UNION ALL SELECT 'visible_deliveries', COUNT(*) FROM raw_events
    WHERE ingested_at <= (SELECT as_of FROM config) AND event_at <= (SELECT as_of FROM config)
UNION ALL SELECT 'logical_events', COUNT(*) FROM latest_events
UNION ALL SELECT 'accepted_events', COUNT(*) FROM accepted_events
UNION ALL SELECT 'quarantined_events', COUNT(*) FROM quarantined_events
UNION ALL SELECT 'request_rows', COUNT(*) FROM request_facts;

CREATE OR REPLACE TABLE quality_reasons AS
SELECT exclusion_reason, COUNT(*) AS events FROM quarantined_events GROUP BY exclusion_reason;

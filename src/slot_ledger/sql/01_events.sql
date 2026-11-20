-- Filter the reporting cutoff BEFORE selecting a revision, so future corrections cannot leak.
CREATE OR REPLACE TABLE latest_events AS
WITH visible AS (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY event_id
        ORDER BY revision DESC, ingested_at DESC, delivery_id DESC
    ) AS position
    FROM raw_events
    WHERE ingested_at <= (SELECT as_of FROM config)
      AND event_at <= (SELECT as_of FROM config)
)
SELECT * EXCLUDE (position) FROM visible WHERE position = 1;

CREATE OR REPLACE TABLE basic_validation AS
SELECT e.*, CASE
    WHEN r.request_id IS NULL THEN 'unknown_request'
    WHEN e.event_type NOT IN ('bid', 'win', 'render', 'measurable', 'viewable', 'click', 'adjustment')
        THEN 'unknown_event_type'
    WHEN e.revision < 1 THEN 'invalid_revision'
    WHEN e.event_at < r.request_at THEN 'before_request'
    WHEN e.ingested_at < e.event_at THEN 'before_occurrence'
    WHEN e.event_type = 'render' AND e.revenue_micros < 0 THEN 'negative_render_value'
    WHEN e.event_type NOT IN ('render', 'adjustment') AND e.revenue_micros <> 0
        THEN 'unexpected_revenue'
    ELSE NULL
END AS rejection
FROM latest_events e
LEFT JOIN requests r USING (request_id);

-- A stage is a normalized request-level observation, not an individual bidder response.
-- Ambiguous multiple stage IDs are rejected rather than counted as additional revenue.
CREATE OR REPLACE TABLE event_validation AS
WITH repeated AS (
    SELECT request_id, event_type FROM basic_validation
    WHERE rejection IS NULL AND event_type <> 'adjustment'
    GROUP BY request_id, event_type HAVING COUNT(*) > 1
)
SELECT b.* EXCLUDE (rejection), COALESCE(b.rejection,
    CASE WHEN r.request_id IS NOT NULL THEN 'multiple_stage_events' END) AS rejection
FROM basic_validation b LEFT JOIN repeated r USING (request_id, event_type);

CREATE OR REPLACE TABLE stage_times AS
SELECT request_id,
    MIN(event_at) FILTER (WHERE event_type = 'bid') AS bid_at,
    MIN(event_at) FILTER (WHERE event_type = 'win') AS win_at,
    MIN(event_at) FILTER (WHERE event_type = 'render') AS render_at,
    MIN(event_at) FILTER (WHERE event_type = 'measurable') AS measurable_at
FROM event_validation WHERE rejection IS NULL
GROUP BY request_id;

CREATE OR REPLACE TABLE classified_events AS
SELECT e.*, COALESCE(e.rejection, CASE
    WHEN e.event_type <> 'bid' AND (s.bid_at IS NULL OR e.event_at < s.bid_at)
        THEN 'missing_or_later_bid'
    WHEN e.event_type IN ('render', 'measurable', 'viewable', 'click', 'adjustment')
        AND (s.win_at IS NULL OR e.event_at < s.win_at OR s.win_at < s.bid_at)
        THEN 'missing_or_invalid_win'
    WHEN e.event_type IN ('measurable', 'viewable', 'click', 'adjustment')
        AND (s.render_at IS NULL OR e.event_at < s.render_at OR s.render_at < s.win_at)
        THEN 'missing_or_invalid_render'
    WHEN e.event_type = 'viewable'
        AND (s.measurable_at IS NULL OR s.measurable_at < s.render_at OR e.event_at < s.measurable_at)
        THEN 'missing_or_later_measurement'
    ELSE NULL
END) AS exclusion_reason
FROM event_validation e
LEFT JOIN stage_times s USING (request_id);

CREATE OR REPLACE VIEW accepted_events AS
SELECT * FROM classified_events WHERE exclusion_reason IS NULL;

CREATE OR REPLACE VIEW quarantined_events AS
SELECT * FROM classified_events WHERE exclusion_reason IS NOT NULL;

-- Collapse event grain before joining requests; requests without events remain in every denominator.
CREATE OR REPLACE TABLE request_facts AS
WITH event_totals AS (
    SELECT request_id,
        MAX(CASE WHEN event_type = 'bid' THEN 1 ELSE 0 END) AS bid,
        MAX(CASE WHEN event_type = 'win' THEN 1 ELSE 0 END) AS win,
        MAX(CASE WHEN event_type = 'render' THEN 1 ELSE 0 END) AS rendered,
        MAX(CASE WHEN event_type = 'measurable' THEN 1 ELSE 0 END) AS measurable,
        MAX(CASE WHEN event_type = 'viewable' THEN 1 ELSE 0 END) AS viewable,
        MAX(CASE WHEN event_type = 'click' THEN 1 ELSE 0 END) AS clicked,
        SUM(revenue_micros) AS revenue_micros,
        MIN(event_at) FILTER (WHERE event_type = 'render') AS render_at
    FROM accepted_events GROUP BY request_id
)
SELECT r.*, CAST(r.request_at AS DATE) AS day,
    CASE WHEN r.request_at < (SELECT current_start FROM config)
        THEN 'baseline' ELSE 'current' END AS period,
    COALESCE(e.bid, 0) AS bid, COALESCE(e.win, 0) AS win,
    COALESCE(e.rendered, 0) AS rendered, COALESCE(e.measurable, 0) AS measurable,
    COALESCE(e.viewable, 0) AS viewable, COALESCE(e.clicked, 0) AS clicked,
    COALESCE(e.revenue_micros, 0)::BIGINT AS revenue_micros,
    DATE_DIFF('millisecond', r.request_at, e.render_at) AS render_latency_ms
FROM requests r LEFT JOIN event_totals e USING (request_id)
WHERE r.request_at >= (SELECT baseline_start FROM config)
  AND r.request_at < (SELECT LEAST(current_end, as_of) FROM config);

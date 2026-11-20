# Metric and event contract

## Scope and time

One row in `requests.csv` is one display-ad opportunity. Required fields are `request_id`, `request_at`, `market`, `device` and `ad_unit`. Request IDs are unique; markets use two uppercase letters; device is `desktop` or `mobile`; units are `article` or `footer`. `*` is reserved for aggregate rows.

`config.json` declares `baseline_start`, `current_start`, `current_end` and `as_of`, with explicit UTC offsets. The planned equal-length intervals are `[baseline_start, current_start)` and `[current_start, current_end)`, bounded at UTC midnight. The as-of timestamp can be intra-day; such a current window is marked preliminary. Daily rolling windows include complete UTC days only. A 72-hour maturity allowance after `current_end` is an explicit modeling assumption, not a vendor SLA or a guarantee of complete billing.

The fixture uses 1–14 and 15–28 October 2026, as of 2 November. These dates belong to generated examples, not historical publisher observations.

## Event identity and revisions

`events.csv` has `delivery_id`, `event_id`, `request_id`, `event_type`, `event_at`, `ingested_at`, `revision` and signed integer `revenue_micros`. Events are normalized `bid`, `win`, `render`, `measurable`, `viewable`, `click` or `adjustment` observations.

`delivery_id` uniquely identifies an exported delivery. Retries reuse an event/revision identity. Request, event type and occurrence time are immutable across revisions; a revised amount is allowed. Conflicting payloads under the same event/revision key fail ingestion. A future revision cannot replace a past value: occurrence/ingestion cutoffs are applied before `ROW_NUMBER()` chooses the latest visible version.

The first six lifecycle types are singleton stages per request. Multiple logical IDs for the same stage are ambiguous and quarantined rather than counted as extra impressions or revenue. Adjustments may have multiple independent IDs. Bid → win → render → measurable/viewable chains must be temporally coherent; click and adjustment require a valid render. Viewability requires valid measurability. Raw bidder-level events require a separate normalization adapter.

Quarantines preserve the valid request denominator. A malformed click is excluded, not transformed into a valid impression. Unknown request IDs never create new requests. Input delivery/quality counts describe the whole visible export; performance measures use only the configured request cohorts.

## Measures

| Measure | Definition |
|---|---|
| Render fill | Requests with a valid render / all in-scope requests |
| Bid coverage | Requests with a valid bid / requests |
| Net publisher revenue | Visible render values plus visible signed adjustments, divided by 1,000,000 |
| Request RPM | Net revenue / requests × 1,000 |
| Impression eCPM | Net revenue / rendered impressions × 1,000 |
| CTR | Valid clicks / rendered impressions |
| Viewability | Viewable / measurable impressions |
| p95 render | 95th percentile of valid request-to-render elapsed times |

Undefined rates are `NULL`, displayed as an em dash. Revenue is not advertiser spending, profit, GMV or ROAS. Negative net value for a request requires review under this narrow contract. There is no currency conversion.

The viewability denominator follows the distinction between measurable and viewable impressions in [Google's Active View guidance](https://support.google.com/admanager/answer/4524488?hl=en). The fixture generates flags; it does not implement pixel/time measurement. Its normalized render-fill metric should not be equated with every vendor's served/matched-request definition. Click and impression metric conventions are also documented in [Kevel Custom Reports](https://dev.kevel.com/docs/custom-reports).

Every filter's p95 is calculated from its underlying request distribution. Overall rates use sums and counts; segment ratios and percentiles are never averaged to create a total.

## Mix bridge

For country × device × ad-unit stratum `s`, let `w0`, `w1` be baseline/current request shares and `r0`, `r1` be their request RPMs:

```text
within-stratum change = sum(w0 * (r1 - r0))
traffic-mix change    = sum((w1 - w0) * r1)
current - baseline   = within-stratum change + traffic-mix change
fixed-mix current    = baseline + within-stratum change
```

This is a sequential, order-dependent descriptive decomposition. It is not a causal model or proof that market, device or inventory mix is exogenous. Standardization is withheld unless every included baseline/current stratum has requests in both periods; baseline/current common-support coverage is exported. No silent renormalization over surviving strata is used.

## Implementation and controls

The models use CTEs, `ROW_NUMBER`, conditional aggregates, joins at declared grains, `CUBE`/`GROUPING_ID`, percentile aggregates, calendar spines, named rolling windows, `LAG` and `DENSE_RANK`. See [DuckDB windows](https://duckdb.org/docs/current/sql/functions/window_functions) and [grouping sets](https://duckdb.org/docs/current/sql/query_syntax/grouping_sets).

Integer-micro revenue reconciles across events, request facts and overall cube rows. Accepted plus quarantined events equals visible logical events. Funnel ordering and nonnegative net request value are checked. Bridge residuals are checked within `1e-9` USD per 1,000 requests, accommodating floating-point rate arithmetic.

SQL files own the analysis; Python handles generation, typed ingestion, execution and artifact export. The static browser selects existing SQL rollups, formats values and exports the selected rows. It does not estimate new percentiles or silently recompute metrics at a different grain.

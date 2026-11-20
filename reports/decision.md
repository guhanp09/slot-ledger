# Publisher yield review

**Synthetic fixture · USD · UTC · 140,000 requests · closed comparison**

## Decision

Investigate the IN/mobile/footer rendering path and validate a bounded change in a controlled test. A three-percentage-point fill decline is this demo's triage heuristic, not a statistical significance test. Do not expand rollout because global RPM rose.

## Evidence

Observed request RPM moves from $1.168 to $1.724. Holding the original country/device/ad-unit mix fixed gives $1.021. The within-stratum change is $-0.147 per 1,000 requests, and the traffic-mix contribution is $+0.703; the bridge residual is 1.1e-16.

The weakest paired render-fill change is IN/mobile/footer: 71.0% to 49.4%, with p95 request-to-render latency moving from 462 to 969 ms.

Requests with no bid or no render remain in the denominator. Viewability uses measurable impressions,
not ad requests or all rendered impressions. Negative revenue adjustments are included after revision
deduplication; quarantine and reconciliation counts are in `data_quality.json`.

## Proposed review and competing interests

| Perspective | Concern | Evidence and next action |
|---|---|---|
| Publisher/commercial | Revenue and monetization coverage | Compare raw and fixed-mix request RPM; check fill before changing floors. |
| Engineering | Rendering reliability and page latency | Inspect the affected market/device/ad unit and event completeness; reproduce the rendering path. |
| Advertiser/quality | Viewability and meaningful delivery | Keep measurable/viewable denominators explicit; check viewability alongside yield. |
| Product | Small, measurable release | Specify the experiment, rollback condition and primary/guardrail metrics before testing. |

These are proposed stakeholder perspectives, not records of meetings or collaboration with actual teams.

## Test before rollout

Randomize eligible publisher/ad-unit clusters with a predeclared request-RPM primary metric. Analyze
revenue/request ratios with cluster-aware uncertainty, not a binomial interval on individual impressions.
Guard render fill, measurable-impression viewability and request-to-render latency. Set the minimum
number of clusters, fixed horizon, allocation check and rollback bounds before observing results. The fixture is observational
and intentionally generated: it does not estimate the causal effect of a price, timeout or template change.

## Scope

One normalized ad opportunity per request, four fictional market cohorts, display inventory and USD.
No real publisher logs, actual ad-server integration, field experiment, advertiser ROI or measured
business uplift. Country/device/ad-unit standardization cannot remove unobserved confounding.
The 72-hour reporting maturity rule is assumed. Validate actual logging, billing and settlement SLAs
before adapting this model to operational decisions.

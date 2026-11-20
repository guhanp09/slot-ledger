def decision_memo(summary):
    b = summary["overall_bridge"]
    worst = summary["largest_fill_decline"]
    maturity = "closed" if summary["mature_comparison"] else "preliminary"
    synthetic = summary["data_kind"] == "synthetic"
    label = "Synthetic fixture" if synthetic else "Local export; unverified provenance"
    origin = (
        "Generated example data. No real publisher logs, actual ad-server integration, field experiment, advertiser ROI or measured business uplift."
        if synthetic else
        "A locally supplied export; its source has not been verified by this project. No ad-server integration, field experiment, advertiser ROI or causal business uplift is established."
    )
    bridge = (
        f"Observed request RPM moves from ${b['baseline_rpm']:.3f} to ${b['current_rpm']:.3f}. "
        f"Holding the original country/device/ad-unit mix fixed gives ${b['fixed_mix_current_rpm']:.3f}. "
        f"The within-stratum change is ${b['within_change']:+.3f} per 1,000 requests, and the traffic-mix "
        f"contribution is ${b['mix_change']:+.3f}; the bridge residual is {b['residual']:.2g}."
        if b["complete_support"] else
        "Complete common support is absent. The standardized result is withheld rather than silently dropping strata."
    )
    finding = (
        f"The weakest paired render-fill change is {worst['market']}/{worst['device']}/{worst['ad_unit']}: "
        f"{worst['baseline_fill']:.1%} to {worst['current_fill']:.1%}, with p95 request-to-render latency "
        f"moving from {worst['baseline_p95']:.0f} to {worst['current_p95']:.0f} ms."
        if worst and worst["baseline_p95"] is not None and worst["current_p95"] is not None else
        "There is insufficient paired segment data to rank a delivery regression."
    )
    if not summary["mature_comparison"]:
        decision = "Hold the launch recommendation: the current comparison is preliminary under the declared maturity rule."
    elif not b["complete_support"]:
        decision = "Hold the standardized-yield recommendation: matched baseline/current strata are incomplete. Review missing coverage first."
    elif worst and worst["fill_change"] is not None and worst["fill_change"] < -0.03:
        decision = (
            f"Investigate the {worst['market']}/{worst['device']}/{worst['ad_unit']} rendering path and validate "
            "a bounded change in a controlled test. A three-percentage-point fill decline is this demo's "
            "triage heuristic, not a statistical significance test. Do not expand rollout because global RPM rose."
        )
    else:
        decision = "Continue monitoring: no paired segment crosses the demo's three-percentage-point fill-decline triage threshold. No rendering fix is prescribed from these results."
    return f"""# Publisher yield review

**{label} · USD · UTC · {summary['requests']:,} requests · {maturity} comparison**

## Decision

{decision}

## Evidence

{bridge}

{finding}

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
number of clusters, fixed horizon, allocation check and rollback bounds before observing results. This descriptive
comparison does not establish the causal effect of a price, timeout or template change.

## Scope

One normalized ad opportunity per request, {len(summary['markets'])} market labels, display inventory and USD.
{origin} Country/device/ad-unit standardization cannot remove unobserved confounding.
The 72-hour reporting maturity rule is assumed. Validate actual logging, billing and settlement SLAs
before adapting this model to operational decisions.
"""

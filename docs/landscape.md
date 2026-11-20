# Publisher reporting workflows and product scope

Research reviewed 20 November 2026. Public documentation supports the capabilities below; this was a desk review, not hands-on access to vendor accounts or a customer interview study.

## Existing approaches

| Approach | Documented capability | Implication for this project |
|---|---|---|
| Google Ad Manager Interactive reports | Filterable metrics/dimensions, time comparisons, charts, pivot layouts and export. Google documents the retirement of the legacy reporting UI in September 2026. [Source](https://support.google.com/admanager/answer/16071282?hl=en) | Do not rebuild a general ad-server report builder. Preserve a small, explicit metric contract and an auditable comparison that can be regenerated as reporting interfaces change. |
| Prebid generic analytics | Publishers can send selected auction events to their own backend, batch deliveries and format payloads; the documentation distinguishes a reduced payload preset. [Source](https://docs.prebid.org/dev-docs/modules/genericAnalyticsAdapter.html) | Retry/revision identity, grain and data minimization must be deliberate before reporting. SlotLedger consumes normalized CSVs; this collector is a possible integration route, not an implemented connector. |
| Kevel Custom Reports | Grouping/filtering includes countries and campaign attributes, with CSV export and distinct event-count/report freshness considerations. [Source](https://dev.kevel.com/docs/custom-reports) | Country comparisons and explicit definitions are ordinary requirements, not novel features. Keep metric reconciliation and report cutoff visible; do not assume this fixture's 72-hour maturity rule matches Kevel's event-report lag. |

These products sit at different layers of the stack. The comparison concerns reporting workflows, not a price/ranking comparison between interchangeable ad servers. No claim is made that vendors lack a mix bridge, reconciliation controls or any feature not established by their public documentation.

## Observed product trend

The documented shift to Interactive reports changes how publishers create, refine and migrate reporting workflows. It supports prioritizing portable definitions and repeatable exports over another general dashboard surface. The September 2026 change is a documented product transition, not evidence of demand for SlotLedger or proof of a market-size estimate. [Google migration guidance](https://support.google.com/admanager/answer/16071282?hl=en)

## A specific opportunity

For a weekly publisher review, make it easy to answer: did the inventory get better, or did the visitor mix move toward higher-priced markets? Pair that question with delivery, viewability and latency so a commercial objective cannot hide a broken experience. This is the project's chosen workflow; its value would need validation with real analysts and their existing tools.

## Scope decisions

1. **Build the metric path first.** Reconcile the request/event grain and revisions before creating a headline chart. A large number of retries must not look like commercial growth.
2. **Keep display separate from video.** The fixture does not mix measurement rules across formats. [Google's viewability guidance](https://support.google.com/admanager/answer/4524488?hl=en) describes different display and video thresholds.
3. **Show latency alongside yield.** Bidding delay can trade off against revenue and user abandonment. This is documented in [Prebid's timeout guidance](https://docs.prebid.org/features/timeouts.html); SlotLedger's measured interval is request-to-render, not a direct implementation of a Prebid auction timeout.
4. **Recommend a test, not an automatic rollout.** A descriptive or modeled difference cannot establish the effect of a proposed intervention. The [decision memo](../reports/decision.md) specifies proposed owners, competing interests and the evidence to gather before release.

## Next evidence

Observe analysts comparing two real reports; measure which denominator, revision or mix questions remain unresolved, and whether the proposed view reduces correction work. Map an authorized export to the normalized contract and reconcile billing totals. These steps are proposed and have not been performed.

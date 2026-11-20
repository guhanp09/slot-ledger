# Quality review

Reviewed 20 November 2026 after the initial implementation.

## Corrections made

- **Recommendation bias:** the first memo draft prescribed a mobile fix regardless of the selected evidence. Recommendations now depend on maturity, common support and the actual lowest-change segment. Stable delivery produces a monitoring recommendation; incomplete support blocks standardization.
- **Snapshot consistency:** conflict/identity validation originally examined future deliveries. It now uses the same visible-event cutoff as revision selection. A future malformed revision cannot invalidate an earlier valid snapshot.
- **Event semantics:** duplicate logical stage IDs are ambiguous, not additional revenue. Invalid measurability cannot validate a later viewability event. Tests exercise these cases independently of the generated demonstration.
- **Browser labeling:** select controls now use explicit native label associations. The keyboard, filter, shareable-URL and accessibility checks use their accessible names.
- **Artifact provenance:** deployment uploads the report bundle checked by the verification job. It does not check out a potentially different committed report in the deploy job. An independent artifact script compares the embedded browser data, SQL CSVs, reconciliations and hashes.
- **Experimental interpretation:** the proposed publisher/ad-unit experiment calls for cluster-aware uncertainty. Request-RPM ratios are not treated as independent binary impression outcomes.

## Claim checks

The demonstration is labeled synthetic in the README, dashboard, generated memo and resume description. Offline comparisons are not customer uplift. Vendor research is a sourced desk review; no vendor-account access, analyst interviews or stakeholder meetings are claimed. Public sources establish documented features, not the absence of an unverified competitor feature.

The SQL retains unfilled requests, signed micro-USD values, report cutoffs, explicit denominators and missing-support states. Exported percentiles come from their actual grouping; the browser never averages percentiles to produce a total. The 72-hour maturity rule and three-percentage-point triage threshold are declared assumptions.

## Validation

- 23 Python cases with small, hand-calculable fixtures.
- Seven browser checks; SQL/UI/export parity, shared filters, keyboard access, automated accessibility and mobile overflow.
- Seven reconciliation controls in the 140,000-request fixture.
- Independent report/input hash and aggregate reconciliation checks.
- Ruff checks and JavaScript parsing.

Local browser validation used installed Google Chrome. The hosted workflow installs the matching Playwright Chromium build. Execution details are in `validation.json`; hosted results are in GitHub Actions.

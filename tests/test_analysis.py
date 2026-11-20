import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from slot_ledger.generate import EVENT_COLUMNS, REQUEST_COLUMNS
from slot_ledger.pipeline import analyze, materialize, open_database, verify


class Export:
    def __init__(self, path):
        self.path = path
        self.requests = []
        self.events = []
        self.times = {}

    def request(self, rid, market="US", period="baseline", day=None):
        at = datetime(2026, 10, day or (1 if period == "baseline" else 15), 12, tzinfo=timezone.utc)
        self.times[rid] = at
        self.requests.append([rid, at.isoformat(), market, "mobile", "article"])

    def event(self, rid, kind, amount=0, offset=None, eid=None, revision=1, received=None):
        offsets = {"bid": 40, "win": 90, "render": 200, "measurable": 1200,
                   "viewable": 2200, "click": 3200, "adjustment": 86400200}
        at = self.times.get(rid, datetime(2026, 10, 1, 12, tzinfo=timezone.utc))
        at += timedelta(milliseconds=offset if offset is not None else offsets.get(kind, 200))
        eid = eid or f"e{len(self.events)}"
        self.events.append([len(self.events)+1, eid, rid, kind, at.isoformat(),
                            (received or at + timedelta(seconds=1)).isoformat(), revision, amount])
        return eid

    def impression(self, rid, amount=1000, latency=200):
        self.event(rid, "bid")
        self.event(rid, "win")
        return self.event(rid, "render", amount, offset=latency)

    def save(self):
        for name, columns, records in [("requests.csv", REQUEST_COLUMNS, self.requests),
                                       ("events.csv", EVENT_COLUMNS, self.events)]:
            with (self.path/name).open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(columns)
                writer.writerows(records)
        (self.path/"config.json").write_text(json.dumps({
            "baseline_start": "2026-10-01T00:00:00Z", "current_start": "2026-10-15T00:00:00Z",
            "current_end": "2026-10-29T00:00:00Z", "as_of": "2026-11-02T00:00:00Z",
        }))
        (self.path/"manifest.json").write_text(json.dumps({"kind": "synthetic", "files": {
            name: hashlib.sha256((self.path/name).read_bytes()).hexdigest()
            for name in ["requests.csv", "events.csv", "config.json"]
        }}))

    def db(self, as_of=None):
        self.save()
        con = open_database(self.path, as_of=as_of)
        materialize(con)
        verify(con)
        return con


@pytest.fixture
def export(tmp_path):
    return Export(tmp_path)


def overall(con, period="baseline"):
    result = con.execute("SELECT * FROM metrics WHERE grouping_id=7 AND period=?", [period])
    return dict(zip([c[0] for c in result.description], result.fetchone(), strict=True))


def test_unfilled_requests_stay_in_denominator(export):
    export.request("a")
    export.request("b")
    export.impression("a", 2000)
    with export.db() as con:
        result = overall(con)
        assert result["requests"] == 2
        assert result["impressions"] == 1
        assert result["render_fill_rate"] == 0.5
        assert result["request_rpm_usd"] == 1.0


def test_delivery_retry_does_not_double_revenue(export):
    export.request("a")
    export.impression("a", 2000)
    duplicate = export.events[-1].copy()
    duplicate[0] += 1
    export.events.append(duplicate)
    with export.db() as con:
        assert overall(con)["revenue_micros"] == 2000
        assert overall(con)["impressions"] == 1


def test_revision_cutoff_precedes_latest_selection(export):
    export.request("a")
    eid = export.impression("a", 2000)
    export.event("a", "render", 1000, eid=eid, revision=2,
                 received=datetime(2026, 10, 20, tzinfo=timezone.utc))
    with export.db(as_of="2026-10-19T00:00:00Z") as con:
        assert overall(con)["revenue_micros"] == 2000
    with export.db() as con:
        assert overall(con)["revenue_micros"] == 1000


def test_conflicting_same_revision_is_rejected(export):
    export.request("a")
    eid = export.impression("a", 1000)
    export.event("a", "render", 2000, eid=eid)
    export.save()
    with pytest.raises(ValueError, match="conflicting payloads"):
        open_database(export.path)


def test_revisions_cannot_reassign_event_identity(export):
    export.request("a")
    export.request("b")
    eid = export.impression("a", 1000)
    export.event("b", "render", 1000, eid=eid, revision=2)
    export.save()
    with pytest.raises(ValueError, match="event IDs change"):
        open_database(export.path)


def test_unknown_request_is_quarantined(export):
    export.request("a")
    export.event("missing", "render", 1000)
    with export.db() as con:
        assert overall(con)["requests"] == 1
        assert overall(con)["revenue_micros"] == 0
        assert con.execute("SELECT exclusion_reason FROM quarantined_events").fetchone()[0] == "unknown_request"


def test_viewability_uses_measurable_denominator(export):
    for rid in ["a", "b"]:
        export.request(rid)
        export.impression(rid)
    export.event("a", "measurable")
    export.event("a", "viewable")
    with export.db() as con:
        result = overall(con)
        assert result["impressions"] == 2
        assert result["measurable"] == 1
        assert result["viewability"] == 1.0


def test_click_without_render_does_not_become_valid_engagement(export):
    export.request("a")
    export.event("a", "click")
    with export.db() as con:
        assert overall(con)["clicks"] == 0
        assert con.execute("SELECT COUNT(*) FROM quarantined_events").fetchone()[0] == 1


def test_invalid_measurement_cannot_validate_viewability(export):
    export.request("a")
    export.impression("a")
    export.event("a", "measurable", offset=100)
    export.event("a", "viewable")
    with export.db() as con:
        assert overall(con)["measurable"] == 0
        assert overall(con)["viewable"] == 0


def test_multiple_render_ids_are_ambiguous_not_extra_money(export):
    export.request("a")
    export.impression("a", 2000)
    export.event("a", "render", 3000)
    with export.db() as con:
        assert overall(con)["impressions"] == 0
        assert overall(con)["revenue_micros"] == 0
        assert con.execute("SELECT COUNT(*) FROM quarantined_events").fetchone()[0] == 2


def test_adjustments_are_signed_and_do_not_add_impressions(export):
    export.request("a")
    export.impression("a", 2000)
    export.event("a", "adjustment", -500)
    with export.db() as con:
        assert overall(con)["revenue_micros"] == 1500
        assert overall(con)["impressions"] == 1


def test_negative_net_revenue_requires_review(export):
    export.request("a")
    export.impression("a", 1000)
    export.event("a", "adjustment", -2000)
    with pytest.raises(ValueError, match="no_negative_net_request_revenue"):
        export.db()


def test_empty_event_export_has_undefined_rates(export):
    export.request("a")
    with export.db() as con:
        result = overall(con)
        assert result["request_rpm_usd"] == 0
        assert result["render_fill_rate"] == 0
        assert result["ctr"] is None
        assert result["viewability"] is None
        assert result["impression_ecpm_usd"] is None


def test_no_requests_is_a_clear_input_error(export, tmp_path):
    export.save()
    with pytest.raises(ValueError, match="No requests"):
        analyze(export.path, tmp_path/"out")


def test_overall_rpm_is_ratio_of_sums_not_mean_of_segment_rates(export):
    for i in range(10):
        export.request(str(i), market="US" if i == 0 else "IN")
        export.impression(str(i), 10000 if i == 0 else 1000)
    with export.db() as con:
        assert overall(con)["request_rpm_usd"] == pytest.approx(1.9)


def test_mix_reversal_and_exact_sequential_bridge(export):
    for period, us_requests, us_amount, in_amount in [("baseline", 1, 10000, 1000), ("current", 9, 9000, 900)]:
        for i in range(10):
            rid = period+str(i)
            export.request(rid, market="US" if i < us_requests else "IN", period=period)
            export.impression(rid, us_amount if i < us_requests else in_amount)
    with export.db() as con:
        row = con.execute("SELECT baseline_rpm,current_rpm,fixed_mix_current_rpm,within_change,mix_change,residual FROM mix_bridge WHERE market='*' AND device='*' AND ad_unit='*'").fetchone()
        assert row == pytest.approx((1.9, 8.19, 1.71, -0.19, 6.48, 0), abs=1e-10)


def test_missing_strata_withhold_standardization(export):
    for rid, market, period in [("a", "US", "baseline"), ("b", "IN", "baseline"), ("c", "US", "current")]:
        export.request(rid, market=market, period=period)
        export.impression(rid)
    with export.db() as con:
        row = con.execute("SELECT complete_support,baseline_coverage,current_coverage,fixed_mix_current_rpm FROM mix_bridge WHERE market='*' AND device='*' AND ad_unit='*'").fetchone()
        assert row == (False, 0.5, 1.0, None)


def test_rolling_window_uses_calendar_spine_and_weighted_counts(export):
    for rid, day, amount in [("a", 1, 2000), ("b", 1, 2000), ("c", 7, 10000)]:
        export.request(rid, day=day)
        export.impression(rid, amount)
    with export.db() as con:
        row = con.execute("SELECT requests_7d,request_rpm_7d_usd FROM rolling_metrics WHERE day='2026-10-07' AND market='*' AND device='*' AND ad_unit='*'").fetchone()
        assert row == pytest.approx((3, 14/3))
        assert con.execute("SELECT request_rpm_7d_usd FROM rolling_metrics WHERE day='2026-10-06' AND market='*' AND device='*' AND ad_unit='*'").fetchone()[0] is None


def test_rollup_percentile_is_not_an_average_of_segment_percentiles(export):
    for i in range(10):
        export.request(str(i), market="US" if i < 9 else "IN")
        export.impression(str(i), latency=200 if i < 9 else 1000)
    with export.db() as con:
        assert overall(con)["p95_render_ms"] == pytest.approx(640)


def test_report_preserves_synthetic_and_preliminary_scope(export, tmp_path):
    export.request("a")
    export.request("b", period="current")
    export.impression("a")
    export.impression("b")
    export.save()
    result = analyze(export.path, tmp_path/"out", as_of="2026-10-20T00:00:00Z")
    assert result["data_kind"] == "synthetic"
    assert result["mature_comparison"] is False
    assert "Hold the launch recommendation" in (tmp_path/"out/decision.md").read_text()


def test_future_conflicts_cannot_change_a_past_snapshot(export):
    export.request("a")
    eid = export.impression("a", 1000)
    export.event("a", "render", 2000, eid=eid,
                 received=datetime(2026, 10, 20, tzinfo=timezone.utc))
    with export.db(as_of="2026-10-19T00:00:00Z") as con:
        assert overall(con)["revenue_micros"] == 1000
    with pytest.raises(ValueError, match="conflicting payloads"):
        export.db()


def test_stable_delivery_does_not_get_a_hardcoded_mobile_fix(export, tmp_path):
    for rid, period in [("a", "baseline"), ("b", "current")]:
        export.request(rid, period=period)
        export.impression(rid)
    export.save()
    analyze(export.path, tmp_path/"out")
    assert "Continue monitoring" in (tmp_path/"out/decision.md").read_text()


def test_missing_support_blocks_a_standardized_recommendation(export, tmp_path):
    for rid, market, period in [("a", "US", "baseline"), ("b", "IN", "baseline"), ("c", "US", "current")]:
        export.request(rid, market=market, period=period)
        export.impression(rid)
    export.save()
    analyze(export.path, tmp_path/"out")
    assert "Hold the standardized-yield recommendation" in (tmp_path/"out/decision.md").read_text()


def test_unknown_local_export_is_not_mislabeled_synthetic(export, tmp_path):
    export.request("a")
    export.impression("a")
    export.save()
    (export.path/"manifest.json").unlink()
    result = analyze(export.path, tmp_path/"out")
    assert result["data_kind"] == "unverified_local_export"
    assert '<span class="badge">Local export</span>' in (tmp_path/"out/index.html").read_text()
    assert "Generated example data" not in (tmp_path/"out/decision.md").read_text()


def test_stale_synthetic_manifest_does_not_certify_modified_inputs(export, tmp_path):
    export.request("a")
    export.save()
    with (export.path/"requests.csv").open("a") as handle:
        handle.write("b,2026-10-02T12:00:00Z,US,mobile,article\n")
    with pytest.raises(ValueError, match="manifest hashes"):
        analyze(export.path, tmp_path/"out")

"""Generate a repeatable fixture with delivery retries, revisions and market-mix change."""

import csv
import hashlib
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

START = datetime(2026, 10, 1, tzinfo=timezone.utc)
REQUEST_COLUMNS = ["request_id", "request_at", "market", "device", "ad_unit"]
EVENT_COLUMNS = [
    "delivery_id", "event_id", "request_id", "event_type", "event_at", "ingested_at",
    "revision", "revenue_micros",
]
MARKETS = ["US", "GB", "IN", "BR"]


def iso(value):
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def generate(output: Path, requests_per_day=5000, seed=20261120):
    if requests_per_day < 1:
        raise ValueError("requests_per_day must be positive")
    output.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    delivery = 0
    logical = 0
    corrections = retries = 0
    with (output / "requests.csv").open("w", newline="") as rf, (
        output / "events.csv"
    ).open("w", newline="") as ef:
        requests = csv.writer(rf)
        events = csv.writer(ef)
        requests.writerow(REQUEST_COLUMNS)
        events.writerow(EVENT_COLUMNS)

        def emit(rid, kind, at, revenue=0, event_id=None, revision=1, received=None):
            nonlocal delivery, logical, retries
            if event_id is None:
                logical += 1
                event_id = f"e{logical:09d}"
            received = received or at + timedelta(seconds=rng.randrange(0, 7200))
            payload = [event_id, rid, kind, iso(at), iso(received), revision, revenue]
            delivery += 1
            events.writerow([delivery, *payload])
            if rng.random() < 0.015:
                delivery += 1
                retries += 1
                payload[4] = iso(received + timedelta(seconds=60))
                events.writerow([delivery, *payload])
            return event_id

        for day in range(28):
            changed = day >= 14
            market_weights = [0.55, 0.20, 0.15, 0.10] if changed else [0.20, 0.20, 0.40, 0.20]
            for number in range(requests_per_day):
                rid = f"r{day:02d}{number:07d}"
                at = START + timedelta(days=day, seconds=rng.randrange(0, 86400))
                market = rng.choices(MARKETS, weights=market_weights)[0]
                device = "mobile" if rng.random() < 0.65 else "desktop"
                unit = "article" if rng.random() < 0.65 else "footer"
                requests.writerow([rid, iso(at), market, device, unit])
                bid_rate = {"US": 0.94, "GB": 0.90, "IN": 0.83, "BR": 0.85}[market]
                if rng.random() > bid_rate:
                    continue
                emit(rid, "bid", at + timedelta(milliseconds=40))
                if rng.random() > 0.88:
                    continue
                emit(rid, "win", at + timedelta(milliseconds=90))
                affected = changed and market == "IN" and device == "mobile"
                if rng.random() > (0.68 if affected else 0.96):
                    continue
                latency = 150 + rng.lognormvariate(4.65, 0.50)
                if device == "mobile":
                    latency += 75
                if affected:
                    latency += 500
                rendered = at + timedelta(milliseconds=latency)
                cpm = {"US": 3.60, "GB": 2.40, "IN": 0.65, "BR": 0.95}[market]
                cpm *= (0.90 if changed else 1) * (0.82 if unit == "footer" else 1)
                revenue = max(1, round(cpm * 1000 * rng.uniform(0.8, 1.2)))
                eid = emit(rid, "render", rendered, revenue)
                if rng.random() < 0.012:
                    corrections += 1
                    emit(rid, "render", rendered, round(revenue * 0.95), event_id=eid,
                         revision=2, received=rendered + timedelta(days=2))
                if rng.random() < 0.025:
                    emit(rid, "adjustment", rendered + timedelta(days=1), -round(revenue * 0.1))
                if rng.random() < 0.95:
                    emit(rid, "measurable", rendered + timedelta(seconds=1))
                    view_rate = (0.58 if device == "mobile" else 0.74)
                    view_rate -= 0.16 if unit == "footer" else 0
                    view_rate -= 0.12 if affected else 0
                    if rng.random() < view_rate:
                        emit(rid, "viewable", rendered + timedelta(seconds=2))
                if rng.random() < (0.009 if device == "mobile" else 0.014):
                    emit(rid, "click", rendered + timedelta(seconds=3))

        # Invalid deliveries exercise quarantine without removing valid requests from the denominator.
        for number in range(8):
            emit(f"missing-{number}", "render", START + timedelta(hours=1), 1000)
        emit("r000000000", "unknown", START + timedelta(hours=1))
        emit("r000000000", "render", START - timedelta(seconds=1), 1000)

    config = {
        "baseline_start": "2026-10-01T00:00:00Z",
        "current_start": "2026-10-15T00:00:00Z",
        "current_end": "2026-10-29T00:00:00Z",
        "as_of": "2026-11-02T00:00:00Z",
    }
    (output / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    manifest = {
        "kind": "synthetic", "seed": seed, "requests": requests_per_day * 28,
        "days": 28, "markets": MARKETS, "logical_events": logical,
        "raw_deliveries": delivery, "retry_deliveries": retries, "revised_events": corrections,
        "assumptions": {
            "traffic_mix": "US share rises from 20% to 55%; current CPM is 10% lower in every market.",
            "regression": "Current IN/mobile render probability and viewability fall; latency increases.",
            "economics": "USD publisher revenue is invented, not observed advertising demand or profit.",
            "measurement": "Viewable/measurable flags are generated; no browser measurement is performed.",
        },
        "files": {},
    }
    for name in ["requests.csv", "events.csv", "config.json"]:
        manifest["files"][name] = hashlib.sha256((output / name).read_bytes()).hexdigest()
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest

import csv
import hashlib
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb

PACKAGE = Path(__file__).resolve().parent

SCHEMA = """
CREATE TABLE requests (
    request_id VARCHAR PRIMARY KEY, request_at TIMESTAMPTZ NOT NULL,
    market VARCHAR NOT NULL CHECK (regexp_full_match(market, '[A-Z]{2}')),
    device VARCHAR NOT NULL CHECK (device IN ('mobile', 'desktop')),
    ad_unit VARCHAR NOT NULL CHECK (ad_unit IN ('article', 'footer'))
);
CREATE TABLE raw_events (
    delivery_id BIGINT PRIMARY KEY, event_id VARCHAR NOT NULL, request_id VARCHAR NOT NULL,
    event_type VARCHAR NOT NULL, event_at TIMESTAMPTZ NOT NULL, ingested_at TIMESTAMPTZ NOT NULL,
    revision INTEGER NOT NULL, revenue_micros BIGINT NOT NULL
);
CREATE TABLE config (
    baseline_start TIMESTAMPTZ, current_start TIMESTAMPTZ,
    current_end TIMESTAMPTZ, as_of TIMESTAMPTZ
);
"""
EXPORTS = ["metrics", "daily_metrics", "rolling_metrics", "mix_bridge", "segment_changes"]


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamps must include their UTC offset")
    return result.astimezone(timezone.utc)


def open_database(source: Path, database=":memory:", as_of=None):
    config = json.loads((source / "config.json").read_text())
    if as_of:
        config["as_of"] = as_of
    values = [timestamp(config[k]) for k in ["baseline_start", "current_start", "current_end", "as_of"]]
    if not values[0] < values[1] < values[2] or values[3] <= values[0]:
        raise ValueError("Expected baseline_start < current_start < current_end and a later cutoff")
    if values[1] - values[0] != values[2] - values[1]:
        raise ValueError("The two planned comparison windows must have equal duration")
    if any(v.time().replace(tzinfo=None) != datetime.min.time() for v in values[:3]):
        raise ValueError("Planned windows must begin and end at UTC midnight")
    con = duckdb.connect(str(database))
    con.execute("SET TimeZone = 'UTC'")
    con.execute(SCHEMA)
    for table, name in [("requests", "requests.csv"), ("raw_events", "events.csv")]:
        # Filenames are passed as parameters; column types come from the destination schema.
        con.execute(f"INSERT INTO {table} SELECT * FROM read_csv(?, header=true)", [str(source / name)])
    con.execute("INSERT INTO config VALUES (?, ?, ?, ?)", values)
    conflicts = con.execute("""
        SELECT COUNT(*) FROM (
            SELECT event_id, revision FROM raw_events
            WHERE ingested_at <= (SELECT as_of FROM config) AND event_at <= (SELECT as_of FROM config)
            GROUP BY event_id, revision
            HAVING COUNT(DISTINCT struct_pack(
                rid := request_id, kind := event_type, occurred := event_at, amount := revenue_micros
            )) > 1
        )
    """).fetchone()[0]
    if conflicts:
        con.close()
        raise ValueError(f"{conflicts} event/revision keys have conflicting payloads")
    identity_changes = con.execute("""
        SELECT COUNT(*) FROM (
            SELECT event_id FROM raw_events
            WHERE ingested_at <= (SELECT as_of FROM config) AND event_at <= (SELECT as_of FROM config)
            GROUP BY event_id
            HAVING COUNT(DISTINCT struct_pack(
                rid := request_id, kind := event_type, occurred := event_at
            )) > 1
        )
    """).fetchone()[0]
    if identity_changes:
        con.close()
        raise ValueError(f"{identity_changes} event IDs change their request, type or occurrence time")
    return con


def materialize(con):
    timings = {}
    for file in sorted((PACKAGE / "sql").glob("*.sql")):
        started = time.perf_counter()
        con.execute(file.read_text())
        timings[file.name] = round(time.perf_counter() - started, 4)
    return timings


def rows(con, query):
    result = con.execute(query)
    columns = [c[0] for c in result.description]
    return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]


def json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def verify(con):
    checks = {
        "one_fact_per_request": """SELECT COUNT(*) - COUNT(DISTINCT request_id) FROM request_facts""",
        "funnel_order": """SELECT COUNT(*) FROM request_facts WHERE
            clicked > rendered OR viewable > measurable OR measurable > rendered
            OR rendered > win OR win > bid""",
        "no_negative_net_request_revenue": """SELECT COUNT(*) FROM request_facts WHERE revenue_micros < 0""",
        "event_partition": """SELECT (SELECT COUNT(*) FROM latest_events)
            - (SELECT COUNT(*) FROM accepted_events) - (SELECT COUNT(*) FROM quarantined_events)""",
        "revenue_reconciliation": """SELECT
            (SELECT COALESCE(SUM(e.revenue_micros), 0) FROM accepted_events e
             JOIN request_facts f USING(request_id))
            - (SELECT COALESCE(SUM(revenue_micros), 0) FROM request_facts)""",
        "cube_reconciliation": """SELECT COALESCE(SUM(ABS(a.revenue_micros-b.revenue_micros)),0)
            FROM (SELECT period, SUM(revenue_micros) AS revenue_micros FROM request_facts GROUP BY period) a
            JOIN (SELECT period, revenue_micros FROM metrics WHERE grouping_id=7) b USING(period)""",
        "bridge_identity": """SELECT COUNT(*) FROM mix_bridge
            WHERE complete_support AND (residual IS NULL OR ABS(residual) > 1e-9)""",
    }
    observed = {name: con.execute(query).fetchone()[0] for name, query in checks.items()}
    if any(value != 0 for value in observed.values()):
        raise ValueError("Reconciliation failed: " + json.dumps(observed))
    return observed


def write_csv(path, data):
    if not data:
        path.write_text("")
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(data[0]))
        writer.writeheader()
        writer.writerows(data)


def analyze(source: Path, output: Path, as_of=None):
    started = time.perf_counter()
    source_hashes = {name: hashlib.sha256((source / name).read_bytes()).hexdigest()
                     for name in ["requests.csv", "events.csv", "config.json"]}
    manifest_path = source / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    data_kind = "synthetic" if manifest.get("kind") == "synthetic" else "unverified_local_export"
    if data_kind == "synthetic" and manifest.get("files") != source_hashes:
        raise ValueError("Synthetic manifest hashes do not match the input export")
    with open_database(source, as_of=as_of) as con:
        timings = materialize(con)
        if con.execute("SELECT COUNT(*) FROM request_facts").fetchone()[0] == 0:
            raise ValueError("No requests fall inside the reporting window")
        controls = verify(con)
        output.mkdir(parents=True, exist_ok=True)
        data = {}
        for name in EXPORTS:
            data[name] = rows(con, f"SELECT * FROM {name} ORDER BY ALL")
            write_csv(output / f"{name}.csv", data[name])
        # Export UTC timestamps as text; fetching TIMESTAMPTZ objects otherwise adds a pytz dependency.
        config = {key: timestamp(value) for key, value in rows(con, """
            SELECT baseline_start::VARCHAR AS baseline_start, current_start::VARCHAR AS current_start,
                current_end::VARCHAR AS current_end, as_of::VARCHAR AS as_of FROM config
        """)[0].items()}
        quality = {r["measure"]: r["value"] for r in rows(con, "SELECT * FROM quality_summary")}
        quality["reasons"] = rows(con, "SELECT * FROM quality_reasons ORDER BY exclusion_reason")
        quality["retry_or_superseded_deliveries"] = quality["visible_deliveries"] - quality["logical_events"]
        overall = next(r for r in data["mix_bridge"] if all(r[k] == "*" for k in ["market", "device", "ad_unit"]))
        ranked = sorted(data["segment_changes"], key=lambda r: (
            r["fill_change"] if r["fill_change"] is not None else 1,
            r["market"], r["device"], r["ad_unit"],
        ))
        mature = config["as_of"] >= config["current_end"] + timedelta(hours=72)
        summary = {
            "data_kind": data_kind, "currency": "USD", "timezone": "UTC",
            "config": config, "mature_comparison": mature,
            "maturity_policy": "72 hours after the current window closes; a modeling assumption, not a universal SLA.",
            "requests": quality["request_rows"], "markets": sorted({r["market"] for r in data["metrics"] if r["market"] != "*"}),
            "overall_bridge": overall, "largest_fill_decline": ranked[0] if ranked else None,
            "controls": controls, "quality": quality,
            "sql_seconds": timings, "pipeline_seconds": round(time.perf_counter() - started, 3),
            "duckdb": duckdb.__version__, "input_sha256": source_hashes,
        }
        data["summary"] = summary
        for name, value in [("summary.json", summary), ("data_quality.json", quality)]:
            (output / name).write_text(json.dumps(value, default=json_default, indent=2, allow_nan=False) + "\n")
        create_report(output, data)
        return summary


def create_report(output, data):
    import shutil

    from .report import decision_memo

    payload = json.dumps(data, default=json_default, separators=(",", ":"), allow_nan=False)
    # A literal </script> in a future dimension value must not terminate the JSON container.
    payload = payload.replace("<", "\\u003c")
    html = (PACKAGE / "web" / "index.html").read_text().replace("__REPORT_DATA__", payload)
    synthetic = data["summary"]["data_kind"] == "synthetic"
    html = html.replace("__DATA_LABEL__", "Synthetic data" if synthetic else "Local export")
    scope = (
        "No live publisher data or ad serving. The fixture intentionally changes market mix and mobile delivery; it demonstrates analysis, not measured commercial improvement."
        if synthetic else
        "Locally supplied export; source provenance is unverified by this analysis. Results are descriptive and do not establish causal improvements. No ad serving or tracking is performed."
    )
    html = html.replace("__DATA_SCOPE__", scope)
    (output / "index.html").write_text(html)
    for name in ["app.js", "style.css"]:
        shutil.copy2(PACKAGE / "web" / name, output / name)
    (output / "decision.md").write_text(decision_memo(data["summary"]))
    manifest = {}
    for file in sorted(output.iterdir()):
        if file.is_file() and file.name != "artifacts.json":
            manifest[file.name] = {"sha256": hashlib.sha256(file.read_bytes()).hexdigest(), "bytes": file.stat().st_size}
    (output / "artifacts.json").write_text(json.dumps(manifest, indent=2) + "\n")

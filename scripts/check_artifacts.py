"""Independent checks on the exported report bundle rather than its in-memory tables."""

import csv
import hashlib
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
reports = root / "reports"
summary = json.loads((reports / "summary.json").read_text())
html = (reports / "index.html").read_text()
payload = json.loads(re.search(r'<script id="report-data" type="application/json">(.*?)</script>', html, re.S)[1])
assert "__REPORT_DATA__" not in html
assert payload["summary"] == summary
assert all(value == 0 for value in summary["controls"].values())
with (reports / "metrics.csv").open() as handle:
    metrics = list(csv.DictReader(handle))
assert sum(int(row["requests"]) for row in metrics if row["grouping_id"] == "0") == summary["requests"]
for period in ["baseline", "current"]:
    cells = [row for row in metrics if row["period"] == period and row["grouping_id"] == "0"]
    total = next(row for row in metrics if row["period"] == period and row["grouping_id"] == "7")
    assert sum(int(row["revenue_micros"]) for row in cells) == int(total["revenue_micros"])
    assert sum(int(row["requests"]) for row in cells) == int(total["requests"])
for file, record in json.loads((reports / "artifacts.json").read_text()).items():
    assert hashlib.sha256((reports / file).read_bytes()).hexdigest() == record["sha256"], file
for file, digest in summary["input_sha256"].items():
    assert hashlib.sha256((root / "data/generated" / file).read_bytes()).hexdigest() == digest, file
print("Artifact checks passed: HTML/JSON parity, request and revenue totals, file hashes and input provenance.")

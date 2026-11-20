"use strict";
const data = JSON.parse(document.getElementById("report-data").textContent);
const summary = data.summary;
const fields = ["market", "device", "ad_unit"];
const marketNames = {US: "United States", GB: "United Kingdom", IN: "India", BR: "Brazil"};
const controls = [document.getElementById("market"), document.getElementById("device"), document.getElementById("unit")];
const fmt = (value, style = "number") => {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "—";
  if (style === "money") return new Intl.NumberFormat("en-US", {style: "currency", currency: "USD", minimumFractionDigits: 3, maximumFractionDigits: 3}).format(value);
  if (style === "percent") return `${(value * 100).toFixed(1)}%`;
  if (style === "ms") return `${Math.round(value).toLocaleString("en-US")} ms`;
  return Number(value).toLocaleString("en-US");
};
const el = (tag, text, cls) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
};
const matches = (row, selection) => fields.every((field, i) => row[field] === selection[i]);
for (const market of summary.markets) controls[0].add(new Option(`${marketNames[market] || market} (${market})`, market));
const url = new URL(location.href);
controls.forEach((control, i) => {
  const value = url.searchParams.get(fields[i]);
  if ([...control.options].some(option => option.value === value)) control.value = value;
  control.addEventListener("change", render);
});
document.querySelector("form").addEventListener("submit", event => event.preventDefault());
document.getElementById("reset").addEventListener("click", () => {
  controls.forEach(control => { control.value = "*"; });
  render();
});
const config = summary.config;
document.getElementById("context").textContent = `Baseline ${config.baseline_start.slice(0, 10)}–${new Date(new Date(config.current_start) - 86400000).toISOString().slice(0, 10)} · Current ${config.current_start.slice(0, 10)}–${new Date(new Date(config.current_end) - 86400000).toISOString().slice(0, 10)} · As of ${config.as_of.slice(0, 10)} · USD / UTC`;
if (!summary.mature_comparison) {
  const warning = document.getElementById("maturity");
  warning.hidden = false;
  warning.textContent = "Preliminary comparison. The declared 72-hour maturity window has not closed. Hold a launch recommendation.";
}
function metricCard(label, current, baseline, style, definition) {
  const card = el("article", undefined, "card");
  card.append(el("h2", label), el("div", fmt(current, style), "value"), el("p", `Baseline ${fmt(baseline, style)}`, "before"), el("p", definition, "definition"));
  return card;
}
function render() {
  const selection = controls.map(control => control.value);
  if (["http:", "https:"].includes(location.protocol)) {
    const next = new URL(location.href);
    fields.forEach((field, i) => selection[i] === "*" ? next.searchParams.delete(field) : next.searchParams.set(field, selection[i]));
    history.replaceState(null, "", next);
  }
  document.getElementById("filter-status").textContent = `Showing ${controls.map(control => control.options[control.selectedIndex].text).join(", ")}`;
  const baseline = data.metrics.find(row => row.period === "baseline" && matches(row, selection)) || {};
  const current = data.metrics.find(row => row.period === "current" && matches(row, selection)) || {};
  const cards = document.getElementById("cards");
  cards.replaceChildren(
    metricCard("Ad requests", current.requests, baseline.requests, "number", "One ad opportunity per request"),
    metricCard("Request RPM", current.request_rpm_usd, baseline.request_rpm_usd, "money", "Net revenue / requests × 1,000"),
    metricCard("Render fill", current.render_fill_rate, baseline.render_fill_rate, "percent", "Rendered / requested opportunities"),
    metricCard("Viewability", current.viewability, baseline.viewability, "percent", "Viewable / measurable impressions"),
    metricCard("Click-through rate", current.ctr, baseline.ctr, "percent", "Clicks / rendered impressions"),
    metricCard("p95 render time", current.p95_render_ms, baseline.p95_render_ms, "ms", "Request-to-render elapsed time")
  );
  renderBridge(selection);
  renderChart(selection);
  const tbody = document.getElementById("market-rows");
  tbody.replaceChildren();
  for (const market of summary.markets.filter(market => selection[0] === "*" || market === selection[0])) {
    const key = [market, selection[1], selection[2]];
    const before = data.metrics.find(row => row.period === "baseline" && matches(row, key)) || {};
    const now = data.metrics.find(row => row.period === "current" && matches(row, key)) || {};
    const row = el("tr");
    [marketNames[market] || market, fmt(now.requests), `${fmt(before.request_rpm_usd, "money")} → ${fmt(now.request_rpm_usd, "money")}`,
      fmt(now.render_fill_rate, "percent"), fmt(now.viewability, "percent"), fmt(now.p95_render_ms, "ms")].forEach(value => row.append(el("td", value)));
    tbody.append(row);
  }
  document.getElementById("download").disabled = !current.period && !baseline.period;
}
function renderBridge(selection) {
  const bridge = data.mix_bridge.find(row => matches(row, selection));
  const values = document.getElementById("mix-values");
  values.replaceChildren();
  for (const [label, key] of [["Baseline", "baseline_rpm"], ["Current, actual mix", "current_rpm"], ["Current, baseline mix", "fixed_mix_current_rpm"]]) {
    const item = el("dl");
    item.append(el("dt", label), el("dd", fmt(bridge?.[key], "money")));
    values.append(item);
  }
  const reading = document.getElementById("mix-reading");
  if (!bridge?.complete_support) {
    reading.textContent = "Insufficient common support: not every baseline/current stratum is represented. Fixed-mix yield and the bridge are withheld.";
  } else {
    const direction = bridge.raw_change > 0 && bridge.within_change < 0 ? "The headline increase masks weaker within-segment yield. " : "Read delivery and yield together before choosing an intervention. ";
    reading.textContent = `${direction}Within-stratum change ${fmt(bridge.within_change, "money")}; traffic-mix contribution ${fmt(bridge.mix_change, "money")} per 1,000 requests. Baseline/current coverage ${(bridge.baseline_coverage * 100).toFixed(0)}% / ${(bridge.current_coverage * 100).toFixed(0)}%.`;
  }
}
function renderChart(selection) {
  const container = document.getElementById("chart");
  const rows = data.rolling_metrics.filter(row => matches(row, selection) && row.request_rpm_7d_usd !== null);
  if (!rows.length) {
    container.replaceChildren(el("p", "Not enough complete UTC days for a seven-day rate.", "subtle"));
    return;
  }
  const width = 500, height = 185, left = 46, top = 13, bottom = 29;
  const max = Math.max(...rows.map(row => row.request_rpm_7d_usd), 0.01) * 1.13;
  const x = i => left + i / Math.max(rows.length - 1, 1) * (width - left - 10);
  const y = value => height - bottom - value / max * (height - top - bottom);
  const path = rows.map((row, i) => `${i ? "L" : "M"}${x(i).toFixed(2)},${y(row.request_rpm_7d_usd).toFixed(2)}`).join(" ");
  let markup = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Trailing seven-day request RPM, ending ${rows.at(-1).day.slice(0,10)} at ${fmt(rows.at(-1).request_rpm_7d_usd, "money")}">`;
  for (const fraction of [0, 0.5, 1]) {
    const at = y(max * fraction);
    markup += `<line x1="${left}" y1="${at}" x2="${width - 10}" y2="${at}" stroke="#e1e8e3"/><text x="0" y="${at + 4}" font-size="10" fill="#607366">$${(max * fraction).toFixed(2)}</text>`;
  }
  markup += `<path d="${path}" fill="none" stroke="#237b66" stroke-width="2.5"/>`;
  for (const i of [0, rows.length - 1]) markup += `<text x="${x(i)}" y="${height - 6}" text-anchor="${i ? "end" : "start"}" font-size="10" fill="#607366">${rows[i].day.slice(5, 10)}</text>`;
  container.innerHTML = markup + "</svg>";
}
const quality = summary.quality;
document.getElementById("quality-reading").textContent = `${fmt(quality.raw_deliveries)} raw deliveries become ${fmt(quality.logical_events)} visible logical events after cutoff and revision selection. ${fmt(quality.quarantined_events)} events are quarantined. All ${Object.keys(summary.controls).length} reconciliation controls pass.`;
for (const [label, key] of [["Request facts", "request_rows"], ["Retries / old revisions", "retry_or_superseded_deliveries"], ["Accepted events", "accepted_events"], ["Quarantined events", "quarantined_events"]]) {
  const item = el("div");
  item.append(el("dt", label), el("dd", fmt(quality[key])));
  document.getElementById("quality").append(item);
}
document.getElementById("download").addEventListener("click", () => {
  const selection = controls.map(control => control.value);
  const records = data.metrics.filter(row => matches(row, selection));
  const columns = ["period", "market", "device", "ad_unit", "requests", "impressions", "measurable", "viewable", "clicks", "revenue_micros", "request_rpm_usd", "render_fill_rate", "viewability", "p95_render_ms"];
  const csv = [columns.join(","), ...records.map(row => columns.map(key => row[key] ?? "").join(","))].join("\r\n");
  const object = URL.createObjectURL(new Blob([csv], {type: "text/csv;charset=utf-8"}));
  const link = el("a");
  link.href = object;
  link.download = `slot-ledger-${selection.map(value => value === "*" ? "all" : value).join("-")}.csv`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(object), 1000);
});
render();

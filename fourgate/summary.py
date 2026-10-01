"""Local pilot summary of runtime Outcome Guard logs.

    fourgate summary outcomes.jsonl [more.jsonl ...] --out fourgate-summary.html

Reads the shape-only ``outcomes.jsonl`` lines written by ``wrap.py`` and
renders one self-contained HTML page (no JavaScript, no remote content, no
network) plus a short text summary on stdout. The logs never contain
arguments, extracted values, record IDs, response bodies or credentials, so
neither does the page. Only known structural keys are read; anything else in a
line is ignored, and malformed lines are counted and skipped.
"""
import datetime
import html
import json
import math
from collections import Counter, OrderedDict
from pathlib import Path

STATUSES = ("pass", "fail", "unknown")
STATUS_LABEL = {"pass": "PASS", "fail": "FAIL", "unknown": "UNKNOWN"}
STATUS_ICON = {"pass": "✓", "fail": "✕", "unknown": "?"}

REASONS = {
    "postcondition_satisfied": "Read-back confirmed the record exists with the contracted values.",
    "record_missing": "Read-back proved the record the tool reported does not exist.",
    "field_mismatch": "Read-back found the record, but a contracted field has a different value.",
    "not_success_result": "The tool itself returned an error (isError), so there was nothing to verify.",
    "required_field_missing": "The tool reported success without a field the contract needs (often the record ID).",
    "verifier_error": "The verifier could not confirm either way (auth, network, unconfigured status). Run the verifier dry run to see why.",
    "verifier_timeout": "The verifier exceeded its time budget.",
    "verifier_malformed": "The verifier returned an unexpected or unapproved answer.",
    "contract_invalid": "The runtime contract for this tool is invalid.",
    "gate_timeout_or_error": "The outcome check itself timed out or faulted; the call passed through unchanged.",
    "internal_error": "Fourgate hit an internal error; the call passed through unchanged.",
}

MAX_LINE_BYTES = 64 * 1024
MAX_KEY_CHARS = 200


def _text(value, default="unknown"):
    if not isinstance(value, str) or not value:
        return default
    return value[:MAX_KEY_CHARS]


def parse_line(line):
    """Return a normalized record or None when the line is not a usable record."""
    if len(line) > MAX_LINE_BYTES:
        return None
    try:
        item = json.loads(line)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(item, dict):
        return None
    status = item.get("status")
    timestamp = item.get("timestamp")
    if status not in STATUSES or isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
        return None
    if not math.isfinite(timestamp):
        return None
    gate_ms = item.get("gate_ms")
    if isinstance(gate_ms, bool) or not isinstance(gate_ms, int) or gate_ms < 0:
        gate_ms = None
    return {
        "timestamp": float(timestamp),
        "server": _text(item.get("server")),
        "tool": _text(item.get("tool")),
        "mode": _text(item.get("mode")),
        "status": status,
        "reason_code": _text(item.get("reason_code"), "internal_error"),
        "gate_ms": gate_ms,
    }


def load(paths):
    records, skipped = [], 0
    for path in paths:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                parsed = parse_line(line)
                if parsed is None:
                    skipped += 1
                else:
                    records.append(parsed)
    records.sort(key=lambda r: r["timestamp"])
    return records, skipped


def _percentile(values, fraction):
    ordered = sorted(values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def _day(timestamp):
    return datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc).strftime("%Y-%m-%d")


def _iso(timestamp):
    return datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def summarize(records, skipped=0):
    totals = Counter(r["status"] for r in records)
    by_tool, by_day = OrderedDict(), OrderedDict()
    reasons = Counter()
    for r in records:
        key = f'{r["server"]}/{r["tool"]}'
        by_tool.setdefault(key, Counter())[r["status"]] += 1
        by_day.setdefault(_day(r["timestamp"]), Counter())[r["status"]] += 1
        reasons[(r["status"], r["reason_code"])] += 1
    gates = [r["gate_ms"] for r in records if r["gate_ms"] is not None]
    latency = None
    if gates:
        latency = {"samples": len(gates), "p50_ms": _percentile(gates, 0.5),
                   "p95_ms": _percentile(gates, 0.95), "max_ms": max(gates)}
    return {
        "calls": len(records),
        "skipped_lines": skipped,
        "totals": {s: totals.get(s, 0) for s in STATUSES},
        "first": _iso(records[0]["timestamp"]) if records else None,
        "last": _iso(records[-1]["timestamp"]) if records else None,
        "servers": sorted({r["server"] for r in records}),
        "modes": sorted({r["mode"] for r in records}),
        "by_tool": {k: {s: v.get(s, 0) for s in STATUSES} for k, v in
                    sorted(by_tool.items(), key=lambda kv: -sum(kv[1].values()))},
        "by_day": {k: {s: v.get(s, 0) for s in STATUSES} for k, v in by_day.items()},
        "reasons": [{"status": s, "reason_code": c, "count": n}
                    for (s, c), n in sorted(reasons.items(), key=lambda kv: (STATUSES.index(kv[0][0]), -kv[1]))],
        "latency": latency,
    }


def text(summary):
    t = summary["totals"]
    lines = [f'fourgate summary: {summary["calls"]} protected calls  '
             f'PASS {t["pass"]}  FAIL {t["fail"]}  UNKNOWN {t["unknown"]}']
    if summary["first"]:
        lines.append(f'period: {summary["first"]} to {summary["last"]}')
    if summary["latency"]:
        lat = summary["latency"]
        lines.append(f'added latency: p50 {lat["p50_ms"]} ms, p95 {lat["p95_ms"]} ms ({lat["samples"]} calls)')
    if summary["skipped_lines"]:
        lines.append(f'skipped {summary["skipped_lines"]} malformed line(s)')
    return "\n".join(lines)


def _pct(part, whole):
    return f"{(100.0 * part / whole):.0f}%" if whole else "0%"


def _bar(counts, scale_max):
    total = sum(counts.values())
    if not total:
        return '<div class="bar"></div>'
    width = 100.0 * total / scale_max if scale_max else 0
    segments = []
    for status in STATUSES:
        n = counts.get(status, 0)
        if not n:
            continue
        label = f"{STATUS_LABEL[status]}: {n} of {total} ({_pct(n, total)})"
        segments.append(f'<span class="seg {status}" style="flex:{n}" title="{html.escape(label)}"></span>')
    return f'<div class="bar"><div class="fill" style="width:{width:.2f}%">{"".join(segments)}</div></div>'


def _counts_cell(counts):
    return " ".join(
        f'<span class="cnt"><span class="dot {s}" aria-hidden="true"></span>{STATUS_LABEL[s]} {counts.get(s, 0)}</span>'
        for s in STATUSES)


CSS = """
:root{--bg:#fcfcfb;--ink:#1d1d1b;--ink2:#555550;--muted:#7a7a74;--line:#e4e4df;--card:#f4f4f1;
--pass:#0ca30c;--fail:#d03b3b;--unknown:#fab219}
@media (prefers-color-scheme:dark){:root{--bg:#1a1a19;--ink:#f1f1ee;--ink2:#c4c4be;--muted:#9a9a93;
--line:#34342f;--card:#242422}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:64rem;margin:0 auto;padding:2rem 1rem 3rem}
h1{font-size:1.6rem;margin:0 0 .25rem}h2{font-size:1.1rem;margin:2.2rem 0 .75rem}
p{margin:.25rem 0}.sub{color:var(--ink2)}.muted{color:var(--muted);font-size:.9rem}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(10rem,1fr));gap:.75rem;margin-top:1.5rem}
.tile{background:var(--card);border-radius:10px;padding:1rem}
.tile .k{color:var(--ink2);font-size:.85rem}.tile .v{font-size:1.9rem;font-weight:650;line-height:1.2}
.tile .s{color:var(--muted);font-size:.85rem}
.dot{display:inline-block;width:.7rem;height:.7rem;border-radius:3px;margin-right:.35rem;vertical-align:-.05rem}
.dot.pass,.seg.pass{background:var(--pass)}.dot.fail,.seg.fail{background:var(--fail)}
.dot.unknown,.seg.unknown{background:var(--unknown)}
.legend{display:flex;gap:1.25rem;flex-wrap:wrap;color:var(--ink2);font-size:.9rem;margin:.25rem 0 .75rem}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:.55rem .5rem;border-bottom:1px solid var(--line);vertical-align:middle}
th{color:var(--ink2);font-weight:600;font-size:.85rem}
td.num{font-variant-numeric:tabular-nums;white-space:nowrap}
td.name{overflow-wrap:anywhere;max-width:16rem}
.bar{width:100%;min-width:6rem;height:14px}
.fill{display:flex;gap:2px;height:100%}
.seg{height:100%;min-width:3px}.seg:first-child{border-radius:4px 0 0 4px}.seg:last-child{border-radius:0 4px 4px 0}
.seg:only-child{border-radius:4px}
.cnt{white-space:nowrap;margin-right:.6rem;color:var(--ink2);font-size:.88rem}
.note{background:var(--card);border-radius:10px;padding:1rem 1.1rem;margin-top:1rem}
.note li{margin:.2rem 0}
code{font:.88em ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.scroll{overflow-x:auto}.scroll table{min-width:40rem}td.res{white-space:nowrap}
.tile .v{overflow-wrap:anywhere}
@media print{body{background:#fff;color:#000}}
"""


def render_html(summary):
    t, calls = summary["totals"], summary["calls"]
    e = html.escape
    tiles = [f'<div class="tile"><div class="k">Protected calls checked</div><div class="v">{calls}</div>'
             f'<div class="s">{e(", ".join(summary["modes"]) or "-")} mode</div></div>']
    for s in STATUSES:
        tiles.append(f'<div class="tile"><div class="k"><span class="dot {s}" aria-hidden="true"></span>'
                     f'{STATUS_ICON[s]} {STATUS_LABEL[s]}</div><div class="v">{t[s]}</div>'
                     f'<div class="s">{_pct(t[s], calls)} of calls</div></div>')
    lat = summary["latency"]
    if lat:
        tiles.append(f'<div class="tile"><div class="k">Added latency</div><div class="v">{lat["p50_ms"]} ms</div>'
                     f'<div class="s">median; p95 {lat["p95_ms"]} ms</div></div>')

    legend = "".join(f'<span><span class="dot {s}" aria-hidden="true"></span>{STATUS_ICON[s]} {STATUS_LABEL[s]}</span>'
                     for s in STATUSES)
    tool_max = max((sum(c.values()) for c in summary["by_tool"].values()), default=0)
    tool_rows = "".join(
        f'<tr><td class="name"><code>{e(name)}</code></td><td>{_bar(c, tool_max)}</td>'
        f'<td class="num">{sum(c.values())}</td><td>{_counts_cell(c)}</td></tr>'
        for name, c in summary["by_tool"].items())
    day_max = max((sum(c.values()) for c in summary["by_day"].values()), default=0)
    day_rows = "".join(
        f'<tr><td class="num">{e(day)}</td><td>{_bar(c, day_max)}</td>'
        f'<td class="num">{sum(c.values())}</td><td>{_counts_cell(c)}</td></tr>'
        for day, c in summary["by_day"].items())
    reason_rows = "".join(
        f'<tr><td class="res"><span class="dot {r["status"]}" aria-hidden="true"></span>{STATUS_LABEL[r["status"]]}</td>'
        f'<td><code>{e(r["reason_code"])}</code></td><td class="num">{r["count"]}</td>'
        f'<td>{e(REASONS.get(r["reason_code"], "See specs/outcome-guard-mvp.md."))}</td></tr>'
        for r in summary["reasons"])

    period = (f'{e(summary["first"])} to {e(summary["last"])}' if summary["first"] else "no records")
    servers = e(", ".join(summary["servers"])) or "-"
    skipped = (f'<p class="muted">{summary["skipped_lines"]} malformed log line(s) were skipped.</p>'
               if summary["skipped_lines"] else "")
    generated = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    body = f"""<main>
<h1>Fourgate outcome summary</h1>
<p class="sub">Did the writes your agent reported as done actually land? Each protected call below was checked
against the system of record by an independent read-back.</p>
<p class="muted">Period: {period} &middot; Servers: {servers} &middot; Generated {generated}</p>
<div class="tiles">{"".join(tiles)}</div>
{skipped}
<h2>By tool</h2>
<div class="legend">{legend}</div>
<div class="scroll"><table><thead><tr><th>Server / tool</th><th>Outcomes</th><th>Calls</th><th>Breakdown</th></tr></thead>
<tbody>{tool_rows}</tbody></table></div>
<h2>By day (UTC)</h2>
<div class="scroll"><table><thead><tr><th>Day</th><th>Outcomes</th><th>Calls</th><th>Breakdown</th></tr></thead>
<tbody>{day_rows}</tbody></table></div>
<h2>Reasons</h2>
<div class="scroll"><table><thead><tr><th>Result</th><th>Reason</th><th>Count</th><th>What it means</th></tr></thead>
<tbody>{reason_rows}</tbody></table></div>
<div class="note"><strong>How to read this</strong><ul>
<li><strong>FAIL</strong> means an independent read-back proved the record missing or different after the tool reported success.</li>
<li><strong>UNKNOWN</strong> means Fourgate could not confirm either way. It is never counted as PASS.</li>
<li>In <strong>shadow</strong> mode the agent received the tool's response unchanged; Fourgate only recorded the result.</li>
<li>Added latency is the time Fourgate spent checking each protected call.</li>
</ul></div>
<p class="muted" style="margin-top:1.5rem">Generated locally from <code>outcomes.jsonl</code>. The log and this page contain
structure only: server and tool names, result, reason and timing. No arguments, record values, response bodies or
credentials are stored, and nothing is sent to Fourgate.</p>
</main>"""
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">"
            f"<title>Fourgate Outcome Summary</title><style>{CSS}</style></head><body>{body}</body></html>\n")

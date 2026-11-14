# Measurement package (founder fill-in)

Publishable numbers for limited beta `0.4.0b1`. **Do not invent values.** Run the
commands on an authorized disposable account, then replace every
`<!-- MEASURE:… -->` placeholder.

Reports used for publication must be the redacted files Fourgate writes
(`fourgate-report.*` from scan, `fourgate-summary.html` / `outcomes.jsonl` from
guard). Review them before sharing; redaction is best effort.

## A. Disposable scan rates (PASS / FAIL / UNKNOWN)

### Commands

```bash
# After a configured scan.json (see docs/external-disposable-scan.md)
fourgate scan ./scan.json \
  --confirm-test-account "$FOURGATE_TEST_ACCOUNT" \
  --report-dir "./fourgate-output/measure-scan-$(date -u +%Y%m%dT%H%M%SZ)"
```

```powershell
$stamp = Get-Date -AsUTC -Format 'yyyyMMddTHHmmssZ'
fourgate scan .\scan.json `
  --confirm-test-account $env:FOURGATE_TEST_ACCOUNT `
  --report-dir ".\fourgate-output\measure-scan-$stamp"
```

Repeat for the planned sample size (each run may perform a real write). Prefer
separate report directories per run. Summarize without printing secrets:

```bash
python - <<'PY'
import json, pathlib, collections
root = pathlib.Path("fourgate-output")
counts = collections.Counter()
runs = 0
for report in root.glob("measure-scan-*/fourgate-report.json"):
    runs += 1
    for case in json.loads(report.read_text(encoding="utf-8"))["cases"]:
        counts[case["status"]] += 1
total = sum(counts.values()) or 1
print(f"runs={runs} cases={sum(counts.values())}")
for status in ("PASS", "FAIL", "UNKNOWN"):
    n = counts[status]
    print(f"{status}: {n} ({100.0 * n / total:.1f}%)")
print(f"UNKNOWN_rate={100.0 * counts['UNKNOWN'] / total:.1f}%")
PY
```

### Results table (founder fills)

| Field | Value |
| --- | --- |
| Date (Asia/Karachi) | <!-- MEASURE:scan-date --> |
| Fourgate version | `0.4.0b1` |
| Target server / version | <!-- MEASURE:scan-server --> |
| Disposable account label | <!-- MEASURE:scan-account --> |
| Planned runs / cases | <!-- MEASURE:scan-planned --> |
| Observed PASS count | <!-- MEASURE:scan-pass --> |
| Observed FAIL count | <!-- MEASURE:scan-fail --> |
| Observed UNKNOWN count | <!-- MEASURE:scan-unknown --> |
| **UNKNOWN rate** | <!-- MEASURE:scan-unknown-rate --> |
| Notes (induced vs natural) | <!-- MEASURE:scan-notes --> |
| Report directory names | <!-- MEASURE:scan-report-dirs --> |

---

## B. Runtime shadow latency (`gate_ms`) and UNKNOWN rate

Requires `fourgate guard --mode shadow` with the **2000 ms** verifier budget
unchanged, logging to `outcomes.jsonl`, then `fourgate summary`.

### Commands

```bash
fourgate guard \
  --contracts ./runtime.json \
  --mode shadow \
  --server measure \
  --log ./fourgate-output/measure-outcomes.jsonl \
  -- /path/to/your-stdio-mcp-server
# Drive N protected tools/call from the real client, then stop.
fourgate summary ./fourgate-output/measure-outcomes.jsonl \
  --out ./fourgate-output/measure-summary.html --json
```

```powershell
fourgate guard `
  --contracts .\runtime.json `
  --mode shadow `
  --server measure `
  --log .\fourgate-output\measure-outcomes.jsonl `
  -- C:\path\to\your-stdio-mcp-server.exe
fourgate summary .\fourgate-output\measure-outcomes.jsonl `
  --out .\fourgate-output\measure-summary.html --json
```

Extract latency / rates from the JSON summary or the log:

```bash
python - <<'PY'
import json, pathlib, statistics
records = []
for line in pathlib.Path("fourgate-output/measure-outcomes.jsonl").read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    item = json.loads(line)
    if item.get("status") in ("pass", "fail", "unknown"):
        records.append(item)
total = len(records) or 1
by = {s: sum(1 for r in records if r["status"] == s) for s in ("pass", "fail", "unknown")}
lat = [r["gate_ms"] for r in records if isinstance(r.get("gate_ms"), int)]
print(f"calls={len(records)}")
print(f"PASS={by['pass']} FAIL={by['fail']} UNKNOWN={by['unknown']}")
print(f"UNKNOWN_rate={100.0 * by['unknown'] / total:.1f}%")
if lat:
    lat = sorted(lat)
    p95 = lat[max(0, int(0.95 * len(lat) + 0.999) - 1)]
    print(f"gate_ms_median={statistics.median(lat):.0f}")
    print(f"gate_ms_p95={p95}")
    print(f"gate_ms_max={lat[-1]}")
PY
```

### Results table (founder fills)

| Field | Value |
| --- | --- |
| Date (Asia/Karachi) | <!-- MEASURE:runtime-date --> |
| Fourgate version | `0.4.0b1` |
| Verifier `timeout_ms` | `2000` (must not be raised for this package) |
| Client used | <!-- MEASURE:runtime-client --> |
| Protected tool(s) | <!-- MEASURE:runtime-tools --> |
| Observed calls | <!-- MEASURE:runtime-calls --> |
| PASS / FAIL / UNKNOWN | <!-- MEASURE:runtime-counts --> |
| **UNKNOWN rate** | <!-- MEASURE:runtime-unknown-rate --> |
| **gate_ms median** | <!-- MEASURE:runtime-median-ms --> |
| **gate_ms p95** | <!-- MEASURE:runtime-p95-ms --> |
| **gate_ms max** | <!-- MEASURE:runtime-max-ms --> |
| Cold-start notes | <!-- MEASURE:runtime-cold-start --> |
| Summary HTML path | <!-- MEASURE:runtime-summary-path --> |

---

## C. Publication checklist

- [ ] Numbers above come from disposable-account runs only
- [ ] No credential values appear in shared HTML/JSON (spot-check)
- [ ] UNKNOWN is never described as PASS
- [ ] 2000 ms runtime budget unchanged
- [ ] Stdio-only scope stated; no remote-transport claim
- [ ] Link evidence directories or private artifact hashes without uploading secrets

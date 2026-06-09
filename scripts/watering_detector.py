#!/usr/bin/env python3
"""Detect watering events from the Flower Care soil probe — FUSED EC + moisture.

A single channel is not reliable (verified over 19 days, 2026-05-20..06-08): a
watering shows up as an EC spike on some days, an EC DIP on others, a moisture
step on others, or several at once. So fuse them — a watering is a sharp
DISTURBANCE in either channel:

  * EC step UP   (+)  — feed, OR plain water flushing accumulated salts past the
                       electrodes in dry soil (so EC+ is NOT proof of feed).
  * EC step DOWN (-)  — plain/low-ion water DILUTING the soil solution.
  * moisture step up  — water wetting the capacitive shaft — coarse, laggy,
                       integer %, LEAST reliable (missed a confirmed watering on
                       06-08), but occasionally carries an event EC misses (06-01).

So the EC *sign* is a hint (feed vs plain water), not a verdict. Events are grouped
(one disturbance = one event) and thresholds are PROVISIONAL pending human labels;
decay-rejection is the main remaining tuning.

    .venv/bin/python scripts/watering_detector.py --days 20
    .venv/bin/python scripts/watering_detector.py --file /tmp/fc_hist.json
"""
import os, sys, json, argparse, ssl, urllib.request, datetime as dt

# Flower Care now comes from the in-repo backend (Pi BLE ingest -> sensor_readings),
# keyed by MAC from XIAOMI_SENSORS; default base URL is the backend's published port.
DEFAULT_BACKEND_URL = "http://localhost:8001"

EC_STEP = 80        # uS/cm excursion (either sign) that counts as a disturbance
M_STEP = 3          # moisture-% rise that counts (below this is quantization wiggle)
# Short baseline (the 2 immediately-preceding readings, ~10-15 min) so it TRACKS the
# slow post-feed EC decay and ignores it — only a SHARP change vs the recent value
# triggers. A long baseline misfired on every decay step as a bogus "dilution".
BASELINE_WIN = 2
REFRACTORY_MIN = 180  # a watering's full disturbance+decay is hours; one event per.


def _env(key, default=""):
    path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(path):
        for line in open(path):
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.getenv(key, default)


def cilantro_mac():
    """Cilantro Flower Care MAC from XIAOMI_SENSORS (name match, else first entry)."""
    sensors = json.loads(_env("XIAOMI_SENSORS", "[]"))
    for s in sensors:
        if (s.get("name") or "").lower().startswith("cilantro"):
            return s["mac"]
    return sensors[0]["mac"] if sensors else None


def fetch(start, end, base_url, mac):
    """Clean Flower Care history from the in-repo backend (Pi ingest). Normalises
    recorded_at -> timestamp so series_of works unchanged. Ingest bearer auth."""
    token = _env("INGEST_API_TOKEN")
    req = urllib.request.Request(
        f"{base_url}/sensors/flower-care/{mac}/readings?start_ts={start}&end_ts={end}",
        headers={"Authorization": f"Bearer {token}"} if token else {})
    rows = json.load(urllib.request.urlopen(req))
    for r in rows:
        r["timestamp"] = r["recorded_at"]
    return rows


def series_of(rows):
    return sorted(((r["timestamp"], r["conductivity_us_cm"], r["moisture_pct"]) for r in rows
                   if r.get("conductivity_us_cm") is not None and r.get("moisture_pct") is not None),
                  key=lambda x: x[0])


def _mins(a, b):
    f = lambda t: dt.datetime.fromisoformat(t.replace("Z", "+00:00"))
    return (f(b) - f(a)).total_seconds() / 60


def _median(xs):
    s = sorted(xs); n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def detect(series):
    """series: list of (ts, ec, moist). One disturbance = one event; the i=j skip
    past the scanned window IS the refractory (no separate 'last' bookkeeping)."""
    events, i, n = [], 0, len(series)
    while i < n:
        ts, ec, m = series[i]
        win = series[max(0, i - BASELINE_WIN):i]
        if not win:
            i += 1; continue
        base_ec = _median([x[1] for x in win])
        # min(): moisture only rises on watering, so baseline off the window's LOW
        # value lets a partial rise still trigger. Trade-off: more sensitive to
        # moisture noise — M_STEP is the guard, and moisture is never trusted alone.
        base_m = min(x[2] for x in win)
        if abs(ec - base_ec) >= EC_STEP or m - base_m >= M_STEP:
            peak_ec, peak_m, j = ec - base_ec, m - base_m, i
            while j < n and _mins(ts, series[j][0]) <= REFRACTORY_MIN:
                if abs(series[j][1] - base_ec) > abs(peak_ec):
                    peak_ec = series[j][1] - base_ec
                peak_m = max(peak_m, series[j][2] - base_m)
                j += 1
            chans = []
            if abs(peak_ec) >= EC_STEP:
                chans.append(f"EC{'+' if peak_ec > 0 else '-'}{abs(peak_ec):.0f}")
            if peak_m >= M_STEP:
                chans.append(f"M+{peak_m:.0f}")
            kind = ("EC+ feed/flush?" if peak_ec >= EC_STEP else
                    "EC- dilution/plain-water?" if peak_ec <= -EC_STEP else "moisture-only?")
            events.append({"onset": ts, "base_ec": base_ec, "peak_ec": peak_ec,
                           "peak_m": peak_m, "channels": chans, "kind": kind})
            i = j                       # skip the disturbance window (= the refractory)
        else:
            i += 1
    return events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=20)
    ap.add_argument("--file", help="analyze a saved readings JSON instead of fetching")
    ap.add_argument("--mac", default=None, help="Flower Care MAC (default: Cilantro from XIAOMI_SENSORS)")
    ap.add_argument("--backend-url", default=None, help="in-repo backend base URL (default XIAOMI_BACKEND_URL)")
    a = ap.parse_args()
    if a.file:
        rows = json.load(open(a.file))
    else:
        mac = a.mac or cilantro_mac()
        if not mac:
            sys.exit("no Cilantro MAC in XIAOMI_SENSORS")
        base = a.backend_url or _env("XIAOMI_BACKEND_URL", DEFAULT_BACKEND_URL)
        now = dt.datetime.now(dt.timezone.utc)
        rows = fetch((now - dt.timedelta(days=a.days)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                     now.strftime("%Y-%m-%dT%H:%M:%SZ"), base, mac)
    s = series_of(rows)
    if not s:
        print("0 usable readings"); return
    print(f"{len(s)} readings, {s[0][0]} .. {s[-1][0]}")
    events = detect(s)
    print(f"\n{len(events)} watering event(s) (UTC; +2h local):")
    print(f"{'onset':>17}  {'channels':>16}  {'EC base->excursion':>20}  kind")
    for e in events:
        print(f"{e['onset']:>17}  {' '.join(e['channels']):>16}  "
              f"{e['base_ec']:.0f} -> {e['base_ec']+e['peak_ec']:.0f} "
              f"({e['peak_ec']:+.0f})       {e['kind']}")


if __name__ == "__main__":
    main()

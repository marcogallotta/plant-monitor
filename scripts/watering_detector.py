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

CILANTRO = "3ee7f8a3-9811-45ce-8296-c909a104952b"   # the only soil probe (Flower Care)
# .env's SENSOR_API_URL reads a stale :8001 (now the backend port); sensor server is :8000.
SENSOR_SERVER = "https://laptop.local:8000"

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


def fetch(start, end, server, sensor):
    # verify disabled: the sensor server uses a self-signed cert on the LAN
    # (laptop.local). Same as app/sensors.py. Do NOT copy this pattern to anything
    # internet-facing.
    req = urllib.request.Request(
        f"{server}/sensors/{sensor}/readings?start_ts={start}&end_ts={end}&max_points=5000",
        headers={"X-Api-Key": _env("SENSOR_API_KEY")})
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    return json.load(urllib.request.urlopen(req, context=ctx))


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
    ap.add_argument("--sensor", default=CILANTRO, help="sensor UUID (default: Cilantro Flower Care)")
    ap.add_argument("--server", default=SENSOR_SERVER, help="sensor server base URL")
    a = ap.parse_args()
    if a.file:
        rows = json.load(open(a.file))
    else:
        now = dt.datetime.now(dt.timezone.utc)
        rows = fetch((now - dt.timedelta(days=a.days)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                     now.strftime("%Y-%m-%dT%H:%M:%SZ"), a.server, a.sensor)
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

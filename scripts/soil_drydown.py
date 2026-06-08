#!/usr/bin/env python3
"""Crack #1 of the irrigation product: does measured soil-moisture DRYDOWN track
demand? If the one instrumented pot (the Cilantro Flower Care) loses water faster
when it's hotter/brighter, the water-balance model captures real loss and can be
extended to unprobed zones — the key to scaling sparse sensing to a 100 m² garden.

Pulls the probe history (moisture / local temp / light / EC), splits it into
DRYDOWN segments between waterings (a moisture jump up = a watering), and tests
whether each segment's drydown RATE (%/day) rises with the segment's mean temp and
light. The probe's OWN temp+light are the demand proxies (no forecast join needed
for this first check).

Runs in the backend container (esp32 reachable there):
    docker compose run --rm backend python scripts/soil_drydown.py
"""
import os, sys
from datetime import datetime
import httpx

PROBE_ID = "3ee7f8a3-9811-45ce-8296-c909a104952b"   # Cilantro Flower Care
WATER_JUMP = 4.0          # +%moisture between readings = a watering event
MIN_SEG_HOURS = 6.0       # ignore tiny segments
MIN_DROP = 2.0            # need a real decline to estimate a rate


def fetch(start, end, n=400):
    url = os.environ.get("SENSOR_API_URL", ""); key = os.environ.get("SENSOR_API_KEY", "")
    with httpx.Client(base_url=url, headers={"X-Api-Key": key}, verify=False, timeout=20) as c:
        r = c.get(f"/sensors/{PROBE_ID}/readings",
                  params={"start_ts": start, "end_ts": end, "max_points": n})
        r.raise_for_status()
        return r.json()


def _rank(x):
    order = sorted(range(len(x)), key=lambda i: x[i])
    r = [0] * len(x)
    for pos, i in enumerate(order):
        r[i] = pos
    return r


def spearman(a, b):
    n = len(a)
    if n < 3:
        return float("nan")
    ra, rb = _rank(a), _rank(b)
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
    va = sum((x - ma) ** 2 for x in ra) ** 0.5
    vb = sum((x - mb) ** 2 for x in rb) ** 0.5
    return cov / (va * vb) if va * vb else float("nan")


def _mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def main():
    rows = fetch("2026-05-25T00:00:00Z", "2026-06-09T00:00:00Z")
    rows = [r for r in rows if r.get("moisture_pct") is not None
            and r.get("temperature_c") is not None and r.get("light_lux") is not None]
    rows = sorted(rows, key=lambda r: r["timestamp"])
    t = [datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")) for r in rows]
    m = [float(r["moisture_pct"]) for r in rows]
    temp = [float(r["temperature_c"]) for r in rows]
    light = [float(r["light_lux"]) for r in rows]
    print(f"{len(rows)} readings, {t[0].date()}→{t[-1].date()}, "
          f"moisture {min(m):.0f}–{max(m):.0f}%")

    # Split into drydown segments at each watering (moisture jump up).
    segs, start = [], 0
    for i in range(1, len(m)):
        if m[i] - m[i - 1] >= WATER_JUMP:           # watering -> close prior segment
            segs.append((start, i - 1)); start = i
    segs.append((start, len(m) - 1))

    print(f"\n{'segment (local-ish UTC)':<34}{'hrs':>5}{'drop%':>7}{'rate/d':>8}"
          f"{'Tmean':>7}{'Lmean':>8}")
    rate, Tm, Lm = [], [], []
    for a, b in segs:
        hrs = (t[b] - t[a]).total_seconds() / 3600.0
        drop = m[a] - m[b]
        if hrs < MIN_SEG_HOURS or drop < MIN_DROP:
            continue
        r = drop / (hrs / 24.0)                      # %/day depletion
        tm, lm = _mean(temp[a:b + 1]), _mean(light[a:b + 1])
        rate.append(r); Tm.append(tm); Lm.append(lm)
        print(f"{str(t[a])[:16]}→{str(t[b])[11:16]:<11}{hrs:5.0f}{drop:7.0f}"
              f"{r:8.1f}{tm:7.1f}{lm:8.0f}")

    print(f"\n{len(rate)} drydown segments")
    if len(rate) >= 3:
        print(f"Spearman  drydown-rate vs Tmean = {spearman(rate, Tm):+.2f}   "
              f"vs Lmean = {spearman(rate, Lm):+.2f}")
        print("(positive = hotter/brighter -> faster drydown = demand drives loss = model viable)")


if __name__ == "__main__":
    main()

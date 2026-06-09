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
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.water_demand as wd
import scripts.forecast_et0 as fe

PROBE_ID = "3ee7f8a3-9811-45ce-8296-c909a104952b"   # Cilantro Flower Care (moisture/temp/light/EC)
SOUTH_ID = "1be4c2d4-988c-40c4-8b22-3304f352c3dc"   # railing SwitchBot -> ambient RH for VPD
WATER_JUMP = 4.0          # +%moisture between readings = a watering event
MIN_SEG_HOURS = 6.0       # ignore tiny segments
MIN_DROP = 2.0            # need a real decline to estimate a rate
START, END = "2026-05-25T00:00:00Z", "2026-06-10T00:00:00Z"


def fetch(sensor_id, start, end, n=400):
    url = os.environ.get("SENSOR_API_URL", ""); key = os.environ.get("SENSOR_API_KEY", "")
    with httpx.Client(base_url=url, headers={"X-Api-Key": key}, verify=False, timeout=20) as c:
        r = c.get(f"/sensors/{sensor_id}/readings",
                  params={"start_ts": start, "end_ts": end, "max_points": n})
        r.raise_for_status()
        return r.json()


def _ts(r):
    return datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00"))


def nearest(series_t, series_v, t):
    """Value in series nearest in time to t (series_t sorted)."""
    best, bv = 1e18, float("nan")
    for st, sv in zip(series_t, series_v):
        d = abs((st - t).total_seconds())
        if d < best:
            best, bv = d, sv
    return bv


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


def linfit(x, y):
    """Least-squares y = slope*x + intercept; returns (slope, intercept, r2)."""
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((xi - mx) ** 2 for xi in x)
    sxy = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    slope = sxy / sxx if sxx else 0.0
    inter = my - slope * mx
    ss_res = sum((y[i] - (slope * x[i] + inter)) ** 2 for i in range(n))
    ss_tot = sum((yi - my) ** 2 for yi in y)
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
    return slope, inter, r2


def ks_intervals(t, m, vpd, segs):
    """Per-reading-interval drydown WITHIN segments, VPD-normalised — the Crack #2
    Ks(moisture) probe. Model each interval as rate = k·VPD·Ks(moisture); then
    y = rate/VPD = k·Ks(moisture) divides demand out, so any remaining trend of y
    vs the interval's moisture LEVEL is the supply-limitation signature (FAO-56 Ks:
    drydown slows as the soil dries below readily-available water). Returns parallel
    lists (y, moisture_mid, rate, vpd_mid) over drydown intervals only."""
    y, mmid, rate, vmid = [], [], [], []
    for a, b in segs:
        for i in range(a, b):
            dt_d = (t[i + 1] - t[i]).total_seconds() / 86400.0
            if dt_d <= 0:
                continue
            r = (m[i] - m[i + 1]) / dt_d          # %/day; >0 = drying
            v = (vpd[i] + vpd[i + 1]) / 2.0
            if r <= 0 or v <= 0:                   # skip noise upticks / bad VPD
                continue
            rate.append(r); vmid.append(v)
            mmid.append((m[i] + m[i + 1]) / 2.0)
            y.append(r / v)
    return y, mmid, rate, vmid


def main():
    rows = fetch(PROBE_ID, START, END)
    rows = [r for r in rows if r.get("moisture_pct") is not None
            and r.get("temperature_c") is not None and r.get("light_lux") is not None]
    rows = sorted(rows, key=lambda r: r["timestamp"])
    t = [_ts(r) for r in rows]
    m = [float(r["moisture_pct"]) for r in rows]
    temp = [float(r["temperature_c"]) for r in rows]
    light = [float(r["light_lux"]) for r in rows]

    # Ambient RH (railing SwitchBot) -> per-probe-reading VPD using the pot's OWN
    # temp + nearest-in-time ambient RH. VPD = the proper instantaneous demand driver.
    srh = [r for r in fetch(SOUTH_ID, START, END) if r.get("humidity_pct") is not None]
    st = [_ts(r) for r in srh]; sv = [float(r["humidity_pct"]) for r in srh]
    vpd = [wd.vpd(temp[i], nearest(st, sv, t[i])) for i in range(len(t))]

    # Daily ET0 from the forecast (proper reference demand), one value per date.
    et0_by_day = {row["date"]: row["et0"] for row in fe.daily_et0(fe.fetch_weather(START[:10], END[:10]))}

    print(f"{len(rows)} readings, {t[0].date()}→{t[-1].date()}, moisture {min(m):.0f}–{max(m):.0f}%; "
          f"ambient RH {min(sv):.0f}–{max(sv):.0f}%; ET0 days {len(et0_by_day)}")

    # Split into drydown segments at each watering (moisture jump up).
    segs, start = [], 0
    for i in range(1, len(m)):
        if m[i] - m[i - 1] >= WATER_JUMP:           # watering -> close prior segment
            segs.append((start, i - 1)); start = i
    segs.append((start, len(m) - 1))

    print(f"\n{'segment start':<18}{'hrs':>5}{'rate/d':>8}{'Tmean':>7}{'VPDmn':>7}{'ET0mn':>7}")
    rate, Tm, Vm, Em = [], [], [], []
    for a, b in segs:
        hrs = (t[b] - t[a]).total_seconds() / 3600.0
        drop = m[a] - m[b]
        if hrs < MIN_SEG_HOURS or drop < MIN_DROP:
            continue
        r = drop / (hrs / 24.0)                      # %/day depletion
        tm = _mean(temp[a:b + 1]); vm = _mean(vpd[a:b + 1])
        em = _mean([et0_by_day.get(str(t[i].date()), float("nan")) for i in range(a, b + 1)])
        rate.append(r); Tm.append(tm); Vm.append(vm); Em.append(em)
        print(f"{str(t[a])[:16]:<18}{hrs:5.0f}{r:8.1f}{tm:7.1f}{vm:7.2f}{em:7.2f}")

    print(f"\n{len(rate)} drydown segments — Spearman of drydown-rate vs each demand proxy:")
    if len(rate) >= 3:
        print(f"  air temp     {spearman(rate, Tm):+.2f}")
        print(f"  VPD          {spearman(rate, Vm):+.2f}   (temp + humidity)")
        print(f"  ET0 (FAO-56) {spearman(rate, Em):+.2f}   (the reference demand)")
        print("(higher = better predictor of real water loss = stronger water-balance model)")
        k, c, r2 = linfit(Vm, rate)
        print(f"\nDepletion model:  drydown ≈ {k:.1f}·VPD {c:+.1f}  (%moisture/day, R²={r2:.2f})")
        print("k = this pot's depletion coefficient (%/day per kPa VPD). Calibrate k per zone with a")
        print("probe, then DRIVE every unprobed zone's drydown from sensor VPD — the sparse-sensing scale path.")

    # --- Crack #2: does drydown SLOW as the soil dries? (FAO-56 Ks(moisture)) ---
    y, mm, rt, vm = ks_intervals(t, m, vpd, segs)
    print(f"\nKs(moisture) probe — {len(y)} drydown intervals (within-segment, VPD-normalised):")
    if len(y) >= 6:
        # y = rate/VPD = k·Ks(moisture). If Ks ramps with moisture, y rises with the
        # moisture LEVEL — positive Spearman. (Raw rate-vs-moisture is confounded by VPD.)
        print(f"  Spearman(rate, VPD)            {spearman(rt, vm):+.2f}   (demand — expect strong +)")
        print(f"  Spearman(rate, moisture)       {spearman(rt, mm):+.2f}   (raw, VPD-confounded)")
        print(f"  Spearman(rate/VPD, moisture)   {spearman(y, mm):+.2f}   <- Ks signal: + = drier→slower")
        # Tercile means of y across the moisture range make the ramp legible.
        order = sorted(range(len(mm)), key=lambda i: mm[i])
        k3 = max(1, len(order) // 3)
        lo, hi = order[:k3], order[-k3:]
        ylo, yhi = _mean([y[i] for i in lo]), _mean([y[i] for i in hi])
        mlo, mhi = _mean([mm[i] for i in lo]), _mean([mm[i] for i in hi])
        print(f"  driest third  (moisture~{mlo:4.0f}%):  rate/VPD = {ylo:.1f}")
        print(f"  wettest third (moisture~{mhi:4.0f}%):  rate/VPD = {yhi:.1f}")
        sig = spearman(y, mm)
        if sig >= 0.2:
            print("  => supports a Ks(moisture) term (drydown slows as soil dries). Needs more")
            print("     probe-days to fit a threshold; per-reading quantisation still adds noise.")
        elif sig <= -0.2:
            print("  => NO Ks slowdown (sign is reversed): demand-normalised drydown is flat-to-")
            print("     higher when drier. Consistent with the pot staying ABOVE the FAO-56 stress")
            print("     threshold (kept watered) so Ks never bites, plus Flower Care nonlinearity.")
            print("     Don't add a Ks term to the production model on this evidence.")
        else:
            print("  => no clear Ks(moisture) signal yet at this moisture range / probe-day count.")
    else:
        print("  too few intervals — gather more probe-days.")


if __name__ == "__main__":
    main()

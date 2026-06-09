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
import os, sys, json
from datetime import datetime
import httpx
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.water_demand as wd
import scripts.forecast_et0 as fe
import scripts.watering_detector as wdet

# Flower Care now comes from the in-repo backend (Pi BLE ingest -> sensor_readings),
# keyed by MAC from XIAOMI_SENSORS. The railing SwitchBot (ambient RH for VPD) and the
# weather feed still come from the esp32 server via SENSOR_API_URL.
FLOWER_CARE_API_URL = os.environ.get("FLOWER_CARE_API_URL", "http://backend:8000")
SOUTH_ID = "1be4c2d4-988c-40c4-8b22-3304f352c3dc"   # railing SwitchBot -> ambient RH for VPD
MIN_SEG_HOURS = 6.0       # ignore tiny segments
MIN_DROP = 2.0            # need a real decline to estimate a rate
START, END = "2026-05-25T00:00:00Z", "2026-06-10T00:00:00Z"


def fetch(sensor_id, start, end, n=5000):
    """esp32 server (SwitchBot ambient RH + weather) — by sensor UUID."""
    url = os.environ.get("SENSOR_API_URL", ""); key = os.environ.get("SENSOR_API_KEY", "")
    with httpx.Client(base_url=url, headers={"X-Api-Key": key}, verify=False, timeout=20) as c:
        r = c.get(f"/sensors/{sensor_id}/readings",
                  params={"start_ts": start, "end_ts": end, "max_points": n})
        r.raise_for_status()
        return r.json()


def cilantro_mac():
    """Cilantro Flower Care MAC from XIAOMI_SENSORS (name match, else first entry)."""
    sensors = json.loads(os.environ.get("XIAOMI_SENSORS", "[]"))
    for s in sensors:
        if (s.get("name") or "").lower().startswith("cilantro"):
            return s["mac"]
    return sensors[0]["mac"] if sensors else None


def fetch_flowercare(mac, start, end):
    """Clean Flower Care history from the in-repo backend (Pi ingest). Normalises the
    new row shape (recorded_at, lux) to the legacy names the rest of this script uses
    (timestamp, light_lux)."""
    token = os.environ.get("INGEST_API_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with httpx.Client(base_url=FLOWER_CARE_API_URL, headers=headers, timeout=30) as c:
        r = c.get(f"/sensors/flower-care/{mac}/readings",
                  params={"start_ts": start, "end_ts": end})
        r.raise_for_status()
    return [{"timestamp": x["recorded_at"], "moisture_pct": x["moisture_pct"],
             "temperature_c": x["temperature_c"], "light_lux": x["lux"],
             "conductivity_us_cm": x["conductivity_us_cm"]} for x in r.json()]


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


def drydown_segments(t, m, onsets):
    """Drydown spans BETWEEN fused watering events (onsets = reading indices from
    watering_detector). Each event closes the prior drydown at the reading before it;
    the next drydown starts at the moisture PEAK inside the event's settle window, so
    the wetting rise + decay is excluded rather than counted as 'drydown'. Replaces the
    old moisture-jump split, which missed EC-only waterings and merged two drydowns."""
    segs, start = [], 0
    for oi in sorted(set(onsets)):
        if oi - 1 > start:
            segs.append((start, oi - 1))
        j, peak = oi, oi                              # moisture peak within settle window
        while j < len(t) and (t[j] - t[oi]).total_seconds() / 60.0 <= wdet.REFRACTORY_MIN:
            if m[j] >= m[peak]:
                peak = j
            j += 1
        start = peak
    if start < len(t) - 1:
        segs.append((start, len(t) - 1))
    return segs


def ks_intervals(t, m, vpd, segs):
    """Per-reading-interval drydown WITHIN segments, VPD-normalised — the Crack #2
    Ks(moisture) probe. Model each interval as rate = k·VPD·Ks(moisture); then
    y = rate/VPD = k·Ks(moisture) divides demand out, so any remaining trend of y
    vs the interval's moisture LEVEL is the supply-limitation signature (FAO-56 Ks:
    drydown slows as the soil dries below readily-available water). Returns parallel
    lists (y, moisture_mid, rate, vpd_mid) over drydown intervals only."""
    # Flower Care moisture is integer-quantised, so a single 1% step over a few minutes
    # reads as ~hundreds of %/day. Compare readings at least MIN_DT_H apart so one
    # quantisation step can't dominate the rate (high-res data makes this essential).
    MIN_DT_H = 2.0
    y, mmid, rate, vmid = [], [], [], []
    for a, b in segs:
        i = a
        while i < b:
            j = i + 1
            while j <= b and (t[j] - t[i]).total_seconds() / 3600.0 < MIN_DT_H:
                j += 1
            if j > b:
                break
            dt_d = (t[j] - t[i]).total_seconds() / 86400.0
            r = (m[i] - m[j]) / dt_d              # %/day; >0 = drying
            v = (vpd[i] + vpd[j]) / 2.0
            if r > 0 and v > 0:                    # skip noise upticks / bad VPD
                rate.append(r); vmid.append(v)
                mmid.append((m[i] + m[j]) / 2.0)
                y.append(r / v)
            i = j
    return y, mmid, rate, vmid


def main():
    mac = cilantro_mac()
    if not mac:
        sys.exit("no Cilantro MAC in XIAOMI_SENSORS")
    rows = fetch_flowercare(mac, START, END)
    rows = [r for r in rows if r.get("moisture_pct") is not None
            and r.get("temperature_c") is not None and r.get("light_lux") is not None
            and r.get("conductivity_us_cm") is not None]
    rows = sorted(rows, key=lambda r: r["timestamp"])
    if not rows:
        sys.exit(f"no Flower Care readings {START[:10]}..{END[:10]} from {FLOWER_CARE_API_URL} "
                 "(Pi ingest may not have backfilled yet — migrate-and-wait)")
    t = [_ts(r) for r in rows]
    ts_str = [r["timestamp"] for r in rows]
    m = [float(r["moisture_pct"]) for r in rows]
    temp = [float(r["temperature_c"]) for r in rows]
    light = [float(r["light_lux"]) for r in rows]
    ec = [float(r["conductivity_us_cm"]) for r in rows]

    # Ambient RH (railing SwitchBot) -> per-probe-reading VPD using the pot's OWN
    # temp + nearest-in-time ambient RH. VPD = the proper instantaneous demand driver.
    srh = [r for r in fetch(SOUTH_ID, START, END) if r.get("humidity_pct") is not None]
    st = [_ts(r) for r in srh]; sv = [float(r["humidity_pct"]) for r in srh]
    vpd = [wd.vpd(temp[i], nearest(st, sv, t[i])) for i in range(len(t))]

    # Daily ET0 from the forecast (proper reference demand), one value per date.
    et0_by_day = {row["date"]: row["et0"] for row in fe.daily_et0(fe.fetch_weather(START[:10], END[:10]))}

    print(f"{len(rows)} readings, {t[0].date()}→{t[-1].date()}, moisture {min(m):.0f}–{max(m):.0f}%; "
          f"ambient RH {min(sv):.0f}–{max(sv):.0f}%; ET0 days {len(et0_by_day)}")

    # Split drydowns at RE-WETTING events only. watering_detector.detect fuses EC +
    # moisture, but for drydown segmentation only events that actually add water bound a
    # segment: a moisture rise, or an EC+ feed/flush. EC- excursions with no moisture
    # rise are dilution OR post-feed decay drift (the detector is explicitly un-tuned for
    # decay) — they do NOT reverse a drydown, so they must not split it. (Verified: a
    # single 06-01→06-05 cool-spell drydown was being chopped by EC-decay false splits.)
    idx = {ts: i for i, ts in enumerate(ts_str)}
    events = wdet.detect(list(zip(ts_str, ec, m)))
    rewet = [e for e in events if e["peak_m"] >= wdet.M_STEP or e["peak_ec"] >= wdet.EC_STEP]
    segs = drydown_segments(t, m, [idx[e["onset"]] for e in rewet])
    print(f"{len(events)} events ({len(rewet)} re-wetting) -> {len(segs)} drydown segments")

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
        print(f"\nDepletion fit:  drydown ≈ {k:.1f}·VPD {c:+.1f}  (%moisture/day, R²={r2:.2f})")
        print("CAUTION: this segment-level coefficient is NOT stable — it swings with watering-event")
        print("segmentation and probe resolution. VPD→drydown holds qualitatively (per-interval below),")
        print("but don't treat k as a fitted constant until known dosing / ground-truth waterings exist.")

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
        lean = ("drier→slower, toward Ks" if sig >= 0.2 else
                "drier→faster, against Ks" if sig <= -0.2 else "flat")
        print(f"  => INCONCLUSIVE: this run leans {lean} (sig={sig:+.2f}), but the sign is")
        print("     METHOD-SENSITIVE — segmentation + moisture quantisation flip it run to run.")
        print("     Treat Ks as unresolved (neither absent nor confirmed). Fitting a reliable k/Ks")
        print("     needs known pump dosing or ground-truth watering labels, not passive days alone.")
    else:
        print("  too few intervals — gather more probe-days.")


if __name__ == "__main__":
    main()

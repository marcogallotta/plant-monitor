#!/usr/bin/env python3
"""Fetch the Open-Meteo forecast/archive from the esp32 server and compute daily
FAO-56 ET0 (the weather demand term) via scripts/water_demand.py.

The forecast endpoint is on the esp32 server (same one the sensor proxy reads,
`SENSOR_API_URL` / `SENSOR_API_KEY`), so this must run where that host resolves —
i.e. INSIDE the backend container, like export_reference_regions.py:

    docker compose run --rm backend python scripts/forecast_et0.py
    docker compose run --rm backend python scripts/forecast_et0.py 2026-06-06 2026-06-08

Unit conversions the FAO-56 math needs (Open-Meteo defaults):
  wind_speed_10m  km/h  -> m/s  (/3.6), then 10 m -> 2 m (water_demand.wind_speed_2m)
  shortwave_radiation  W/m^2 hourly -> daily mean W/m^2 -> MJ/m^2/day (x0.0864)
Actual vapour pressure ea is taken from dew_point_2m (FAO-56 eq.14, the preferred
source) rather than RH.

This is the fetch half of the demand adapter; the per-plant join (ET0 x Kc x
camera sun-fraction, VPD per micro-climate) lands once region<->sensor mapping is
wired. See docs/vision-tagging.md "water-balance estimator".
"""
import os, sys, argparse
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import httpx
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.water_demand as wd

KMH_TO_MS = 1.0 / 3.6


def fetch_weather(start: str, end: str):
    url = os.environ.get("SENSOR_API_URL", "")
    key = os.environ.get("SENSOR_API_KEY", "")
    if not url:
        sys.exit("SENSOR_API_URL not set (run inside the backend container)")
    with httpx.Client(base_url=url, headers={"X-Api-Key": key}, verify=False, timeout=15) as c:
        r = c.get("/openmeteo/weather", params={"start_ts": start, "end_ts": end})
        r.raise_for_status()
        return r.json()


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def daily_et0(points, lat=wd.DEFAULT_LAT_DEG, alt=wd.DEFAULT_ALT_M):
    """Group hourly points by UTC date -> one ET0 row per day with full inputs."""
    by_day = defaultdict(list)
    for p in points:
        by_day[p["timestamp"][:10]].append(p)
    rows = []
    for day in sorted(by_day):
        pts = by_day[day]
        temps = [p["temperature_2m"] for p in pts if p.get("temperature_2m") is not None]
        if len(temps) < 2:
            continue                                    # too sparse for Tmin/Tmax
        tmin, tmax = min(temps), max(temps)
        ea = wd.actual_vapour_pressure_dewpoint(_mean([p["dew_point_2m"] for p in pts]))
        u2 = wd.wind_speed_2m(_mean([p["wind_speed_10m"] for p in pts]) * KMH_TO_MS)
        rs = wd.w_per_m2_to_mj_per_m2_day(_mean([p["shortwave_radiation"] for p in pts]))
        doy = datetime.fromisoformat(day).timetuple().tm_yday
        et0 = wd.et0_fao56(tmin, tmax, ea, u2, rs, lat_deg=lat, altitude_m=alt, doy=doy)
        rows.append({"date": day, "tmin": tmin, "tmax": tmax, "ea": ea,
                     "u2": u2, "rs": rs, "rain": sum(p.get("rain") or 0 for p in pts),
                     "et0": et0})
    return rows


def main():
    today = datetime.now(timezone.utc).date()
    ap = argparse.ArgumentParser()
    ap.add_argument("start", nargs="?", default=str(today - timedelta(days=2)))
    ap.add_argument("end", nargs="?", default=str(today))
    a = ap.parse_args()
    rows = daily_et0(fetch_weather(a.start, a.end))
    print(f"daily FAO-56 ET0 @ Aosta ({wd.DEFAULT_LAT_DEG} N, {wd.DEFAULT_ALT_M} m)")
    print(f"{'date':<12}{'Tmin':>6}{'Tmax':>6}{'u2':>6}{'Rs':>7}{'rain':>7}{'ET0':>7}")
    print(f"{'':12}{'C':>6}{'C':>6}{'m/s':>6}{'MJ/m2':>7}{'mm':>7}{'mm/d':>7}")
    for r in rows:
        print(f"{r['date']:<12}{r['tmin']:>6.1f}{r['tmax']:>6.1f}{r['u2']:>6.1f}"
              f"{r['rs']:>7.1f}{r['rain']:>7.1f}{r['et0']:>7.2f}")


if __name__ == "__main__":
    main()

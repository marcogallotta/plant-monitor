#!/usr/bin/env python3
"""Scrape timeanddate.com historic daily minimum temps for frost-tail analysis.

WHY THIS EXISTS
  timeanddate.com (CustomWeather) is the trusted station source for Aosta
  temps (ERA5/Open-Meteo run ~5-8C too cold here - the 9km grid blends in the
  valley walls). The historic endpoint hard-blocks simple fetchers (HTTP 403
  via curl/requests/WebFetch), so this drives a real headless Chromium, which
  gets through. The whole month's hourly series is embedded in the page as a
  `var data={...}` JS blob; we parse that and take the daily minima.

  Primary use: frost-tail (latest cold spring night per year) to sanity-check
  seedling move-out dates. Re-point --station at the new garden location's
  nearest station when the plot is secured.

CAVEATS
  - Dev-only tool. NOT wired into project deps. Needs Playwright + Chromium:
        .venv/bin/pip install playwright
        .venv/bin/python -m playwright install chromium
  - Station figures are a REFERENCE, not on-site: an exposed balcony sensor
    radiatively cools below screened air temp on clear nights (and reads high
    in daytime sun), so true site minima can sit several C below these.
  - Temps are rounded to whole C, so a reported 0C night may be marginally sub-zero.
  - Tied to timeanddate's current page markup; may break if they change it.

USAGE
  .venv/bin/python scripts/aosta_station_temps.py
  .venv/bin/python scripts/aosta_station_temps.py --station 3182997 \
      --years 2021 2026 --months 3 4
"""
import argparse
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

TZ = ZoneInfo("Europe/Rome")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def month_daily_mins(page, station, year, month):
    """Return {day: min_temp_C} for one month, from the embedded JS data blob."""
    url = (f"https://www.timeanddate.com/weather/@{station}"
           f"/historic?month={month}&year={year}")
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    m = re.search(r"var data=(\{.*?\});", page.content())
    if not m:
        return None
    temps = json.loads(m.group(1)).get("temp", [])
    daymin = {}
    for rec in temps:
        dt = datetime.fromtimestamp(rec["date"] / 1000.0, TZ)
        if dt.year != year or dt.month != month:
            continue
        t = rec["temp"]
        if dt.day not in daymin or t < daymin[dt.day]:
            daymin[dt.day] = t
    return daymin


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--station", default="3182997",
                    help="timeanddate location id (default Aosta = 3182997)")
    ap.add_argument("--years", type=int, nargs=2, default=[2021, 2026],
                    metavar=("FROM", "TO"), help="inclusive year range")
    ap.add_argument("--months", type=int, nargs="+", default=[3, 4],
                    help="months to pull (default Mar Apr, the frost window)")
    args = ap.parse_args()
    years = range(args.years[0], args.years[1] + 1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=UA, locale="en-GB",
                                  viewport={"width": 1366, "height": 900})
        page = ctx.new_page()
        for y in years:
            print(f"\n===== {y} =====")
            coldest = None
            last_sub_zero = None
            for mo in args.months:
                daymin = month_daily_mins(page, args.station, y, mo)
                if not daymin:
                    print(f"  NO DATA {y}-{mo:02d}")
                    continue
                for d in sorted(daymin):
                    t = daymin[d]
                    mark = "  <<FROST" if t < 0 else ""
                    print(f"  {y}-{mo:02d}-{d:02d}  min {t:>4}C{mark}")
                    if t < 0:
                        last_sub_zero = (mo, d, t)
                    if coldest is None or t < coldest[2]:
                        coldest = (mo, d, t)
            print(f"  -> coldest night: {coldest}")
            print(f"  -> last sub-zero night: {last_sub_zero}")
        browser.close()


if __name__ == "__main__":
    main()

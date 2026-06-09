#!/usr/bin/env python3
"""Demand side of the per-plant water-balance model: evaporative demand from
weather, ready to wire to the Open-Meteo forecast + the SwitchBot temp/humidity
sensors once SENSOR_API_URL is fixed (see docs/vision-tagging.md "Forecast
source already exists" / "water-balance estimator").

Pure functions, no I/O — fed either live forecast rows or sensor readings. Two
layers:

  VPD  (vapour-pressure deficit, kPa)  — the immediate evaporative-demand signal,
       from temperature + humidity ALONE (what the SwitchBot sensors already give
       per micro-climate). High VPD = thirsty air = fast transpiration.

  ET0  (FAO-56 Penman-Monteith reference evapotranspiration, mm/day) — the
       standard irrigation-scheduling demand, from the forecast vars
       (temperature_2m, relative_humidity_2m / dew_point_2m, wind_speed_10m,
       shortwave_radiation). Per-plant demand = ET0 x crop coeff x SUN FRACTION,
       where sun-fraction is the camera term from sun_hours.py — the two halves
       finally meet here.

Equations + constants follow FAO Irrigation & Drainage Paper 56 (Allen et al.,
1998), Chapter 3 (ET0) and Annex. Validated component-wise in test_water_demand.py
against FAO's own published example values (es, slope, pressure, Ra, ...).

Defaults are for the balcony (Aosta, ~45.7 N, ~580 m); override per site.
"""
import math

# Aosta balcony site defaults (override per call)
DEFAULT_LAT_DEG = 45.74
DEFAULT_ALT_M = 580.0

ALBEDO = 0.23                  # FAO reference grass
STEFAN_BOLTZMANN = 4.903e-9    # MJ K^-4 m^-2 day^-1
SOLAR_CONSTANT = 0.0820        # MJ m^-2 min^-1


# --- vapour pressure ------------------------------------------------------

def saturation_vapour_pressure(t_c: float) -> float:
    """es(T) in kPa. FAO-56 eq.11."""
    return 0.6108 * math.exp(17.27 * t_c / (t_c + 237.3))


def svp_slope(t_c: float) -> float:
    """Slope of the es(T) curve, kPa/degC. FAO-56 eq.13."""
    return 4098.0 * saturation_vapour_pressure(t_c) / (t_c + 237.3) ** 2


def actual_vapour_pressure_rh(t_c: float, rh_pct: float) -> float:
    """ea from temperature + relative humidity, kPa. FAO-56 eq.19 (single T)."""
    return saturation_vapour_pressure(t_c) * rh_pct / 100.0


def actual_vapour_pressure_dewpoint(tdew_c: float) -> float:
    """ea from dew point, kPa. FAO-56 eq.14 — ea = es(Tdew)."""
    return saturation_vapour_pressure(tdew_c)


def vpd(t_c: float, rh_pct: float) -> float:
    """Vapour-pressure deficit, kPa. The evaporative-demand signal from temp+RH."""
    es = saturation_vapour_pressure(t_c)
    return es - actual_vapour_pressure_rh(t_c, rh_pct)


# --- atmosphere -----------------------------------------------------------

def atmospheric_pressure(altitude_m: float) -> float:
    """P in kPa from elevation. FAO-56 eq.7."""
    return 101.3 * ((293.0 - 0.0065 * altitude_m) / 293.0) ** 5.26


def psychrometric_constant(pressure_kpa: float) -> float:
    """gamma in kPa/degC. FAO-56 eq.8 (cp/(eps*lambda) = 0.665e-3)."""
    return 0.665e-3 * pressure_kpa


def wind_speed_2m(u10: float) -> float:
    """Adjust wind from 10 m (forecast height) to 2 m. FAO-56 eq.47."""
    return u10 * 4.87 / math.log(67.8 * 10.0 - 5.42)


# --- radiation ------------------------------------------------------------

def extraterrestrial_radiation(lat_deg: float, doy: int) -> float:
    """Ra in MJ/m^2/day. FAO-56 eq.21. (Daily, top-of-atmosphere.)"""
    phi = math.radians(lat_deg)
    dr = 1.0 + 0.033 * math.cos(2.0 * math.pi / 365.0 * doy)          # inverse rel. distance
    decl = 0.409 * math.sin(2.0 * math.pi / 365.0 * doy - 1.39)       # solar declination
    ws = math.acos(max(-1.0, min(1.0, -math.tan(phi) * math.tan(decl))))  # sunset hour angle
    return (24.0 * 60.0 / math.pi) * SOLAR_CONSTANT * dr * (
        ws * math.sin(phi) * math.sin(decl) + math.cos(phi) * math.cos(decl) * math.sin(ws)
    )


def clear_sky_radiation(ra: float, altitude_m: float) -> float:
    """Rso in MJ/m^2/day. FAO-56 eq.37."""
    return (0.75 + 2e-5 * altitude_m) * ra


def net_radiation(rs: float, tmin_c: float, tmax_c: float, ea: float,
                  ra: float, altitude_m: float, albedo: float = ALBEDO) -> float:
    """Rn (net radiation at the surface) in MJ/m^2/day. FAO-56 eqs.38-40.

    rs = incoming shortwave (solar) radiation, MJ/m^2/day. Rnl uses Tmin/Tmax in
    Kelvin; the Rs/Rso cloudiness factor is clamped (forecast Rs can edge past Rso).
    """
    rns = (1.0 - albedo) * rs
    rso = clear_sky_radiation(ra, altitude_m)
    cloud = max(0.0, min(1.0, rs / rso)) if rso > 0 else 1.0
    rnl = STEFAN_BOLTZMANN * (
        ((tmax_c + 273.16) ** 4 + (tmin_c + 273.16) ** 4) / 2.0
    ) * (0.34 - 0.14 * math.sqrt(max(0.0, ea))) * (1.35 * cloud - 0.35)
    return rns - rnl


def w_per_m2_to_mj_per_m2_day(mean_w_per_m2: float) -> float:
    """Mean irradiance (W/m^2, as the forecast reports shortwave_radiation) over a
    day -> daily total MJ/m^2. 1 W/m^2 sustained for a day = 0.0864 MJ/m^2."""
    return mean_w_per_m2 * 0.0864


# --- reference ET ---------------------------------------------------------

def et0_fao56(tmin_c: float, tmax_c: float, ea_kpa: float, u2: float, rs: float,
              lat_deg: float = DEFAULT_LAT_DEG, altitude_m: float = DEFAULT_ALT_M,
              doy: int = 200, g: float = 0.0) -> float:
    """FAO-56 Penman-Monteith reference ET0 in mm/day (eq.6).

    ea_kpa = actual vapour pressure; u2 = wind at 2 m (use wind_speed_2m); rs =
    incoming solar radiation MJ/m^2/day (use w_per_m2_to_mj_per_m2_day if the
    forecast gives mean W/m^2). G (soil heat flux) ~ 0 for daily steps.
    """
    tmean = (tmin_c + tmax_c) / 2.0
    delta = svp_slope(tmean)
    es = (saturation_vapour_pressure(tmax_c) + saturation_vapour_pressure(tmin_c)) / 2.0
    p = atmospheric_pressure(altitude_m)
    gamma = psychrometric_constant(p)
    ra = extraterrestrial_radiation(lat_deg, doy)
    rn = net_radiation(rs, tmin_c, tmax_c, ea_kpa, ra, altitude_m)
    num = 0.408 * delta * (rn - g) + gamma * (900.0 / (tmean + 273.0)) * u2 * (es - ea_kpa)
    den = delta + gamma * (1.0 + 0.34 * u2)
    return num / den


def plant_demand_mm(et0_mm: float, crop_coeff: float, sun_fraction: float) -> float:
    """Per-plant water demand, mm/day. et0 x Kc x sun-fraction.

    sun_fraction (0..1) is the camera demand term from sun_hours.py — a region in
    full sun pulls the full reference demand; a shaded region pulls a fraction.
    crop_coeff (Kc) is per-species (leafy herbs ~0.9-1.05 mid-season; FAO-56 Table 12).
    """
    return et0_mm * crop_coeff * max(0.0, min(1.0, sun_fraction))


if __name__ == "__main__":
    # Demo on a realistic hot, mostly-clear Aosta summer day (no live data yet).
    tmin, tmax, rh = 16.0, 30.0, 45.0
    rs = w_per_m2_to_mj_per_m2_day(290.0)     # ~290 W/m^2 daily-mean shortwave
    u2 = wind_speed_2m(2.5)
    ea = actual_vapour_pressure_rh((tmin + tmax) / 2.0, rh)
    et0 = et0_fao56(tmin, tmax, ea, u2, rs, doy=190)
    print(f"VPD at 30C/45%RH ........ {vpd(30.0, 45.0):.2f} kPa")
    print(f"ET0 (FAO-56) ............ {et0:.2f} mm/day")
    for name, kc, sun in [("Rocket (full sun)", 1.0, 0.9),
                          ("Basil (part shade)", 1.0, 0.6),
                          ("Mint (shaded)", 0.9, 0.3)]:
        print(f"  demand {name:<20} {plant_demand_mm(et0, kc, sun):.2f} mm/day")

#!/usr/bin/env python3
"""Validate water_demand.py against FAO-56 (Allen et al., 1998) published values.

Component-level checks against numbers FAO prints in its worked examples/tables —
the rigorous way to trust the chain without depending on one end-to-end example.
Run:  python -m scripts.test_water_demand
"""
import math
import scripts.water_demand as wd


class Skip(Exception):
    pass


def approx(a, b, tol):
    assert abs(a - b) <= tol, f"{a} != {b} (tol {tol})"


def test_saturation_vapour_pressure_fao_table():
    # FAO-56 Table 2.3 / eq.11: es(20)=2.338, es(25)=3.168 kPa.
    approx(wd.saturation_vapour_pressure(20.0), 2.338, 0.001)
    approx(wd.saturation_vapour_pressure(25.0), 3.168, 0.002)


def test_svp_slope_fao_table():
    # FAO-56 Annex (slope of vapour pressure): Delta(20)=0.1448, Delta(30)=0.2434.
    approx(wd.svp_slope(20.0), 0.1448, 0.0005)
    approx(wd.svp_slope(30.0), 0.2434, 0.0010)


def test_atmospheric_pressure_fao_example():
    # FAO-56 eq.7: sea level 101.3 kPa; at 1800 m -> 81.8 kPa (FAO Example 2).
    approx(wd.atmospheric_pressure(0.0), 101.3, 0.05)
    approx(wd.atmospheric_pressure(1800.0), 81.8, 0.1)


def test_psychrometric_constant_fao_example():
    # FAO-56 Example 2: at 1800 m, P=81.8 -> gamma = 0.054 kPa/degC.
    approx(wd.psychrometric_constant(81.8), 0.054, 0.001)


def test_wind_2m_conversion():
    # FAO-56 eq.47 factor at 10 m: 4.87/ln(672.58) = 0.748.
    approx(wd.wind_speed_2m(1.0), 0.748, 0.002)


def test_extraterrestrial_radiation_fao_example8():
    # FAO-56 Example 8: lat -20 deg, 3 September (DOY 246) -> Ra = 32.2 MJ/m2/day.
    approx(wd.extraterrestrial_radiation(-20.0, 246), 32.2, 0.3)


def test_clear_sky_radiation():
    # FAO-56 eq.37 at sea level: Rso = 0.75 * Ra.
    approx(wd.clear_sky_radiation(32.2, 0.0), 0.75 * 32.2, 0.01)


def test_vpd_positive_and_zero_at_saturation():
    assert wd.vpd(25.0, 100.0) == 0.0           # saturated air, no deficit
    assert wd.vpd(30.0, 40.0) > wd.vpd(20.0, 40.0)  # hotter air, larger deficit


def test_et0_plausible_and_monotone():
    # No single FAO worked-example hardcoded (input recall risk); instead assert
    # ET0 lands in the physical 1-12 mm/day band and responds correctly.
    ea = wd.actual_vapour_pressure_rh(23.0, 45.0)
    u2 = wd.wind_speed_2m(2.5)
    rs = wd.w_per_m2_to_mj_per_m2_day(290.0)
    hot = wd.et0_fao56(16.0, 30.0, ea, u2, rs, doy=190)
    assert 1.0 < hot < 12.0, hot
    # Cooler, more humid, calmer, dimmer day -> strictly less demand.
    ea2 = wd.actual_vapour_pressure_rh(16.0, 80.0)
    cool = wd.et0_fao56(12.0, 20.0, ea2, wd.wind_speed_2m(1.0),
                        wd.w_per_m2_to_mj_per_m2_day(120.0), doy=190)
    assert cool < hot, (cool, hot)


def test_plant_demand_scales_with_sun():
    et0 = 5.0
    full = wd.plant_demand_mm(et0, 1.0, 1.0)
    half = wd.plant_demand_mm(et0, 1.0, 0.5)
    approx(full, 5.0, 1e-9)
    approx(half, 2.5, 1e-9)
    approx(wd.plant_demand_mm(et0, 1.0, 1.5), 5.0, 1e-9)   # sun_fraction clamped to 1


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = skipped = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
            print(f"PASS {t.__name__}")
        except Skip as e:
            skipped += 1
            print(f"SKIP {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{passed} passed, {skipped} skipped, {failed} failed")
    raise SystemExit(1 if failed else 0)

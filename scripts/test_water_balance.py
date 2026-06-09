#!/usr/bin/env python3
"""Tests for the per-plant water-balance join. Run: python -m scripts.test_water_balance"""
import scripts.water_balance as wb


class Skip(Exception):
    pass


def approx(a, b, tol=1e-9):
    assert abs(a - b) <= tol, f"{a} != {b}"


def test_unit_sensor_maps_chillis_to_west():
    assert wb.unit_sensor(34) == "West"
    assert wb.unit_sensor(36) == "West"
    assert wb.unit_sensor(4) == "South"          # dill -> railing placeholder


def test_demand_is_et0_times_kc_times_sun():
    rows = wb.assemble(5.0, {7: 0.8}, {"South": 2.0})
    r = rows[0]
    approx(r["demand_mm"], 5.0 * 1.0 * 0.8)       # default Kc=1.0
    assert r["sensor"] == "South" and r["vpd_kpa"] == 2.0


def test_kc_override_applies():
    rows = wb.assemble(5.0, {7: 1.0}, {"South": 1.0}, kc_by_unit={7: 0.6})
    approx(rows[0]["demand_mm"], 5.0 * 0.6 * 1.0)


def test_chilli_gets_west_vpd():
    rows = wb.assemble(4.0, {34: 0.5}, {"South": 1.0, "West": 3.2})
    assert rows[0]["sensor"] == "West"
    approx(rows[0]["vpd_kpa"], 3.2)


def test_rows_sorted_by_demand_desc():
    rows = wb.assemble(5.0, {1: 0.2, 2: 0.9, 3: 0.5}, {"South": 2.0})
    demands = [r["demand_mm"] for r in rows]
    assert demands == sorted(demands, reverse=True)


def test_stress_flag_on_high_vpd():
    hi = wb.assemble(5.0, {1: 0.5}, {"South": wb.VPD_STRESS_KPA + 0.1})[0]
    lo = wb.assemble(5.0, {1: 0.5}, {"South": wb.VPD_STRESS_KPA - 0.1})[0]
    assert hi["stress"] is True and lo["stress"] is False


def test_kc_by_species_keyword():
    approx(wb.kc_for_name("Birdseye"), 1.1)       # chilli
    approx(wb.kc_for_name("Hangijiao4"), 1.1)
    approx(wb.kc_for_name("Rosemary"), 0.8)       # woody perennial
    approx(wb.kc_for_name("Lemongrass"), 0.9)
    approx(wb.kc_for_name("Rocket"), 1.0)         # leafy default
    approx(wb.kc_for_name("Peppermint"), 1.0)     # NOT a pepper (keyword regression)


def test_missing_sensor_vpd_is_none_not_crash():
    r = wb.assemble(5.0, {1: 0.5}, {})[0]          # no VPD for the unit's sensor
    assert r["vpd_kpa"] is None and r["stress"] is False
    approx(r["demand_mm"], 2.5)


def test_dual_coeffs_heavy_is_transpiration_dominated():
    # A heavy canopy is transpiration-dominated: Kcb >> Ke even with a wet surface
    # (only ~15% soil exposed). With a DRY surface (kr=0) Ke->0 and Kcb+Ke ~ single Kc.
    kcb, ke = wb.dual_coeffs("Rocket", "heavy", kr=1.0)
    assert kcb > 3 * ke
    kcb_dry, ke_dry = wb.dual_coeffs("Rocket", "heavy", kr=0.0)
    approx(ke_dry, 0.0, 1e-9)
    approx(kcb_dry + ke_dry, wb.kc_for_name("Rocket"), 0.12)


def test_dual_coeffs_bare_wet_is_evap_dominated():
    # Bare freshly-watered bed: tiny Kcb, big soil-evap Ke (the case single-Kc misses).
    kcb, ke = wb.dual_coeffs("Rocket", "bare", kr=1.0)
    assert kcb < 0.3 and ke > kcb
    # Dry surface kills the soil-evap term.
    _, ke_dry = wb.dual_coeffs("Rocket", "bare", kr=0.0)
    approx(ke_dry, 0.0, 1e-9)


def test_dual_coeffs_unknown_bucket_falls_back_heavy():
    assert wb.dual_coeffs("Rocket", "???") == wb.dual_coeffs("Rocket", "heavy")


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

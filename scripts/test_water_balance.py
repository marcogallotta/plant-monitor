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


def test_missing_sensor_vpd_is_none_not_crash():
    r = wb.assemble(5.0, {1: 0.5}, {})[0]          # no VPD for the unit's sensor
    assert r["vpd_kpa"] is None and r["stress"] is False
    approx(r["demand_mm"], 2.5)


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

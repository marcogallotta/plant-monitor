# Backend test performance — findings & options

Investigation of `make test-backend` runtime. All numbers below are **measured**, not
estimated, on 2026-05-30 inside the test stack (`docker-compose.test.yml`, Postgres 16),
running `pytest tests/` with `--durations=0`.

## TL;DR

The suite is **not slow**. 419 tests run in **~43s wall** (~40s pytest-internal). An
earlier investigation claimed "~462 tests in ~3 minutes" with "37 teardowns at 1.00s from
connection-pool contention" — **both claims are false**; see "Corrections" below. The only
real lever is the `clean_tables` teardown, which accounts for ~59% of in-test time but is
cheap per-call and spread across every test.

## Measured baseline

| Run | Tests | pytest internal | wall clock |
|-----|-------|-----------------|------------|
| Coverage **off** | 419 | 39.6s | 43.2s |
| Coverage **on** (current default) | 419 | 41.6s | 47.6s |

The default `make test-backend` runs with `--cov=app --cov-report=term-missing`. Coverage
adds only **~2s internal / ~4s wall** — minor.

### Where in-test time goes (coverage off, 38.05s of measured phase records)

| Phase | Total | n | Mean |
|-------|-------|-----|------|
| **teardown** (`clean_tables`) | **22.4s** | 419 | 53ms |
| call (actual test logic) | 15.1s | 376 | 40ms |
| setup | 0.6s | 31 | 19ms |

The single largest bucket is the autouse `clean_tables` teardown (`backend/tests/conftest.py`):
after **every** test it opens a fresh `engine.connect()`, `TRUNCATE`s 10 tables with
`RESTART IDENTITY CASCADE`, re-inserts 7 seed labels, and commits. Because it is
`autouse=True`, even pure-unit tests that never touch the DB pay this ~53ms cost.

## Corrections to the earlier investigation

- ❌ "~462 tests in ~3 minutes" → actually **419 tests in ~43s wall**. There is no 3-minute problem.
- ❌ "37 teardowns at 1.00s, likely pool contention" → **zero** teardowns reach 1s. Max
  teardown is **0.10s**, mean **0.053s**. The cost is uniform, not spiky; there is no
  measurable connection-pool contention.

## Options (ranked by value / risk)

1. **Do nothing.** At ~43s, the suite is already fast. Recommended unless the time becomes
   a real friction point.

2. **Scope `clean_tables` to DB-touching tests** (low risk).
   Drop `autouse=True`; make it (or the truncation) depend on `db_session` / `client` so
   pure-unit tests skip truncation entirely. Estimated saving: 53ms × number of non-DB
   tests ≈ **3–6s**. Pure cleanup, no behaviour change for DB tests.

3. **Drop coverage from the default target** (low risk, small win).
   ~4s wall. Costs the coverage report; could keep a separate `test-backend-cov` target.

4. **`pytest-xdist` parallelization** (higher effort/risk, biggest win).
   Could roughly halve wall time. Requires: adding `pytest-xdist` to
   `backend/requirements.txt` **and** solving the shared-DB problem — all tests currently
   share the single `plantmonitoring_test` database, so workers would collide on TRUNCATE.
   Needs a DB-per-worker scheme (e.g. `worker_id`-suffixed databases created in a
   session-scoped fixture). Only worth it if the suite grows substantially.

## Notes for whoever implements

- `pytest-xdist` is **not** currently a dependency.
- There is no `pytest.ini` / `pyproject` `addopts`; flags live in `Makefile` (`test-backend`).
- `engine` fixture (session-scoped) already does the expensive `stamp base → drop_all →
  upgrade head` only once per session — that is not per-test overhead.

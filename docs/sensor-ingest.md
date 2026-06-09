# Sensor ingest — Xiaomi Flower Care on the Pi

_Status: design, not yet built._

Adds Flower Care soil-sensor data collection to this repo, running entirely on the Pi Zero 2W.
The `esp32-home-display` stack is left untouched. This is additive: the existing SwitchBot
microclimate proxy (`SensorState`) is **kept** — only the Flower Care path is new.

## Context: what the current sensor proxy actually does

`SENSOR_SENSORS` in `.env` contains three **SwitchBot** MACs (South, South wall, West). The
existing `SensorState` in `app/sensors.py` proxies those to the esp32 server and surfaces them via
`GET /sensors/latest` as microclimate temp/RH. The Flower Care sensor data has never flowed through
`app/sensors.py` — it was only ever read directly by research scripts. This migration adds a new
local storage path for Flower Care; it does not touch the SwitchBot proxy.

## Goals

- Read soil temperature, light, moisture, and conductivity from one or more Flower Care sensors.
- Minimise sensor battery drain — connect infrequently, pull buffered history, disconnect.
- Survive wifi outages of several hours without losing readings.
- Store readings in the existing plant-monitoring DB so they can be correlated with photos.

## Non-goals

- Passive BLE scanning (the current source of reliability problems; dropped entirely).
- Reading the sensor's full deep archive (only entries since last sync are pulled).
- A separate service or separate database.
- Touching the SwitchBot proxy or any SwitchBot data path.
- Updating the research scripts (`soil_drydown.py`, `watering_detector.py`,
  `insolation_experiment.py`) — that is on-path follow-up work (see below).

---

## Architecture

```text
Pi Zero 2W (systemd timer, hourly)
  pi/xiaomi_ingest.py
    ├── flush local queue (wifi was down)
    ├── connect to each sensor via BLE (active, not passive)
    ├── read history entries since last_sync_ts
    ├── convert device-epoch timestamps → UTC wall time
    └── POST /sensors/ingest  ──► FastAPI backend
                                      └── sensor_readings table (Flower Care only)
                                              └── GET /sensors/flower-care/latest
                                              └── GET /sensors/flower-care/{mac}/readings
```

`GET /sensors/latest` (SwitchBot microclimate, proxied via `SensorState`) is unchanged. The new
Flower Care endpoints are separate routes so the two data sources stay decoupled.

The Pi script runs on the host (not inside Docker). BLE stays entirely on the Pi; the backend only
sees plain HTTP. No device passthrough, no Docker changes needed. HTTP POSTs use a 15 s timeout;
a slow or unresponsive backend is treated as a network failure (rows queued, state not advanced).

---

## Pi script — `pi/xiaomi_ingest.py`

Derived from `tools/xiaomi.py` in `esp32-home-display`; passive scan and CLI print modes are
dropped.

### History index order

The Flower Care history API assigns index 0 to the **most recent** entry. The script reads
forward from index 0, stopping when `entry_datetime` falls before `last_sync_ts`. Verified by the
`age_s = device_now − entry_ts` relationship: index 0 has the smallest `age_s`. The loop is also
bounded to ≤ 325 entries (the device's maximum history buffer) so a very stale `last_sync_ts`
cannot trigger an unbounded read.

### BLE handshake — verify before copying

`tools/xiaomi.py` issues `write_gatt_char(MODE_UUID, b"\xA0\x1F")` only in `read_current()` (the
realtime path). The history path (`read_history()`) does **not** send this handshake — it goes
directly to `HIST_CTRL_UUID`. Confirm this is correct on the actual device before copying the
script; if history reads require the mode switch too, add it to the history path.

### Behaviour per run

1. **Queue flush.** If `~/.local/state/plant-monitoring/xiaomi_queue.jsonl` exists, read it and
   attempt to POST in chunks of 200 rows. Any 2xx response — including `{"inserted": 0, "skipped":
   200}` — is a successful flush; remove those rows from the file (rewrite without them). Error
   handling by response type:

   | Response | Action |
   |----------|--------|
   | 2xx | success — remove rows, advance state |
   | 400 / 422 | bad rows — quarantine to `xiaomi_queue_bad.jsonl` with response body logged; remove from main queue |
   | 401 / 403 / 429 / 5xx / network error | transient or config fault — leave rows in queue, retry next run |

   Local JSON parse errors go straight to `xiaomi_queue_bad.jsonl` without a POST attempt.
2. **BLE reads.** For each configured sensor MAC:
   a. Connect via `BleakClient` with an explicit connect timeout (10 s).
   b. Read `EPOCH_UUID` to get `device_now` (device's internal seconds counter).
   c. Pull history entries from index 0, up to 325, stopping when `entry_datetime < last_sync_ts`.
   d. Convert each entry's device timestamp to UTC: `wall_now − timedelta(seconds=device_now − entry_ts)`.
   e. Discard entries with `age_s < 0` (clock skew / sensor reset).
   f. Disconnect.
3. **POST.** Send new rows to `POST /sensors/ingest` in chunks of 200.
4. **State update.** On any 2xx POST — regardless of `inserted`/`skipped` split — advance
   `last_sync_ts` **per MAC** to the maximum `recorded_at` for that MAC in the successfully posted
   batch. When a chunk contains rows from multiple sensors, each MAC is advanced independently.
   This correctly handles the crash-after-insert-before-state-update case: a retry returns all
   skipped, but the rows are safe and state should still advance. State is written to
   `~/.local/state/plant-monitoring/xiaomi_state.json` (`{mac: iso_timestamp}`). On non-2xx or
   network failure the rows are appended to the queue file and `last_sync_ts` is not advanced.

The queue directory (`~/.local/state/plant-monitoring/`) is writable by the `pi` user without
any `sudo` or `chown` steps.

`Type=oneshot` in the systemd unit means a new run will not start while the previous one is still
active. The main hanging risk is a stuck BLE connect; the 10 s connect timeout and read timeouts
(5 s per characteristic) bound the worst-case run time.

### Configuration

Env vars (read from the same `.env` the backend uses):

| Var | Example |
|-----|---------|
| `XIAOMI_SENSORS` | `[{"mac":"5C:85:7E:14:43:45","name":"South bed"}]` |
| `XIAOMI_BACKEND_URL` | `http://localhost:8001` |
| `INGEST_API_TOKEN` | _(existing token, reused)_ |

`name` is sent with each reading for convenience but is denormalised — a rename would create mixed
names across history. Treat `mac` as the canonical key everywhere; look up a human name from
`XIAOMI_SENSORS` at display time if needed.

### Battery impact

One active connect + history read takes ~3–5 s and ~0.05 mAh at the sensor. At hourly cadence
that is well within the Flower Care's ~1-year battery budget (the passive-scan mode was hitting the
sensor for minutes at a time due to repeated advertisement retries).

---

## Backend changes

### DB — new table `sensor_readings`

Migration `0015_sensor_readings.py`:

```sql
CREATE TABLE sensor_readings (
    id                 SERIAL PRIMARY KEY,
    mac                TEXT NOT NULL,
    name               TEXT,
    recorded_at        TIMESTAMPTZ NOT NULL,
    temperature_c      REAL,
    lux                INTEGER,
    moisture_pct       INTEGER,
    conductivity_us_cm INTEGER
);

CREATE UNIQUE INDEX sensor_readings_mac_recorded_at_uniq
    ON sensor_readings (mac, recorded_at);

CREATE INDEX sensor_readings_recorded_at_idx ON sensor_readings (recorded_at);
```

`recorded_at` is the wall-clock UTC time derived from the device epoch at read time — not an ingest
timestamp. The `TIMESTAMPTZ` column stores UTC; the backend normalises offset-aware datetimes to UTC
before inserting.

### Ingest endpoint — `POST /sensors/ingest`

Added to `app/routers/sensors.py`. Accepts a JSON array:

```json
[
  {
    "mac": "5C:85:7E:14:43:45",
    "name": "South bed",
    "recorded_at": "2026-06-09T08:00:00Z",
    "temperature_c": 21.5,
    "lux": 4200,
    "moisture_pct": 38,
    "conductivity_us_cm": 142
  }
]
```

All four reading fields are optional (Flower Care history entries always carry all four, but the
schema stays lenient for future sensors). `recorded_at` must carry a UTC offset — a naive datetime
returns 400. The endpoint normalises all timestamps to UTC before inserting.

Auth: existing `INGEST_API_TOKEN` bearer — same token the camera uploader uses. No new secret
needed.

Upsert behaviour: `INSERT … ON CONFLICT (mac, recorded_at) DO NOTHING`. Duplicate entries (queue
replay, retry) are silently skipped.

Returns `{"inserted": N, "skipped": N}`.

### New read endpoints

`GET /sensors/flower-care/latest` — one row per distinct MAC using
`DISTINCT ON (mac) … ORDER BY mac, recorded_at DESC`. Staleness threshold is **90 minutes**
(1.5× the ingest interval) so a reading stays non-stale across one missed run. A sensor that goes
silent stays on the list marked stale — it does not drop off.

`GET /sensors/flower-care/{mac}/readings?start_ts=…&end_ts=…` — readings for one MAC in a time
window, ordered by `recorded_at`. Used by future analysis scripts and by `readings_around` in the
photo-context endpoint.

### `app/sensors.py` — no changes

`SensorState` and `SENSOR_API_URL` / `SENSOR_API_KEY` / `SENSOR_SENSORS` are **unchanged**. The
SwitchBot microclimate proxy continues to serve `GET /sensors/latest` exactly as before. Only new
code is added.

### Env var changes

No env vars are removed. `XIAOMI_SENSORS` is added (Pi script only; the backend does not read it).

---

## Systemd units — `pi/systemd/plant-xiaomi.{service,timer}`

Follows the convention of the existing Pi units in `pi/systemd/` (system units with `User=pi`),
not the `plant-stabilize` pattern (which is a user unit on the laptop).

**`plant-xiaomi.service`**

```ini
[Unit]
Description=Xiaomi Flower Care ingest
After=network.target

[Service]
Type=oneshot
User=pi
WorkingDirectory=/home/pi/plant-monitoring
EnvironmentFile=/home/pi/plant-monitoring/.env
ExecStart=/home/pi/plant-monitoring/.venv/bin/python \
    /home/pi/plant-monitoring/pi/xiaomi_ingest.py
```

**`plant-xiaomi.timer`**

```ini
[Unit]
Description=Run Xiaomi ingest hourly

[Timer]
OnCalendar=*:05
Persistent=true

[Install]
WantedBy=timers.target
```

`Persistent=true` means a missed run (Pi was off) fires once on next boot rather than being
skipped. `OnCalendar=*:05` — five minutes past the hour, after the camera capture at `:00`.

Install (same pattern as `plant-capture`):

```sh
sudo cp pi/systemd/plant-xiaomi.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now plant-xiaomi.timer
```

---

## Testing

**Pi script (no BLE hardware):**

- `parse_history_entry` and `entry_datetime` with representative byte payloads.
- Queue flush: POST fails → rows land in queue file; next run flushes them; `last_sync_ts` is not
  advanced on failure and is advanced to `max(recorded_at)` on success.
- Duplicate queue replay: re-posting the same rows returns the correct `skipped` count; queue is
  cleared.
- Malformed queue row: written to `_bad.jsonl`, does not block the rest of the flush.

**Backend:**

- `POST /sensors/ingest`: batch insert, assert `inserted` count; re-POST, assert `skipped` count.
- `recorded_at` without UTC offset returns 400.
- `GET /sensors/flower-care/latest` and `GET /sensors/flower-care/{mac}/readings` tested against
  fixture rows.
- Staleness: a row 89 minutes old is not stale; a row 91 minutes old is.
- POST with all rows already in DB returns `{"inserted": 0, "skipped": N}` with 2xx; queue is
  cleared and `last_sync_ts` is advanced (covers crash-after-insert-before-state-update).

BLE hardware is not mocked — the Pi script has no unit tests for `BleakClient` calls.

---

## Implementation stages

### Stage 1 — data collection

Gets data flowing into the DB. Verifiable end-to-end on the Pi immediately.

- Migration `0015_sensor_readings`
- `POST /sensors/ingest`
- `pi/xiaomi_ingest.py` (BLE read, queue, POST)
- `pi/systemd/plant-xiaomi.{service,timer}`
- Tests: ingest endpoint + Pi script pure-logic functions

### Stage 2 — read endpoints

Surfaces Flower Care data to the dashboard and future consumers.

- `GET /sensors/flower-care/latest`
- `GET /sensors/flower-care/{mac}/readings`
- Tests: both endpoints + staleness boundary

### Stage 3 — script repoint (critical path)

The migration only delivers analytical value once this is done. Until then, drydown and soil
analysis remain on the old (potentially corrupt) esp32 data.

- Repoint `soil_drydown.py`, `watering_detector.py`, `insolation_experiment.py` from esp32 UUID
  to `sensor_readings` by MAC

---

## Follow-up work — on the critical path

The primary payoff of this migration is clean Flower Care data for drydown and soil analysis. That
payoff is not realised until the research scripts are repointed:

- `soil_drydown.py` and `insolation_experiment.py` use UUID `3ee7f8a3-9811-45ce-8296-c909a104952b`
  (the esp32 server's internal ID for the Cilantro Flower Care sensor). Post-migration, these must
  query `sensor_readings` by MAC instead. This is **not** optional cleanup — the k/Ks drydown
  question does not move until it is done.
- `watering_detector.py` similarly calls the esp32 server directly and will need the same repoint.

**Cutover.** Record the timestamp of the first successful Pi run. Pre-cutover readings live in the
esp32 server's DB only; they are not imported here.

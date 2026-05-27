# Plant Tracking System — Stage 5 Design

## Sensor Context Read-Through Integration

## Goal

Show environmental sensor context around plant photos/events without duplicating sensor data into Plant Tracker.

Plant Tracker should read from the existing sensor API and display relevant readings near photos, locations, and growing units.

## Core principle

```text
Sensor API remains source of truth.
Plant Tracker only maps sensors to locations and displays context.
```

## Existing sensor API

Use the existing sensor API as the upstream source.

Relevant endpoints include:

```text
GET /sensors
GET /sensors/latest
GET /sensors/{sensor_id}/readings
GET /openmeteo/weather
GET /predict/temperature
```

Look at the code in ~/esp32-home-display/server/ for the full API. The API is currently hosted on https://laptop.local:8000/ but this should be in env.

Stage 5 should mainly use:

```text
/sensors/latest
/sensors/{sensor_id}/readings
```

Weather and prediction endpoints stay out of scope unless trivial.

## Scope

Stage 5 includes:

- config-based mapping from external sensor IDs to Plant Tracker locations
- latest sensor display per mapped location
- sensor readings around photo timestamps
- sensor readings around event timestamps if useful
- dashboard display of nearby temperature/humidity context
- graceful handling when the sensor API is offline

## Non-goals

Stage 5 does not include:

- local duplication of sensor history
- sensor database tables in Plant Tracker
- predictions/rules
- alerts/reminders
- irrigation control
- sensor-driven diagnosis
- complex microclimate modelling
- mapping sensors directly to growing units, unless obvious later

## Sensor mapping

Add config, not DB, for now.

Example:

```text
{
  "sensor_api_base_url": "http://laptop.local:8000",
  "sensors": [
    {
      "mac": "AA:BB:CC:DD:EE:01",
      "name": "Railing sensor"
    },
    {
      "mac": "AA:BB:CC:DD:EE:02",
      "name": "Wall sensor"
    },
    {
      "mac": "AA:BB:CC:DD:EE:03",
      "name": "Indoor/reference sensor"
    }
  ]
}```

Each configured sensor has:

- `mac`: real SwitchBot MAC used to query the sensor API
- `name`: display label in Plant Tracker

Do not map sensors to growing units yet.

Do not require Plant Tracker locations yet. Location mapping can be added later if useful.

Get current South, South wall and West sensors from ~/esp32-home-display/data/config.json

This may become more nuanced later because the balcony has microclimates, such as rail-side and wall-side sensors. For now, keep it simple and learn from use.

## Dashboard behaviour

### Latest location context

For each mapped location, show latest:

```text
temperature
humidity
last reading time
sensor label
offline/stale warning
```

### Photo context

When a photo is opened, show sensor readings near the photo time.

Suggested window:

```text
photo captured_at ± 60 minutes
```

Display simply:

```text
nearest reading before photo
nearest reading after photo
or small list/table around the time
```

No complex charts required yet.

### Event context

If easy, show readings around event time using the same logic.

## Backend proxy endpoints

Plant Tracker should proxy the sensor API rather than requiring dashboard JavaScript to know all upstream details.

Add:

```text
GET /sensors/latest
GET /sensors/photos/{photo_id}
GET /sensors/events/{event_id}
```

These endpoints:

- read Plant Tracker config
- call external sensor API
- return compact context
- fail gracefully if sensor API is unavailable

## Failure behaviour

If the sensor API is down:

```text
show "sensor API unavailable"
do not break photo dashboard
do not block uploads/notes/events
```

If a mapped sensor has no readings:

```text
show "no readings available"
```

If readings are stale:

```text
show stale warning
```

## Suggested step breakdown

### 5.1 — Config and sensor API client

- Add sensor API base URL config.
- Add location/sensor mapping config.
- Add small HTTP client wrapper.
- Add tests with mocked sensor API responses.

### 5.2 — Latest sensor context

- Add `/sensors/latest`.
- Return latest readings grouped by mapped location.
- Dashboard shows latest temp/humidity/staleness.

### 5.3 — Photo-time sensor context

- Add `/sensors/photos/{photo_id}`.
- Fetch readings around `photo.captured_at`.
- Dashboard photo modal shows readings near photo time.

### 5.4 — Event-time sensor context

- Add `/sensors/events/{event_id}` if easy.
- Same pattern as photo context.

### 5.5 — Usage checkpoint

- Use it for real balcony photos.
- Decide later whether to add charts, local caching, weather, or predictions.

## Acceptance criteria

Stage 5 is done when:

- Plant Tracker can call the existing sensor API
- sensors can be mapped to Plant Tracker locations via config
- dashboard shows latest readings for mapped locations
- photo modal shows readings around photo capture time
- sensor API failure does not break the dashboard
- no sensor history is duplicated into Plant Tracker
- no alerts, predictions, irrigation control, or diagnosis are added

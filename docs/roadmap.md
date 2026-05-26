# Plant Tracking System - Initial Design Doc

## 1. Goal

Build a small, practical plant-tracking system for the balcony setup that can later scale into a nursery/garden operating system.

The first version should prove the core workflow:

capture evidence -> attach it to plant/batch/location/time -> combine with sensor/weather/watering data -> review outcomes -> improve decisions.

The system should avoid premature ML. The priority is reliable data collection, good identifiers, and useful review screens.

## 2. Non-goals for the first version

The first version will not try to:

- diagnose plant health issues automatically
- control irrigation automatically
- track every individual leaf or plant perfectly
- run heavy ML on the Raspberry Pi
- build a polished commercial product UI

Those can come later if the basic system proves useful.

## 3. High-level architecture

```text
Raspberry Pi Zero 2W + Camera
 |
 | scheduled photos + metadata
 v
Uploader / local queue
 |
 | HTTP upload when laptop/backend reachable
 v
Laptop backend + Postgres
 |
 +--> photo storage
 +--> plant/batch/location records
 +--> sensor readings
 +--> watering/move/note events
 +--> dashboard
```

Additional data sources:

- SwitchBot temp/humidity sensors -> backend ingestion
- Xiaomi Flower Care sensor -> light/moisture reference readings
- Manual camera photos -> high-quality inspection records
- Weather forecast -> contextual data / future rules
- Manual notes -> watering, moves, pruning, plant stress, harvest

## 4. Hardware components

### 4.1 Raspberry Pi camera node

Ordered hardware:

- Raspberry Pi Zero 2W / 2WH
- Official Raspberry Pi Camera Module 3 Standard
- Standard-to-Mini camera cable for Pi Zero
- Pi Zero case
- Camera Module 3 housing

Purpose:

- take scheduled overview photos
- store locally if backend is unavailable
- upload photos and metadata to laptop/backend

The Pi is not the main brain. It is a camera node.

### 4.2 Existing sensors

Existing useful inputs:

- SwitchBot temperature/humidity sensors
- Xiaomi Flower Care sensor for light/moisture reference
- manual watering notes
- manual proper-camera photos

Do not add wired soil probes yet unless there is a clear test case. Balcony pots plus lots of wires will become messy quickly.

## 5. Software components

### 5.1 Pi camera node

The Pi is a permanently powered camera node.

Camera service:

- take scheduled photos
- store photos on disk with timestamp metadata
- start with every 30 minutes during daylight

Upload service:

- upload photos and metadata to the backend
- retry failed uploads

Cleanup service:

- keep 7 days of local backup photos
- remove older local photos after successful upload

### 5.2 Backend API

Runs on laptop.

Responsibilities:

- accept photo uploads
- accept metadata-only events
- provide dashboard data

### 5.3 Database

Postgres on laptop.

### 5.4 Photo storage

- store files on laptop filesystem
- database stores path + metadata

### 5.5 Dashboard

First dashboard should be basic but useful.

Minimum screens:

1. Latest overview
   - latest Pi camera image
   - latest sensor values
   - warnings/missing data

2. Zone timeline
   - photos over time
   - temp/humidity/light/moisture graph
   - watering/move notes

3. Batch timeline
   - sowing/cutting date
   - current location
   - photos/manual photos
   - events and observations

4. To-do / prompts
   - take manual photo
   - check plant/batch
   - sensor offline
   - missing watering note

## 6. Future expansion

### 6.1 Manual photo workflow

Manual photos are useful for close inspection, pests, plant stress, weekly records, before/after moments, and experiments where image quality matters.

### 6.2 Sensor and weather context

Later versions can add richer sensor history, weather forecasts, and rules that connect plant outcomes to heat, humidity, light, moisture, and watering.

### 6.3 Alerts and prompts

Later versions can prompt for missing photos, missed watering notes, heat checks, sensor problems, or batches that need inspection.

### 6.4 Nursery-scale workflow

The same structure can later scale from balcony zones to benches, beds, batches, propagation trays, QR labels, and irrigation zones.

## 7. Roadmap

Stages:

1. Capture, upload, and store photos.
2. Build a basic frontend to view photos, generate timelapses, compare two times, and track manual notes.
3. Add simple image metrics:
   - green pixel area estimate
   - rough canopy coverage
   - brightness/exposure quality check
   - blur/dark image detection
   - colour trend, cautiously interpreted
4. Add decision support rules:
   - pot/zone dries faster after hot days
   - watering interval too long for forecast temperature
   - batch needs closer photo after stress event
   - compare growth between two locations or treatments
5. Add ML / computer vision experiments, only after enough data exists:
   - segmentation of plant vs background
   - growth-rate anomaly detection
   - wilt/stress classification
   - batch comparison models

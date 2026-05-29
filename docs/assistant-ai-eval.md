# Plant Tracker AI Data Processing Review

_Date: 2026-05-29_

## Executive Summary

The Plant Tracker system is already in the right shape for useful assistant-driven data processing. The current roadmap correctly prioritizes reliable capture, identifiers, storage, review screens, manual notes, sensor/weather context, and simple image metrics before any serious ML work.

Now that the assistant can access the API, the most useful near-term role is not automated plant diagnosis. It is:

> Turn the data already collected into review queues, metadata audits, plant timelines, and next-action prompts.

The existing API already exposes enough structure for this:

- photos and timestamps;
- source metadata, including manual and SD imports;
- original filenames and file sizes for imported camera photos;
- rotations;
- growing units;
- labels;
- locations;
- photo-to-growing-unit associations;
- unclassified photos;
- per-photo context.

The main gap remains visual inspection. The assistant can see image metadata and URLs, but it cannot reliably inspect custom-action binary image responses as vision input. To unlock visual AI tagging, add an assistant-friendly image context endpoint with a short-lived signed image URL, rotation, existing metadata, known growing units, and existing labels.

The recommended strategy is:

> API-grounded assistant review now; assistant-friendly image access next; deterministic image metrics before custom ML; custom ML only after reviewed data exists.

---

## Inputs Reviewed

This review is based on:

1. The feedback/evaluation Markdown describing the current Plant Tracker API and AI tagging evaluation.
2. The roadmap/design document for the Plant Tracking System.
3. Live API access to the current assistant endpoints.

The roadmap's guiding principle is sound: the first version should prove the workflow of capturing evidence, attaching it to plant/batch/location/time, combining it with sensor/weather/watering data, reviewing outcomes, and improving decisions. It explicitly says to avoid premature ML and prioritize reliable data collection, good identifiers, and useful review screens.

---

## Current Dataset Snapshot

Observed from the live API:

| Item | Count |
|---|---:|
| Photos | 70 |
| Unclassified photos | 56 |
| Growing units | 8 |
| Locations | 1 |
| Events | 0 |

Current location:

- Balcony

Current growing units:

| ID | Name | Unit type |
|---:|---|---|
| 1 | Rosemary | individual |
| 2 | Chillis | tray |
| 3 | Thai basil vendita | mother_plant |
| 4 | Dill | clump |
| 5 | French tarragon | mother_plant |
| 6 | Garlic chives | mother_plant |
| 7 | Rau ram | mother_plant |
| 8 | Sorrel | mother_plant |

Recent API examples:

| Photo ID | Captured at | Source | Original file | Current metadata |
|---:|---|---|---|---|
| 100 | 2026-05-29T07:13:44Z | sd | DSC01389.ARW | no plant, label, location, or type |
| 101 | 2026-05-29T07:13:36Z | sd | DSC01388.ARW | no plant, label, location, or type |
| 102 | 2026-05-29T07:13:28Z | sd | DSC01387.ARW | no plant, label, location, or type |
| 103 | 2026-05-29T07:13:20Z | sd | DSC01386.ARW | rotated 270°, otherwise unclassified |
| 104 | 2026-05-29T07:12:56Z | sd | DSC01385.ARW | Rau ram, label `sulking` |

---

## Alignment With The Roadmap

The roadmap's staged direction is strong:

1. Capture, upload, and store photos.
2. Build a basic frontend to view photos, generate timelapses, compare two times, and track manual notes.
3. Add simple image metrics.
4. Add decision-support rules.
5. Add ML/CV experiments only after enough data exists.

The assistant can help at every stage, but its best role changes by stage.

| Roadmap stage | Best assistant contribution |
|---|---|
| Capture/upload/store photos | Audit missing metadata, identify ingestion issues, summarize photo backlog |
| Basic frontend/review | Generate review queues, plant timelines, before/after candidates, user prompts |
| Simple image metrics | Interpret metrics, flag anomalies, explain trends, prioritize review |
| Decision-support rules | Draft rules, inspect evidence chains, explain why a prompt fired |
| Later ML/CV experiments | Help define labels, evaluate model outputs, compare AI suggestions against reviewed truth |

The assistant should not be framed as the core automation layer yet. It should be framed as a review and decision-support layer over the evidence the system already captures.

---

## What The Assistant Can Do Immediately

### 1. Dataset inventory

The assistant can already answer:

- How many photos exist?
- How many are unclassified?
- Which growing units exist?
- Which photos are associated with each growing unit?
- Which photos have labels?
- Which photos have no plant association?
- Which photos are recent SD imports?
- Which photos have rotation metadata?
- Which photos have original filenames and imported file sizes?

This is useful because the current dataset already has enough structure to support backlog review.

### 2. Metadata QA

The assistant can find likely data-quality issues, such as:

- photos with no growing unit;
- photos with no location;
- photos with no photo type;
- photos with labels but no plant association;
- photos with plant associations but no photo type;
- photos with issue labels needing follow-up;
- photos with rotation values that may need display correction;
- SD-imported photos that are mostly unclassified;
- timestamp bursts that may be near-duplicates or sequence captures.

Concrete examples in the current data:

- Photo `104` is attached to Rau ram and labelled `sulking`.
- Photo `65` is attached to Garlic chives and labelled `root_bound`.
- Photos `95` and `94` have `delivery_stress` labels but no growing unit.
- Recent SD photos `109` to `100` are mostly unclassified.
- Photo `103` is rotated 270° and otherwise unclassified.

### 3. Review queue generation

The current dataset has 56 unclassified photos. The assistant can turn that into review queues.

Suggested queues:

| Queue | Purpose |
|---|---|
| `recent_sd_imports` | Newly imported camera photos needing classification |
| `has_label_no_plant` | Issue/stress labels that need plant association |
| `has_plant_no_type` | Plant-associated photos missing photo type |
| `rotated_needs_check` | Photos with non-zero rotation |
| `incident_or_stress` | Important history items needing notes or follow-up |
| `candidate_baselines` | Early plant-associated photos useful for future comparison |
| `low_context_old_backlog` | Older photos with no plant, label, location, or type |

Example first-pass queue:

```json
{
  "recent_sd_imports": [109, 108, 107, 106, 105, 103, 102, 101, 100],
  "labelled_but_no_plant": [95, 94],
  "plant_attached_missing_type": [7, 14, 65, 64, 85, 84, 83, 82, 81, 80, 86, 87, 90, 89, 96, 104]
}
```

### 4. Plant timelines

The assistant can build plant timelines from the current API.

Useful summaries include:

- first associated photo;
- latest associated photo;
- number of photos;
- labels seen;
- incident/stress photos;
- whether there are comparison candidates;
- whether the plant needs a fresh overview photo.

This aligns directly with the roadmap's “batch timeline” and “zone timeline” screens.

### 5. Prompt generation

The roadmap calls for a To-do / prompts screen. The assistant can help generate prompt candidates from metadata before sensor integration is complete.

Possible prompts:

| Prompt | Trigger |
|---|---|
| “Classify recent SD imports” | Recent photos with no plant/type/label |
| “Attach delivery-stress photos to a plant” | Label exists but no growing unit |
| “Take follow-up photo of Rau ram” | Recent `sulking` label |
| “Choose baseline photo for each plant” | Growing unit has photos but no baseline |
| “Add photo type to plant-associated photos” | Growing unit exists but photo_type is null |
| “Check rotated images” | rotation is 90/270 |

---

## What The Assistant Still Cannot Reliably Do

The assistant cannot yet reliably inspect actual image pixels through the custom-action API.

It can retrieve metadata and URLs, but binary image endpoints are not enough for robust assistant-side vision in this context.

Until image access is improved, the assistant should not be expected to reliably:

- identify plants visually;
- validate visible wilting;
- detect pests;
- judge yellowing/browning;
- estimate canopy from pixels;
- compare visual change between two photos;
- detect blur/exposure from the actual image;
- choose the best visual baseline image.

It can prepare the workflow, queue the work, and design the output schemas. Visual suggestions require an assistant-friendly image access mechanism.

---

## Recommended Assistant-Friendly Image Endpoint

Add:

```http
GET /assistant/photos/{photo_id}/vision-context
```

Recommended response:

```json
{
  "photo_id": 104,
  "image_url": "https://example.com/signed/photo-104.jpg",
  "thumbnail_url": "https://example.com/signed/photo-104-thumb.jpg",
  "rotation": 0,
  "captured_at": "2026-05-29T07:12:56Z",
  "source": "sd",
  "original_filename": "DSC01385.ARW",
  "photo_type": null,
  "location": null,
  "existing_growing_units": [
    {
      "id": 7,
      "name": "Rau ram",
      "unit_type": "mother_plant"
    }
  ],
  "existing_labels": [
    "sulking"
  ],
  "known_growing_units": [
    {"id": 1, "name": "Rosemary", "unit_type": "individual"},
    {"id": 2, "name": "Chillis", "unit_type": "tray"},
    {"id": 3, "name": "Thai basil vendita", "unit_type": "mother_plant"},
    {"id": 4, "name": "Dill", "unit_type": "clump"},
    {"id": 5, "name": "French tarragon", "unit_type": "mother_plant"},
    {"id": 6, "name": "Garlic chives", "unit_type": "mother_plant"},
    {"id": 7, "name": "Rau ram", "unit_type": "mother_plant"},
    {"id": 8, "name": "Sorrel", "unit_type": "mother_plant"}
  ]
}
```

Recommended implementation details:

- Use short-lived signed URLs rather than public permanent URLs.
- Include rotation so the assistant or frontend can interpret the image correctly.
- Include known growing units to constrain visual classification.
- Include existing labels so the assistant can validate or challenge them.
- Include photo source and original filename for traceability.
- Include previous/next photo IDs in the same capture sequence when possible.

---

## Recommended Review Queue Endpoint

Add:

```http
GET /assistant/review-queue
```

Example response:

```json
{
  "summary": {
    "total_photos": 70,
    "unclassified_photos": 56,
    "high_priority": 3,
    "medium_priority": 20,
    "low_priority": 33
  },
  "queues": [
    {
      "name": "labelled_but_no_plant",
      "photo_ids": [95, 94],
      "priority": "high",
      "reason": "Photos have stress labels but no plant association."
    },
    {
      "name": "recent_sd_imports",
      "photo_ids": [109, 108, 107, 106, 105, 103, 102, 101, 100],
      "priority": "medium",
      "reason": "Recent SD imports with no classification."
    },
    {
      "name": "plant_attached_missing_type",
      "photo_ids": [7, 14, 65, 64, 85, 84, 83, 82, 81, 80, 86, 87, 90, 89, 96, 104],
      "priority": "medium",
      "reason": "Useful plant history exists, but photo type is missing."
    }
  ]
}
```

This endpoint would be helpful even before visual AI.

---

## Recommended AI Suggestion Data Model

Store assistant output separately from confirmed user data.

### `photo_ai_analyses`

Suggested fields:

- `id`
- `photo_id`
- `model_name`
- `model_version`
- `prompt_version`
- `status`
- `created_at`
- `raw_response_json`
- `requires_human_review`
- `image_access_method`

### `photo_ai_suggested_growing_units`

Suggested fields:

- `id`
- `photo_id`
- `analysis_id`
- `growing_unit_id`
- `confidence`
- `reason`
- `accepted_at`
- `rejected_at`
- `reviewed_by`

### `photo_ai_suggested_labels`

Suggested fields:

- `id`
- `photo_id`
- `analysis_id`
- `label`
- `confidence`
- `reason`
- `accepted_at`
- `rejected_at`
- `reviewed_by`

### `photo_ai_suggested_photo_types`

Suggested fields:

- `id`
- `photo_id`
- `analysis_id`
- `photo_type`
- `confidence`
- `reason`
- `accepted_at`
- `rejected_at`
- `reviewed_by`

### `photo_quality_metrics`

Suggested fields:

- `id`
- `photo_id`
- `analysis_id`
- `blur_score`
- `brightness_score`
- `contrast_score`
- `exposure_flag`
- `duplicate_candidate_photo_id`
- `rotation_suggested`
- `quality_flags_json`

### `photo_canopy_measurements`

Suggested fields:

- `id`
- `photo_id`
- `analysis_id`
- `measurement_type`
- `bbox_x`
- `bbox_y`
- `bbox_width`
- `bbox_height`
- `area_px`
- `green_area_px`
- `width_px`
- `height_px`
- `scale_reference_type`
- `scale_confidence`
- `notes`

---

## Suggested AI Output Shape

Once image access is available, the assistant should emit structured suggestions like this:

```json
{
  "photo_id": 104,
  "analysis_status": "suggested",
  "suggested_growing_units": [
    {
      "growing_unit_id": 7,
      "name": "Rau ram",
      "confidence": 0.78,
      "reason": "Appears visually consistent with known Rau ram photos."
    }
  ],
  "suggested_photo_type": {
    "value": "health_check",
    "confidence": 0.70,
    "reason": "The existing label indicates this photo may document plant condition."
  },
  "suggested_labels": [
    {
      "label": "wilting",
      "confidence": 0.72,
      "reason": "Leaves appear drooped compared with expected healthy posture."
    },
    {
      "label": "needs_review",
      "confidence": 1.0,
      "reason": "Health-related observations should be confirmed by the user."
    }
  ],
  "canopy_estimate": {
    "available": true,
    "measurement_type": "relative_pixels_only",
    "bbox_px": [120, 90, 860, 720],
    "width_px": 740,
    "height_px": 630,
    "area_px": 310000,
    "confidence": 0.60,
    "note": "No scale marker visible, so real-world size cannot be inferred."
  },
  "quality_flags": [
    "single_plant_visible",
    "rotation_ok",
    "background_clutter_medium"
  ],
  "requires_human_review": true
}
```

Important policy:

- AI suggestions are never confirmed facts.
- Health/disease/stress suggestions always require review.
- Low-confidence plant identity suggestions require review.
- New or unseen plant identity suggestions require review.

---

## Label Taxonomy Recommendations

The current labels already include useful real-world states such as:

- `root_bound`
- `delivery_stress`
- `sulking`

Recommended starter taxonomy:

| Category | Labels |
|---|---|
| General | `healthy`, `needs_review`, `unknown` |
| Water/stress | `wilting`, `sulking`, `drought_stress`, `overwatered_possible` |
| Leaf condition | `yellowing`, `browning`, `leaf_spots`, `pest_damage` |
| Handling | `delivery_stress`, `transplant_shock`, `root_bound` |
| Growth form | `leggy`, `overgrown`, `new_growth`, `flowering` |
| Image quality | `blurry`, `underexposed`, `overexposed`, `cropped`, `poor_angle` |
| Workflow | `baseline_candidate`, `followup_needed`, `not_useful` |

Do not allow the label namespace to become too free-form too early. Prefer a controlled set plus notes.

---

## Photo Type Recommendations

Recommended `photo_type` values:

| Type | Use |
|---|---|
| `overview` | General plant or tray state |
| `closeup` | Detail photo of leaves, roots, pests, flowers, etc. |
| `health_check` | Condition-focused image |
| `incident` | Damage, stress, accident, pest finding, etc. |
| `new_purchase` | Initial acquisition record |
| `after_watering` | Post-watering record |
| `after_pruning` | Post-pruning record |
| `after_repotting` | Post-repotting record |
| `propagation` | Cutting, seedling, propagation state |
| `harvest` | Harvest moment |
| `comparison` | Deliberate before/after or A/B comparison |
| `pi_overview` | Scheduled Pi camera overview |

Adding `pi_overview` is useful because the roadmap separates the Pi camera node from manual proper-camera photos.

---

## Pi Camera Integration

The roadmap identifies the Pi as a camera node, not the main brain. That is the right architecture.

When the Pi camera is active, store extra capture metadata:

- `camera_id`
- `capture_profile`
- `viewpoint`
- `scheduled_capture`
- `capture_interval`
- `light_window`
- `local_queue_id`
- `upload_attempt_count`
- `uploaded_at`
- `scale_marker_visible`
- `camera_mount_position`
- `zone_id` or `location_id`

The first Pi goal should not be ML. It should be consistent evidence capture.

Recommended early Pi operating mode:

- daylight captures every 30 minutes, as the roadmap says;
- local retry queue;
- 7-day local backup after successful upload;
- fixed camera position;
- stable mount;
- known background if possible;
- optional printed scale marker or ruler;
- one plant/tray/zone per capture where possible.

---

## Simple Image Metrics Before ML

This strongly aligns with the roadmap.

Recommended deterministic metrics:

| Metric | Tooling | Use |
|---|---|---|
| Blur score | OpenCV / Laplacian variance | Reject low-quality images |
| Brightness | Histogram / mean luminance | Detect dark/overexposed captures |
| Exposure flags | Histogram clipping | Prompt for better image |
| Green pixel area | HSV thresholding | Rough canopy trend |
| Canopy bounding box | Threshold + morphology | Relative growth tracking |
| Frame alignment | feature matching / crop registration | Detect camera movement |
| Duplicate detection | perceptual hash | Reduce review load |
| Scale marker detection | ArUco/ruler | Convert pixels to approximate physical units |

Cautions:

- Green-pixel area is not true biomass.
- Colour trend is lighting-sensitive.
- Brown/red/purple leaves can break simple green thresholds.
- Balcony lighting will vary strongly.
- Handheld photos are poor for precise canopy comparison.
- Fixed Pi photos are much better for trends.

---

## Decision-Support Rules

The roadmap includes rules such as:

- pot/zone dries faster after hot days;
- watering interval too long for forecast temperature;
- batch needs closer photo after stress event;
- compare growth between two locations or treatments.

The assistant can help draft and explain these rules, but the backend should own rule execution.

Suggested early rules:

| Rule | Trigger | Prompt |
|---|---|---|
| Stress follow-up | photo labelled `sulking`, `wilting`, or `delivery_stress` | “Take a follow-up photo within 24h.” |
| Missing classification | recent SD import has no plant/type | “Classify recent camera import.” |
| Plant missing baseline | growing unit has photos but no baseline | “Choose a baseline image for this plant.” |
| Sensor offline | no recent sensor reading | “Check sensor.” |
| Hot day watering review | high temperature forecast + no watering note | “Review watering for heat-sensitive pots.” |
| Pi capture quality | repeated dark/blurred photos | “Adjust camera position or schedule.” |

---

## Updated Roadmap With Assistant Role

### Phase 1: Capture, upload, and store photos

Already partly working.

Assistant role:

- audit ingestion;
- summarize recent imports;
- detect missing metadata;
- flag broken or inconsistent records.

### Phase 2: Basic frontend and review screens

Assistant role:

- generate review queues;
- summarize plant timelines;
- propose prompts;
- identify baseline candidates;
- help compare two selected times once images are accessible.

Recommended screens:

1. Latest overview.
2. Unclassified review queue.
3. Plant timeline.
4. Zone timeline.
5. Photo detail with metadata and suggestions.
6. To-do/prompts.

### Phase 3: Simple image metrics

Assistant role:

- explain metric changes;
- flag suspicious trends;
- summarize daily/weekly changes;
- combine metrics with notes and sensor context.

Example summary:

> Chillis tray canopy area increased compared with the previous comparable Pi overview. No stress labels were added. Sensor history shows hotter conditions, so continue monitoring watering interval.

### Phase 4: Decision-support rules

Assistant role:

- explain why prompts fired;
- suggest missing evidence;
- summarize outcomes after user action;
- help tune thresholds.

### Phase 5: ML/CV experiments later

Assistant role:

- help define training labels;
- compare predictions with accepted/rejected suggestions;
- identify classes with enough examples;
- evaluate whether custom ML is justified.

Good first ML candidates later:

- same-plant / known-plant classifier;
- plant-vs-background segmentation;
- pot/tray detection;
- image quality classifier.

Avoid early ML for:

- disease diagnosis;
- nutrient deficiency diagnosis;
- exact species identification;
- precise health scoring.

---

## Practical Next Actions

### Backend/API

1. Add `GET /assistant/review-queue`.
2. Add `GET /assistant/photos/{photo_id}/vision-context`.
3. Add AI suggestion storage tables.
4. Add accept/reject endpoints for suggestions.
5. Add `baseline_photo_id` or baseline relationship for each growing unit.
6. Add `pi_overview` as a photo type.
7. Add capture metadata fields for Pi photos.

### Frontend

1. Build an unclassified-photo review screen.
2. Show grouped queues rather than one long backlog.
3. Add quick actions:
   - assign plant;
   - assign photo type;
   - assign label;
   - mark reviewed;
   - mark not useful;
   - choose baseline.
4. Add plant timeline screen.
5. Add photo detail screen with existing metadata and AI suggestions.

### Data workflow

1. Classify recent SD imports first.
2. Resolve labelled-but-no-plant photos.
3. Add photo types to plant-associated photos.
4. Choose baseline images per growing unit.
5. Use labels consistently.
6. Keep notes for meaningful events, not every tiny observation.

### Image processing

1. Start with blur and brightness detection.
2. Add duplicate/near-duplicate detection.
3. Add green-pixel canopy estimate for fixed Pi views.
4. Add canopy bounding boxes.
5. Add scale marker only after the camera mount is stable.

### Assistant/AI

1. Use metadata-only assistant review immediately.
2. Add visual suggestions after signed image URLs exist.
3. Store all AI output as suggestions.
4. Require human confirmation.
5. Use accepted/rejected suggestions as future training data.

---

## Final Assessment

The system has crossed the threshold where the assistant can be genuinely useful.

It is not yet a visual plant diagnostician, and it should not try to become one in the first version. But it can already help turn a growing photo archive into structured review work.

The best immediate assistant value is:

- inventory;
- triage;
- metadata QA;
- review queues;
- plant timelines;
- prompt generation;
- schema and workflow design.

The best next unlock is assistant-friendly image access.

The best long-term path is:

> capture reliable evidence -> review and enrich metadata -> add simple metrics -> add decision-support rules -> collect reviewed labels -> only then consider custom ML.

This matches the roadmap and avoids premature ML while still making the data useful right away.

# Plant Tracker AI Data Processing Evaluation — Live Trial With Vision Context

_Date: 2026-05-29_

## Purpose

This document updates the earlier evaluation by doing concrete processing work against the live Plant Tracker API, including the new `vision-context` photo endpoint.

The goal is no longer only to describe what the assistant could do. The goal is to show what it can actually output from the current data and where the remaining limits are.

## Inputs Used

- Live assistant API.
- Current photo list.
- Current growing unit list.
- Current unclassified-photo summary.
- Sampled `vision-context` records.
- Existing roadmap direction: capture and review first, simple metrics before ML, avoid premature automation.

## Executive Summary

The assistant can already provide meaningfully useful data-processing outputs from the current Plant Tracker dataset.

Useful outputs available now:

- dataset completeness audit;
- missing-field audit;
- source/import audit;
- rotation/orientation audit;
- label and incident audit;
- plant-specific timelines;
- candidate baseline photos;
- review queues;
- sequence-aware review batches using nearby-photo context;
- concrete next actions for the dashboard and review workflow.

The new `vision-context` endpoint is a major improvement. It now gives the assistant one JSON object containing:

- photo ID;
- image URL;
- rotation;
- capture time;
- source;
- original filename;
- photo type;
- location;
- growing-unit associations;
- labels;
- known growing units;
- neighbouring photos.

That is the right shape for AI-assisted review.

However, in this chat/tool environment, the returned `image_url` is not yet directly renderable as pixels by the assistant. The endpoint makes image-aware workflows architecturally possible, but the current assistant run still cannot honestly claim visual observations such as “this leaf is yellow” or “this plant is wilted” unless the image bytes are made available to a vision-capable tool or the model runtime can fetch the URL as an image.

So the current state is:

> Excellent for metadata and sequence-aware review today; ready for visual tagging once the image URL is actually consumable by the vision model.

---

# 1. Live Dataset Snapshot

Observed through the live API:

| Metric | Count |
|---|---:|
| Total photos | 70 |
| Unclassified photos | 56 |
| Growing units | 8 |
| Locations | 1 |
| Events | 0 |

Current location:

| ID | Name |
|---:|---|
| 1 | Balcony |

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

---

# 2. Concrete Dataset Audit

## 2.1 Photo Source Audit

| Source | Count | Notes |
|---|---:|---|
| `manual` | 59 | Most older photos and all existing closeup/new purchase/incident photo types |
| `sd` | 11 | Recent camera-imported photos, mostly unclassified |

Interpretation:

- The SD import workflow is working.
- SD photos are arriving with useful metadata: source, original filename, original size, capture timestamp, rotation.
- SD imports are now the highest-value review queue because most are recent and not classified.

## 2.2 Capture Date Audit

| Date | Count | Notes |
|---|---:|---|
| 2026-05-26 | 14 | Initial manual sequence |
| 2026-05-27 | 39 | Main manual capture/review day |
| 2026-05-28 | 7 | Follow-up photos plus stress labels and one SD photo |
| 2026-05-29 | 10 | Recent SD-imported sequence |

Interpretation:

- The dataset already has enough temporal structure to support timelines.
- It is not yet a long time series, but it is enough for review-screen prototyping.
- The current capture distribution is burst-based rather than scheduled. This matches the roadmap stage before the Pi camera node takes over regular capture.

## 2.3 Missing Metadata Audit

| Field / condition | Count | Example IDs | Interpretation |
|---|---:|---|---|
| Missing `photo_type` | 56 | 1, 2, 3, 4, 5, 6, 7, 14, 65, 104 | Main reason many photos remain “unclassified” |
| Has `photo_type` | 14 | 46, 45, 40, 39, 32, 31, 63, 62, 61, 60, 59, 57, 66, 88 | Existing photo-type taxonomy is already useful |
| Missing location | 68 | Most records | Location assignment should be easy to improve |
| Has location | 2 | 7, 14 | Only Chillis and Rosemary early records are attached to Balcony |
| Missing growing unit | 52 | Many unclassified photos | Main review workload |
| Has growing unit | 18 | 7, 14, 66, 65, 64, 85, 84, 83, 82, 81, 80, 86, 88, 87, 90, 89, 96, 104 | Enough data for plant timelines |
| Has labels | 4 | 65, 95, 94, 104 | Issue/stress labels are sparse but useful |
| Missing original filename | 14 | 1–14 | Early manual timestamp-named photos |
| Missing original file size | 59 | Manual photos | SD imports have richer file metadata |

Interpretation:

- The most valuable immediate UI feature is a review screen for missing `photo_type`, `growing_unit`, and `location`.
- Location can probably be bulk-applied for most existing photos as `Balcony`, unless there are exceptions.
- `photo_type` is the cleanest “classification complete” marker right now.

## 2.4 Rotation Audit

| Rotation | Count | Example IDs |
|---:|---:|---|
| `0` | 50 | 1, 3, 4, 5, 6, 7, 14, 104 |
| `90` | 9 | 31, 62, 60, 59, 69, 57, 83, 86, 89 |
| `270` | 11 | 2, 73, 63, 64, 85, 82, 81, 80, 90, 110, 103 |

Interpretation:

- Rotation metadata is already useful.
- Any visual review UI should apply rotation before display.
- Rotation is also useful as a quality/review flag because many plant-associated photos are rotated.

Suggested review flag:

```json
{
  "flag": "rotation_nonzero",
  "meaning": "Display should apply rotation before review; photo may need orientation confirmation."
}
```

---

# 3. Existing Taxonomy Audit

## 3.1 Photo Types Currently Present

| Photo type | Count | Example IDs |
|---|---:|---|
| `closeup` | 6 | 46, 45, 40, 39, 32, 31 |
| `new_purchase` | 6 | 63, 62, 61, 60, 59, 57 |
| `incident` | 2 | 66, 88 |
| `null` | 56 | Many |

Interpretation:

- Existing photo types are sensible.
- The major gap is not taxonomy design; it is review throughput.
- `overview` or `baseline` would be useful additions for future Pi camera and comparison workflows.

Recommended additions:

- `overview`
- `baseline`
- `health_check`
- `after_watering`
- `after_pruning`
- `after_repotting`
- `comparison`
- `not_useful`

## 3.2 Labels Currently Present

| Label | Photo IDs | Notes |
|---|---|---|
| `root_bound` | 65 | Attached to Garlic chives |
| `delivery_stress` | 95, 94 | Labelled but not attached to a growing unit |
| `sulking` | 104 | Attached to Rau ram |

Interpretation:

- Labels are highly valuable when present.
- The most important label-related audit finding is that photos 95 and 94 have `delivery_stress` but no growing unit.
- Labelled photos should be treated as high-priority review items because they often encode plant-health context.

---

# 4. Plant Timelines Generated From Current Data

These are concrete timeline summaries the assistant can generate now.

## 4.1 Chillis

| Photo ID | Captured | Source | Type | Location | Labels | Rotation |
|---:|---|---|---|---|---|---:|
| 7 | 2026-05-26 17:32:49Z | manual | null | Balcony | none | 0 |
| 96 | 2026-05-28 06:40:56Z | manual | null | null | none | 0 |

Useful output:

- Chillis has at least two records across two days.
- Photo 7 is a good candidate for an early baseline because it has a growing unit and location.
- Photo 96 is a later comparison candidate but needs location and photo type.

Suggested actions:

- Set photo 7 as candidate `baseline`.
- Add location to photo 96.
- Set photo 96 photo type to `overview` or `health_check` after visual review.

## 4.2 Rosemary

| Photo ID | Captured | Source | Type | Location | Labels | Rotation |
|---:|---|---|---|---|---|---:|
| 14 | 2026-05-26 17:33:33Z | manual | null | Balcony | none | 0 |
| 88 | 2026-05-27 18:43:57Z | manual | incident | null | none | 0 |
| 87 | 2026-05-27 18:44:03Z | manual | null | null | none | 0 |

Useful output:

- Rosemary has an incident record and an adjacent follow-up photo.
- Photos 88 and 87 were captured six seconds apart, making them a likely mini-sequence.
- Photo 14 is a candidate early baseline.

Suggested actions:

- Attach location `Balcony` to photos 88 and 87 if correct.
- Add a note or label explaining the incident in photo 88.
- Consider linking 88 and 87 as the same review session.

## 4.3 Dill

| Photo ID | Captured | Source | Type | Location | Labels | Rotation |
|---:|---|---|---|---|---|---:|
| 66 | 2026-05-27 13:20:24Z | manual | incident | null | none | 0 |

Useful output:

- Dill has one known record and it is an incident.
- This should be high priority because the plant’s only associated photo is a problem/incident photo.

Suggested actions:

- Add an issue label to photo 66 if known.
- Capture or assign a healthy/baseline photo for Dill.
- Add location if correct.

## 4.4 Garlic Chives

| Photo ID | Captured | Source | Type | Location | Labels | Rotation |
|---:|---|---|---|---|---|---:|
| 65 | 2026-05-27 13:28:40Z | manual | null | null | root_bound | 0 |
| 80 | 2026-05-27 17:11:14Z | manual | null | null | none | 270 |

Useful output:

- Garlic chives has a labelled root-bound record and a later same-day record.
- This is a good case for before/after or issue-follow-up review.

Suggested actions:

- Set photo 65 type to `incident` or `health_check`.
- Add location to both.
- Rotate photo 80 for review.
- If photo 80 was after handling/repotting, label it as `after_repotting` or `follow_up`.

## 4.5 Thai Basil Vendita

| Photo ID | Captured | Source | Type | Location | Labels | Rotation |
|---:|---|---|---|---|---|---:|
| 64 | 2026-05-27 14:57:16Z | manual | null | null | none | 270 |
| 82 | 2026-05-27 17:11:10Z | manual | null | null | none | 270 |

Useful output:

- Two same-day records exist.
- Both are rotated 270 degrees.
- Needs photo type and location.

Suggested actions:

- Apply location if correct.
- Rotate for review.
- Choose one as baseline if visually suitable.

## 4.6 French Tarragon

| Photo ID | Captured | Source | Type | Location | Labels | Rotation |
|---:|---|---|---|---|---|---:|
| 85 | 2026-05-27 16:57:35Z | manual | null | null | none | 270 |
| 81 | 2026-05-27 17:11:12Z | manual | null | null | none | 270 |

Useful output:

- Two same-day records exist.
- Both need orientation-aware review.
- Likely candidates for selecting one baseline.

Suggested actions:

- Rotate for review.
- Add location.
- Assign `baseline` or `overview` if one photo shows the plant well.

## 4.7 Rau Ram

| Photo ID | Captured | Source | Type | Location | Labels | Rotation |
|---:|---|---|---|---|---|---:|
| 84 | 2026-05-27 17:10:55Z | manual | null | null | none | 270 |
| 86 | 2026-05-27 18:36:14Z | manual | null | null | none | 90 |
| 104 | 2026-05-29 07:12:56Z | sd | null | null | sulking | 0 |

Useful output:

- Rau ram has a useful three-point timeline.
- The latest record is labelled `sulking`.
- The latest record is from SD import and has a nearby photo sequence.

Suggested actions:

- High-priority review because there is a stress label.
- Compare photo 104 against 84 and 86 once visual access works.
- Set photo 104 type to `health_check` or `incident` depending on visual review.
- Add location if correct.

## 4.8 Sorrel

| Photo ID | Captured | Source | Type | Location | Labels | Rotation |
|---:|---|---|---|---|---|---:|
| 83 | 2026-05-27 17:10:59Z | manual | null | null | none | 90 |
| 90 | 2026-05-27 19:21:23Z | manual | null | null | none | 270 |
| 89 | 2026-05-27 19:21:29Z | manual | null | null | none | 90 |

Useful output:

- Sorrel has three same-day photos.
- Photos 90 and 89 were captured six seconds apart and should be treated as a likely mini-sequence.
- All Sorrel records need rotation-aware review.

Suggested actions:

- Pick a baseline.
- Add location.
- Mark duplicate/near-duplicate if 90 and 89 are visually redundant.

---

# 5. Review Queues Actually Generated

## 5.1 Highest Priority Queue

These records are high priority because they involve incidents or stress labels.

| Photo ID | Reason | Current metadata |
|---:|---|---|
| 66 | Incident photo | Dill, `incident`, no label |
| 88 | Incident photo | Rosemary, `incident`, no label |
| 65 | Issue label | Garlic chives, `root_bound`, no photo type |
| 95 | Stress label with no plant | `delivery_stress`, no growing unit |
| 94 | Stress label with no plant | `delivery_stress`, no growing unit |
| 104 | Stress label | Rau ram, `sulking`, no photo type |

Recommended UI:

- A “Needs attention” panel should show these first.
- Each row should ask for: confirm plant, confirm issue label, set photo type, add note.

## 5.2 Labelled But No Plant

| Photo ID | Label | Captured | Nearby context |
|---:|---|---|---|
| 95 | delivery_stress | 2026-05-28 10:55:58Z | previous 96, next 94 |
| 94 | delivery_stress | 2026-05-28 10:56:02Z | previous 95, next 110 |

Why this is useful:

- The user already knew these photos were about delivery stress.
- The missing plant association is the key blocker.
- These are ideal examples for an assistant-assisted review screen.

Suggested prompt:

> These two photos are labelled `delivery_stress` but are not attached to a plant. Please pick the plant from the known growing units or mark as unknown.

## 5.3 Recent SD Import Queue

Recent SD photos needing classification:

| Photo ID | Captured | Original file | Rotation | Known context |
|---:|---|---|---:|---|
| 109 | 2026-05-29 07:11:36Z | DSC01380.ARW | 0 | unclassified |
| 108 | 2026-05-29 07:11:40Z | DSC01381.ARW | 0 | unclassified |
| 107 | 2026-05-29 07:11:48Z | DSC01382.ARW | 0 | unclassified |
| 106 | 2026-05-29 07:12:32Z | DSC01383.ARW | 0 | unclassified |
| 105 | 2026-05-29 07:12:54Z | DSC01384.ARW | 0 | previous to Rau ram `sulking` photo |
| 104 | 2026-05-29 07:12:56Z | DSC01385.ARW | 0 | Rau ram, `sulking` |
| 103 | 2026-05-29 07:13:20Z | DSC01386.ARW | 270 | unclassified |
| 102 | 2026-05-29 07:13:28Z | DSC01387.ARW | 0 | unclassified |
| 101 | 2026-05-29 07:13:36Z | DSC01388.ARW | 0 | unclassified |
| 100 | 2026-05-29 07:13:44Z | DSC01389.ARW | 0 | unclassified |

Why this is useful:

- These photos form a tight capture sequence.
- The new `vision-context` endpoint provides neighbouring photos, so the review UI can move through them as a sequence.
- Photo 104 acts as an anchor because it is already assigned to Rau ram and labelled `sulking`.
- Photos 105 and 103 are immediate neighbours around the anchor and should be reviewed next.

Recommended sequence review order:

1. 104 — known anchor: Rau ram, `sulking`.
2. 105 — previous photo, captured two seconds before 104.
3. 103 — next photo, captured 24 seconds after 104.
4. 106 — previous context before 105.
5. 102, 101, 100 — following end of sequence.
6. 109, 108, 107 — earlier part of sequence.

## 5.4 Plant-Associated But Missing Photo Type

| Photo IDs | Count | Meaning |
|---|---:|---|
| 7, 14, 65, 64, 85, 84, 83, 82, 81, 80, 86, 87, 90, 89, 96, 104 | 16 | Already attached to plants, but not classified by photo type |

Why this is useful:

- These are easier than fully unclassified photos because the plant is known.
- The review task is only: choose type, add location, maybe add labels.

Suggested bulk action:

- If visually suitable, set one early photo per plant to `baseline`.
- Otherwise set to `overview`, `health_check`, or `not_useful`.

## 5.5 Rotation Review Queue

Nonzero rotation photos:

| Rotation | Photo IDs |
|---:|---|
| 90 | 31, 62, 60, 59, 69, 57, 83, 86, 89 |
| 270 | 2, 73, 63, 64, 85, 82, 81, 80, 90, 110, 103 |

Why this is useful:

- The review UI must apply rotation correctly.
- A thumbnail/contact-sheet view without rotation will be frustrating.
- Several plant-associated baseline candidates are rotated.

---

# 6. Vision Context Endpoint Trial

## 6.1 Endpoint Tested

Example:

```http
GET /assistant/photos/104/vision-context
```

## 6.2 Example Output: Photo 104

Photo 104 returned:

```json
{
  "photo_id": 104,
  "image_url": "https://laptop.tail46f0b9.ts.net/assistant/photos/33a3e02dbbb941548295cb5aea47e6e3.jpg",
  "rotation": 0,
  "captured_at": "2026-05-29T07:12:56Z",
  "source": "sd",
  "original_filename": "DSC01385.ARW",
  "photo_type": null,
  "location": null,
  "growing_units": [
    {
      "id": 7,
      "name": "Rau ram",
      "unit_type": "mother_plant"
    }
  ],
  "labels": ["sulking"],
  "nearby_photos": [
    {
      "id": 105,
      "captured_at": "2026-05-29T07:12:54Z",
      "relation": "previous"
    },
    {
      "id": 103,
      "captured_at": "2026-05-29T07:13:20Z",
      "relation": "next"
    }
  ]
}
```

This is exactly the right shape for review.

## 6.3 Sampled Vision Context Records

| Photo ID | What it demonstrates | Useful context returned |
|---:|---|---|
| 104 | labelled plant-health case | Rau ram, label `sulking`, previous 105, next 103 |
| 105 | neighbour of labelled case | previous 106, next 104 |
| 103 | rotated neighbour after labelled case | rotation 270, previous 104, next 102 |
| 95 | labelled but no plant | `delivery_stress`, previous 96, next 94 |
| 94 | second delivery-stress photo | `delivery_stress`, previous 95, next 110 |
| 66 | incident photo | Dill, photo type `incident`, previous 67, next 65 |
| 88 | incident photo | Rosemary, photo type `incident`, previous 86, next 87 |
| 65 | labelled plant issue | Garlic chives, label `root_bound`, previous 66, next 64 |
| 100 | sequence end | SD import, previous 101 |

## 6.4 What Vision Context Unlocks

The new endpoint makes these workflows feasible:

1. **Single-photo review**
   - Show image.
   - Show plant options.
   - Show existing labels.
   - Ask for suggested photo type, labels, and location.

2. **Sequence review**
   - Use `nearby_photos` to move through bursts.
   - Start from an anchored known photo.
   - Classify neighbours faster.

3. **Plant-aware suggestions**
   - The assistant sees the known growing units.
   - It does not need universal plant identification first.
   - It can ask: “which of these eight plants is this most likely to be?”

4. **Stress/incident review**
   - Labels such as `sulking`, `root_bound`, and `delivery_stress` can trigger high-priority prompts.

5. **Baseline selection**
   - For each plant, choose one photo that is best for future comparison.

## 6.5 Remaining Blocker For Pixel-Level Visual Analysis

The endpoint now returns `image_url`, but in this assistant run the image itself was not rendered as pixels for inspection.

What I could verify:

- the endpoint exists;
- it returns the correct metadata;
- it returns image URLs;
- it returns known growing units;
- it returns neighbouring photos;
- it returns labels and existing associations.

What I could not honestly verify:

- whether photo 104 visibly looks wilted or “sulking”;
- whether photo 103 is the same plant as 104;
- whether photo 95 or 94 belongs to a specific growing unit;
- whether any image is blurry, underexposed, cropped, or duplicated;
- canopy area or greenness from pixels.

Practical implication:

> The endpoint is ready for visual AI workflows, but the assistant/runtime still needs a way to actually load the image pixels from `image_url`.

Recommended implementation options:

1. Make the image URL public/signed and consumable by the model runtime.
2. Add `image_base64` or a short-lived `data_url` option for small thumbnails.
3. Add backend-generated low-cost metrics: width, height, blur score, brightness, green pixel ratio.
4. Add a thumbnail endpoint that returns JSON with an accessible image reference, not only binary bytes.

---

# 7. Examples Of Meaningfully Useful Outputs Today

## 7.1 Dashboard Summary Card

The assistant can generate this today:

```markdown
## Plant Tracker Status

- 70 photos total.
- 56 need classification.
- 8 growing units tracked.
- 6 high-priority review items:
  - 2 incident photos.
  - 4 labelled stress/issue photos.
- 10 recent SD-imported photos from 2026-05-29 need review.
- 20 photos have nonzero rotation metadata.
- Only 2 photos currently have location assigned.
```

## 7.2 “Needs Attention” List

```json
{
  "needs_attention": [
    {
      "photo_id": 104,
      "reason": "Rau ram has label sulking",
      "next_action": "Review photo, set type to health_check or incident, compare with earlier Rau ram photos."
    },
    {
      "photo_id": 65,
      "reason": "Garlic chives has label root_bound",
      "next_action": "Set photo type and add follow-up status."
    },
    {
      "photo_id": 95,
      "reason": "delivery_stress label without growing unit",
      "next_action": "Assign plant or mark unknown."
    },
    {
      "photo_id": 94,
      "reason": "delivery_stress label without growing unit",
      "next_action": "Assign plant or mark unknown."
    },
    {
      "photo_id": 66,
      "reason": "Dill incident photo",
      "next_action": "Add issue label or note."
    },
    {
      "photo_id": 88,
      "reason": "Rosemary incident photo",
      "next_action": "Add issue label or note."
    }
  ]
}
```

## 7.3 Sequence-Aware Review Prompt

For photo 104:

```markdown
Photo 104 is an anchor photo:
- Plant: Rau ram
- Label: sulking
- Captured: 2026-05-29 07:12:56Z
- Source: SD import
- Previous photo: 105, captured 2 seconds earlier
- Next photo: 103, captured 24 seconds later

Suggested review flow:
1. Confirm photo 104 type: health_check or incident.
2. Review photo 105 as likely related context.
3. Review photo 103 as likely related context, applying rotation 270.
4. If 105 or 103 show the same plant/session, attach them to Rau ram or mark as related.
```

## 7.4 Bulk Location Fix Candidate

Because only photos 7 and 14 currently have location `Balcony`, but all tracked growing units appear to belong to the balcony setup, the assistant can propose:

```json
{
  "bulk_action_candidate": "assign_location",
  "location_id": 1,
  "location_name": "Balcony",
  "candidate_photo_ids": [
    65, 64, 85, 84, 83, 82, 81, 80, 86, 88, 87, 90, 89, 96, 104
  ],
  "confidence": "medium",
  "requires_user_confirmation": true,
  "reason": "These photos are attached to known balcony growing units but have no location."
}
```

## 7.5 Baseline Candidate List

| Growing unit | Candidate baseline | Why |
|---|---:|---|
| Chillis | 7 | Earliest associated photo; location present; rotation 0 |
| Rosemary | 14 | Earliest associated photo; location present; rotation 0 |
| Dill | none yet | Only known photo is an incident |
| Garlic chives | 80 or 65 | 65 has issue label; 80 may be follow-up but rotated |
| Thai basil vendita | 64 or 82 | Two same-day records, both rotated |
| French tarragon | 85 or 81 | Two same-day records, both rotated |
| Rau ram | 84 or 86 | Earlier than sulking photo; both rotated |
| Sorrel | 83, 90, or 89 | Multiple records; all rotated |

Interpretation:

- Baselines should be selected visually, but metadata can narrow the candidates.
- Chillis and Rosemary already have strong metadata baseline candidates.
- Dill needs a non-incident baseline capture.

---

# 8. Recommended Product Changes Based On The Trial

## 8.1 Add A Review Queue Endpoint

```http
GET /assistant/review-queue
```

Example response:

```json
{
  "summary": {
    "total_photos": 70,
    "unclassified": 56,
    "high_priority": 6,
    "recent_sd_imports": 10,
    "rotation_review": 20
  },
  "queues": [
    {
      "name": "needs_attention",
      "photo_ids": [104, 65, 95, 94, 66, 88]
    },
    {
      "name": "recent_sd_imports",
      "photo_ids": [109, 108, 107, 106, 105, 104, 103, 102, 101, 100]
    },
    {
      "name": "labelled_no_plant",
      "photo_ids": [95, 94]
    },
    {
      "name": "plant_attached_missing_type",
      "photo_ids": [7, 14, 65, 64, 85, 84, 83, 82, 81, 80, 86, 87, 90, 89, 96, 104]
    }
  ]
}
```

## 8.2 Add Review Actions

Suggested endpoints:

```http
POST /assistant/photos/{photo_id}/set-photo-type
POST /assistant/photos/{photo_id}/set-location
POST /assistant/photos/{photo_id}/attach-growing-unit
POST /assistant/photos/{photo_id}/add-label
POST /assistant/photos/{photo_id}/mark-reviewed
POST /assistant/photos/{photo_id}/mark-not-useful
```

## 8.3 Add Session / Burst Grouping

The current data clearly contains bursts:

- 2026-05-26 17:32–17:33;
- 2026-05-27 05:30–05:32;
- 2026-05-27 12:47–12:48;
- 2026-05-27 17:10–17:11;
- 2026-05-29 07:11–07:13.

Suggested derived field:

```json
{
  "capture_session_id": "2026-05-29T0711Z_sd_sequence",
  "photo_ids": [109, 108, 107, 106, 105, 104, 103, 102, 101, 100]
}
```

This would make review screens much more efficient.

## 8.4 Add Precomputed Image Metrics

To align with the roadmap and avoid premature ML, add simple deterministic metrics before custom ML:

```json
{
  "photo_id": 104,
  "image_metrics": {
    "width_px": null,
    "height_px": null,
    "brightness_mean": null,
    "blur_score": null,
    "green_pixel_ratio": null,
    "dominant_rotation_applied": true
  }
}
```

Useful first metrics:

- image width/height;
- blur score;
- brightness/exposure;
- green pixel ratio;
- perceptual hash;
- duplicate/near-duplicate candidates;
- rough green bounding box.

## 8.5 Store AI Suggestions Separately

Do not write assistant guesses directly into confirmed metadata.

Recommended pattern:

```json
{
  "photo_id": 104,
  "suggestion_type": "photo_type",
  "suggested_value": "health_check",
  "confidence": 0.7,
  "reason": "Photo has existing stress label sulking and is attached to Rau ram.",
  "requires_review": true
}
```

---

# 9. Updated Feasibility Assessment

## Useful Now

The assistant can already do:

- dataset status summaries;
- missing-field audits;
- review queues;
- timeline summaries;
- issue/stress queues;
- baseline candidate selection;
- sequence-aware review suggestions;
- schema/API recommendations.

## Useful Now With Vision Context

The assistant can now also do:

- context-rich photo review prompts;
- known-plant-constrained tagging prompts;
- neighbouring-photo sequence planning;
- better review prioritisation around anchored photos;
- better UI payload design for photo review.

## Not Yet Fully Useful In This Runtime

The assistant still cannot directly produce reliable visual observations from pixels in this run.

Blocked examples:

- “photo 104 visibly shows wilting”;
- “photo 103 is also Rau ram”;
- “photo 95 is French tarragon”;
- “this image is blurry”;
- “canopy coverage is 42%.”

These become feasible once the image URL is actually loaded by a vision-capable model or once the backend supplies precomputed metrics.

---

# 10. Best Next Step

The highest-value next feature is a review screen powered by the new vision context endpoint.

Suggested first workflow:

1. Load `needs_attention` queue.
2. For each photo, fetch `vision-context`.
3. Display rotated image.
4. Show known growing units.
5. Show existing labels.
6. Show nearby photos.
7. Ask user to confirm:
   - growing unit;
   - photo type;
   - labels;
   - location;
   - reviewed/not useful.

Recommended first queue:

```json
[104, 65, 95, 94, 66, 88]
```

Recommended second queue:

```json
[109, 108, 107, 106, 105, 104, 103, 102, 101, 100]
```

---

# 11. Bottom Line

The live trial confirms that the assistant is already useful for real data-processing work.

The strongest current outputs are:

- review queues;
- plant timelines;
- missing metadata audits;
- high-priority issue queues;
- sequence-aware classification prompts.

The new `vision-context` endpoint is the correct API shape and materially improves what the assistant can do. It turns isolated photo metadata into reviewable photo context.

The remaining gap is pixel access. Once the assistant or backend can actually load the returned image URL as image data, the next evaluation can add true visual examples: likely plant, visible stress, photo quality, duplicate/near-duplicate status, and rough canopy observations.

Recommended principle remains:

> AI suggests; user confirms; deterministic CV measures; custom ML waits.

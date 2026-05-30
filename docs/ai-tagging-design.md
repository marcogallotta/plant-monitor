# AI-Assisted Tagging & Capture Queue — Design Doc

_Date: 2026-05-29_
_Status: Draft_

---

## Context

This doc covers two sequential features:

1. **Claude-assisted tagging**: unclassified photos → Claude suggestions → human review → DB write. Build now.
2. **Capture queue**: gap detection → "what to photograph next" → Pi acts on it. Build before Pi arrives (Pi Zero 2W arriving Mon/Tue).

Both live in the web UI. Neither writes final data without human confirmation.

Note: `growing_units`, `photo_labels`, and `photo_type` are already in the DB.

---

## What the trial run taught us

Before describing the design, here's what the human-Claude tagging loop looked like in practice (May 2026 session):

| Photo | Claude's read | Reality | Why it failed |
|---|---|---|---|
| Lemongrass (ID 5) | Garlic chives | Lemongrass | Visually similar at this angle. Species ID needs known-plant list + close-up |
| Dill pre-aphid (ID 67) | Healthy dill on counter | Floppy dill, early aphid stress | No targeted "is it drooping?" prompt. Generic description missed it |
| Garlic chives bundle (ID 69) | Harvested leaves | New plant arrival | No context that this was delivery day |
| Thyme in flower (ID 4) | Thyme | Lemon thyme, stress-flowering | Variety and stress history both invisible without metadata |

**Key lessons:**

- **Timestamp proximity is a strong signal.** Photos taken within 60 seconds of each other are almost certainly the same subject or event. Photos from the same 10-minute window are the same session. This should influence how the batch is assembled and what context Claude receives.
- **Targeted prompts beat generic ones.** "Is the plant standing upright or drooping?" catches floppy-dill stress. "Look for insect clusters on stems" catches aphids. A generic prompt would not have flagged either.
- **Delivery-day context unlocks plant association.** If the batch hint says "new deliveries", a bundle of leaves reads as new_purchase, not harvest.
- **Variety information is invisible from photos alone.** Lemon thyme vs. thyme, peppermint vs. spearmint — Claude cannot distinguish these without being told the known plant list including varieties.

---

## What the bulk backfill taught us (≈2,600-photo triage, May 2026)

A one-off backfill of the phone camera roll (2,626 JPEGs) was triaged into the DB. Method: downscale to 160px thumbnails, pack 25 per 5×5 **contact sheet**, and have Claude judge whole sheets at once for a binary **keep / discard** ("is this a monitoring photo of one of my plants?"). This is the cheap **pre-filter gate** that should run _before_ the per-photo species/condition tagging described below. Result: 2,626 → 891 phone keepers (956 total with manual/sd).

**This is a separate, earlier stage than the tagging loop above.** Tagging assumes the photo is already a legitimate plant photo. The backfill showed that assumption doesn't hold for a raw camera roll — roughly **half** of it is not monitoring material at all, and that junk must be filtered first or it pollutes the suggestion queue.

### The keep/discard rule (learned by correction)

The bar is **narrower than "gardening-related."** Keep only if an **actual living plant of the user's own** is in frame — in a pot/planter/tray, including seedlings, wilted, dying, ugly. Discard, even when green or garden-adjacent:

- Bare soil / potting mix / sand / substrate close-ups with no visible plant
- Empty pots, saucers, drainage trays, stacked planters
- Garden-product packaging (fertiliser/pesticide bottles, soil bags, seed boxes)
- Store / nursery displays: seed-packet racks, plants-for-sale shelves
- Store-bought / bagged herbs with price tags; harvested herbs being washed, weighed, bundled, or on a cutting board
- Cooking / food; kitchen scraps (onion/ginger) sprouting in a pan
- Screens, thermostats, documents

### Calibration numbers (useful for setting auto-filter thresholds)

- **False-keep rate ≈30%** in the first two human-reviewed batches before the rule tightened. The single biggest miscalibration: treating "contains a plant or gardening context" as keep. Requiring an actual living plant would have caught ~1/3 of the over-keeps.
- An aggressive automated discard pass then had a **false-reject rate ≈8%** — genuine potted seedlings wrongly discarded. So an automated gate should **bias toward keep on ambiguous soil/tray shots** and surface them for a cheap human glance rather than hard-deleting.

### Confusable categories a classifier must handle

These are the boundaries that produced nearly all the errors at thumbnail scale:

- **Grains / oats / flour / sawdust vs. soil** — visually identical at 160px; the food versions are the trap.
- **Sparse seedling tray vs. bare-soil tray** — a freshly-sown cell tray reads as "empty soil." Bias keep.
- **Lemongrass / leek / spring-onion stalks** — harvested-on-a-board (discard) vs. growing-in-a-pot (keep) vs. rooting-in-water for propagation (keep).
- **Sprouting kitchen scraps vs. propagation** — onion bottoms in a glass (discard) look like a deliberate cutting (keep).
- **Jars of yellowish liquid** — recurring false-keep (assumed propagation/rooting in water); at least one was not horticultural at all. Default discard unless a plant/cutting is clearly visible in the jar.

**Implication for the pipeline:** add a cheap binary keep/discard gate (thumbnail-grid batching keeps the token cost near-free) ahead of the expensive per-photo tagging. Photos that fail the gate never reach `photo_ai_suggestions`. Ambiguous gate results get a lightweight "confirm import" review, distinct from the richer tagging review.

---

## Claude-assisted tagging

### Flow

```
Unclassified photo queue
  → User optionally adds batch hint
  → Backend: thumbnail + hint + known plants + temporal neighbours → Claude API
  → Claude returns: suggested_plant, photo_type, labels, confidence, question
  → Dashboard shows suggestion alongside photo
  → User: Accept / Edit / Reject
  → Accepted suggestions write to photos + photo_labels tables
```

Claude never writes to the final tables directly. It writes to `photo_ai_suggestions`. Human confirmation moves values across.

### Batch hints

The hint input is the key feature. Without it, Claude guesses blind. With it, accuracy jumps dramatically.

Examples:
- `"These are from delivery day — probably rau ram and sorrel arriving"`
- `"Balcony session, mostly herbs on the shelf"`
- `"Repotting session — expect root balls and disturbed soil"`
- `"Check for stress — I was away for a week"`

Hint is stored with each suggestion row so the reasoning is auditable.

### Temporal context Claude receives

For each photo, the prompt includes:
- Thumbnail (base64, 256px — already served by `/assistant/photos/{id}/vision-context`)
- Batch hint (if set)
- Photos captured within ±5 minutes: their IDs, timestamps, and any already-confirmed plant associations
- Known growing units list (names, types, varieties)
- Existing labels on this photo (if any)

This means if photo A in a burst is confidently identified as sorrel, photo B taken 30 seconds later gets that as a strong prior.

### Claude's structured response

```json
{
  "suggested_plant_id": 12,
  "suggested_plant_name": "Sorrel",
  "confidence": "high",
  "suggested_photo_type": "health_check",
  "suggested_labels": ["delivery_stress", "wilting"],
  "question": null,
  "observation": "Plant is dramatically drooping over pot sides, reddish stems, consistent with transplant shock."
}
```

When `confidence` is `"low"`, `question` is populated:
```json
{
  "suggested_plant_id": null,
  "confidence": "low",
  "question": "The long flat leaves resemble either lemongrass or garlic chives. Which is registered on this balcony?",
  "observation": "Cannot distinguish without knowing the known-plant list variants."
}
```

Questions are shown in the dashboard review UI and the user can answer inline, which re-runs the suggestion for that photo.

### DB schema

```sql
CREATE TABLE photo_ai_suggestions (
    id SERIAL PRIMARY KEY,
    photo_id INTEGER NOT NULL REFERENCES photos(id),
    model VARCHAR(100) NOT NULL,
    batch_hint TEXT,
    prompt_context JSONB,          -- temporal neighbours, known plants sent
    suggested_plant_id INTEGER REFERENCES growing_units(id),
    suggested_plant_name TEXT,     -- raw text if no match found
    suggested_photo_type TEXT,
    suggested_labels JSONB,        -- list of label strings
    confidence TEXT,               -- high / medium / low
    question TEXT,                 -- populated when confidence is low
    observation TEXT,              -- one-sentence visual note
    status TEXT NOT NULL DEFAULT 'pending',  -- pending / accepted / rejected / edited
    edited_plant_id INTEGER REFERENCES growing_units(id),
    edited_photo_type TEXT,
    edited_labels JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ
);
```

`edited_*` fields hold the human's corrections if they chose "Edit" rather than "Accept" or "Reject".

### API endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/assistant/ai-suggestions/batch` | Submit photo IDs + hint → runs Claude → stores suggestions |
| `GET` | `/assistant/ai-suggestions` | List pending suggestions (with photo thumbnails) |
| `PATCH` | `/assistant/ai-suggestions/{id}` | Accept / reject / edit a suggestion |
| `POST` | `/assistant/ai-suggestions/{id}/rerun` | Re-run with updated hint or user answer to question |

Accepting a suggestion via `PATCH` triggers the write to `photos.photo_type`, `photo_growing_units`, and `photo_labels` in a single transaction.

### Web UI — review panel

The dashboard gets a new **"Review" tab** (or sidebar panel):

```
┌─────────────────────────────────────────────────────┐
│ Unreviewed suggestions: 14                          │
│ Batch hint: [                              ] [Run]  │
├───────────────────┬─────────────────────────────────┤
│  [Photo thumbnail] │ Suggested: Sorrel               │
│                   │ Type: health_check               │
│                   │ Labels: delivery_stress, wilting │
│                   │ Confidence: high                 │
│                   │ "Plant dramatically drooping..." │
│                   │                                  │
│                   │ [Accept] [Edit] [Reject]         │
├───────────────────┼─────────────────────────────────┤
│  [Photo thumbnail] │ ⚠ Question:                     │
│                   │ "Long flat leaves — lemongrass   │
│                   │ or garlic chives?"               │
│                   │                                  │
│                   │ [Answer: ___________] [Rerun]   │
└───────────────────┴─────────────────────────────────┘
```

Keyboard shortcuts: `A` accept, `R` reject, `E` edit, arrow keys to navigate. Same pattern as the existing photo modal.

---

## Capture queue (Pi integration)

### Purpose

Build this before the Pi arrives so it's ready on day one. The Pi auto-captures overviews on a schedule; the system tells it what to photograph next and why. This closes the loop: Claude analyses overviews → flags gaps or concerns → Pi captures follow-up → Claude reviews again.

### Gap detection rules

The backend evaluates these rules against current DB state to produce capture requests:

| Rule | Trigger | Suggested shot |
|---|---|---|
| Stress label with no follow-up | Plant has `wilting`/`sulking`/`delivery_stress` and no photo in last 3 days | `health_check` overview |
| Incident with no resolution | `aphids`/`pest_damage` label and no follow-up photo | `closeup` of affected area |
| No photo in 7+ days | Growing unit has no photo this week | `overview` |
| Unregistered plant visible | Photo with `multi_plant` flag and no plant association | `overview` of each pot individually |
| Post-repot gap | `root_bound` label and no photo since event date | `health_check` |
| New purchase with no follow-up | `new_purchase` or `delivery_stress` and no photo 48h later | `health_check` |

### Capture request schema

```sql
CREATE TABLE capture_requests (
    id SERIAL PRIMARY KEY,
    growing_unit_id INTEGER REFERENCES growing_units(id),
    plant_name TEXT,               -- for unregistered plants
    suggested_shot_type TEXT NOT NULL,  -- overview / closeup / health_check
    reason TEXT NOT NULL,
    priority INTEGER DEFAULT 2,    -- 1=urgent, 2=normal, 3=low
    source_photo_id INTEGER REFERENCES photos(id),  -- photo that triggered this
    status TEXT NOT NULL DEFAULT 'open',  -- open / captured / dismissed
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);
```

### API

```
GET /assistant/capture-queue         → open requests, ordered by priority
PATCH /assistant/capture-queue/{id}  → mark captured or dismissed
```

The Pi checks `GET /assistant/capture-queue` before each session. When it captures a photo that satisfies a request, it POSTs the photo and patches the request `status: captured`.

### Web UI — capture queue panel

Second tab in the Review panel:

```
┌─────────────────────────────────────────────────────┐
│ Capture queue: 4 open                               │
├─────────────────────────────────────────────────────┤
│ ● URGENT  Rau ram — health_check                    │
│   "Last photo (104) shows severe wilt. 2 days ago." │
│   [Dismiss]                                         │
├─────────────────────────────────────────────────────┤
│ ● NORMAL  Dill — closeup                            │
│   "Aphid infestation documented (photo 66). No      │
│    follow-up since."                                │
│   [Dismiss]                                         │
├─────────────────────────────────────────────────────┤
│ ● LOW     Lemon thyme — overview                    │
│   "No photo since stress event. Recovery unclear."  │
│   [Dismiss]                                         │
└─────────────────────────────────────────────────────┘
```

---

## What this enables end-to-end

```
Pi captures overview on schedule
  → photo uploaded, enters unclassified queue
  → Claude runs on it (or user triggers batch)
  → suggestion: "Rau ram, health_check, wilting"
  → user accepts in 2 keystrokes
  → capture queue sees: wilting + no follow-up in 3 days
  → capture queue adds: "Rau ram closeup, urgent"
  → Pi (or you) captures closeup
  → repeat
```

The human stays in the loop at the tagging step and the capture step. Claude handles the pattern recognition and the gap detection. You handle the judgment calls — which is exactly how the manual session above worked.

---

## Build order

**Tagging:**
1. `photo_ai_suggestions` table + migration
2. Batch suggestion API endpoint (sync, Claude API)
3. Review panel in dashboard (accept/edit/reject + keyboard shortcuts)

**Capture queue:**
4. `capture_requests` table + gap detection rules
5. Capture queue API (`GET /assistant/capture-queue`)
6. Capture queue panel in dashboard

---

## Open questions

- Should the batch suggestion endpoint be synchronous (wait for Claude) or async (job queue + polling)? For 70 photos, sync is fine. For ongoing Pi imports at scale, async is better.
- Should `capture_requests` be auto-generated on a schedule, or triggered manually after each import batch?
- Do we want a mobile-friendly review UI for quick yes/no from the phone, or is desktop-only fine for now?

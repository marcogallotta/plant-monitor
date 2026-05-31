#!/usr/bin/env python3
"""Submit unclassified photos to the Anthropic Batch API for AI tagging (Phase 1).

Usage:
    python scripts/submit_tagging_batch.py [options]

Options:
    --run-id ID          Run ID slug (default: YYYYMMDD_HHMMSS)
    --limit N            Only process the first N unclassified photos
    --thin-prior         Omit container map — use species list only (A/B test)
    --include-pending    Include photos that already have a pending suggestion
    --backend-url URL    Backend base URL (default: http://localhost:<BACKEND_PORT>)
    --dry-run            Print plan without submitting

Reads ANTHROPIC_API_KEY and ASSISTANT_API_TOKEN from environment.
Writes manifest to data/tagging-runs/<run_id>/manifest.json.
"""

import argparse
import base64
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from PIL import Image

# fmt: off
# The Phase-1 system prompt — use verbatim (only the container map section differs between variants)
_PROMPT_INTRO = """\
You identify plants in photos from ONE person's balcony herb garden. CLOSED-SET task:
every photo shows plants from the KNOWN LIST. MATCH to the list — do not identify plants
in general, and do not free-guess outside it.

KNOWN PLANTS (only valid labels):
  Distinctive: dill, parsley, rocket, rosemary, sage, sorrel, French tarragon, fenugreek, lemongrass
  Confusable groups (use options): peppermint/Moroccan mint/spearmint · chives/garlic chives/Welsh onion ·
    parsley/cilantro · genovese basil/Thai basil · bird's-eye/Hangjiao-H7/Hangjiao-H4 chilli ·
    lemongrass/rau ram · sorrel/rau ram · thyme/lemon thyme
  (Two real Thai basils — "Thai basil" and "Thai basil vendita". Label "Thai basil"; always
   present both as a binary on review.)"""

_CONTAINER_MAP = """
CONTAINER MAP (HINTS, not facts — pots move and troughs get replanted):
  trough: dill + parsley + chives
  trough: 2 genovese basil + 1 Thai basil
  trough: rocket + cilantro
  trough: Moroccan mint (solo)
  small trough: Welsh onion (seedlings) | cilantro (solo) | fenugreek (solo) | thyme + lemon thyme
  round pots: one plant each (peppermint, rosemary, sage, sorrel, rau ram, lemongrass, French tarragon, garlic chives…)
  trays: tiny seedlings
  → If a trough's visible composition matches a known one, prefer that grouping. If it does
    NOT match, say so — never force the expected plants."""

_PROMPT_RULES = """
RULES:
1. MATCH, don't free-guess. Resembles something off-list ⇒ it's almost certainly the nearest
   KNOWN plant. "unknown" only if nothing fits.
2. Do NOT over-assign a common label (a past run dumped "lemongrass" on anything long/thin).
   Unsure between candidates ⇒ options, never a confident single guess.
3. One photo usually shows SEVERAL plants/zones. Output one object PER plant/zone. Scan all
   four edges — secondary plants at the frame edge are the most-missed.
4. CONFUSABLES ⇒ fill `options` (2–3), not a single pick. Disambiguate by container where the
   map allows (pot=peppermint, trough=Moroccan mint).
5. SEEDLINGS: never force a species. plant="SEEDLINGS" by default; only narrow to a genus
   (options) with decent confidence, or to a species if the leaves are clear OR the container
   composition pins it.
6. CONFIDENCE is honest. "high" only for distinctive, unambiguous mature plants. Anything in a
   confusable group is at most "medium" and carries options. Confidence is NOT permission to
   guess.
7. NON-PLANT (bare soil, tools, test/process, food, screens): plant=null, photo_type=null,
   labels=["delete_candidate"], say why. Do NOT set photo_type to "delete".
8. Note CONDITION/STAGE in observation: seedling/young/mature/flowering; wilting/yellowing/pests.
9. suggested_rotation if the image is clearly mis-oriented.

OUTPUT — ONLY a JSON array, one object per plant/zone:
[
  { "plant": "<known name | SEEDLINGS | null>",
    "options": ["…"],                 // [] if confident
    "confidence": "high|medium|low",
    "photo_type": "overview|health_check|closeup|null",
    "labels": [],                      // e.g. ["seedling"], ["delete_candidate"]
    "region": [x,y,x2,y2],             // normalised 0–1; null = whole photo
    "observation": "<≤8 words: stage/condition>" }
]
No prose outside the array."""
# fmt: on

SYSTEM_PROMPT_RICH = _PROMPT_INTRO + _CONTAINER_MAP + _PROMPT_RULES
SYSTEM_PROMPT_THIN = _PROMPT_INTRO + "\n\n[Container map omitted — classify by visual appearance only]" + _PROMPT_RULES

MAX_LONG_EDGE = 1024
MODEL = os.environ.get("TAGGING_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = int(os.environ.get("TAGGING_MAX_TOKENS", "2048"))

SCRIPTS_DIR = Path(__file__).parent
REPO_ROOT = SCRIPTS_DIR.parent
PHOTOS_DIR = REPO_ROOT / "data" / "photos"
RUNS_DIR = REPO_ROOT / "data" / "tagging-runs"


def _resize_and_encode(path: Path, rotation: int = 0) -> str | None:
    """Open image, apply stored CW rotation so the model sees an upright frame, then encode."""
    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            # `rotation` is stored as degrees CW to display correctly; bake it in before sending.
            if rotation == 90:
                img = img.transpose(Image.Transpose.ROTATE_270)
            elif rotation == 180:
                img = img.transpose(Image.Transpose.ROTATE_180)
            elif rotation == 270:
                img = img.transpose(Image.Transpose.ROTATE_90)
            w, h = img.size
            if max(w, h) > MAX_LONG_EDGE:
                scale = MAX_LONG_EDGE / max(w, h)
                img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return base64.standard_b64encode(buf.getvalue()).decode()
    except Exception as e:
        print(f"  [warn] could not process {path.name}: {e}", file=sys.stderr)
        return None


def _get_photos(base_url: str, token: str) -> list[dict]:
    with httpx.Client(headers={"Authorization": f"Bearer {token}"}, timeout=60) as client:
        r = client.get(f"{base_url}/assistant/unclassified")
        r.raise_for_status()
        return r.json()


def _pending_photo_ids() -> set[int]:
    """Return photo IDs that already have a pending suggestion (via DB)."""
    try:
        # Import here so the script can still run without a DB if needed
        sys.path.insert(0, str(REPO_ROOT / "backend"))
        from app.database import build_engine, build_session_factory
        from app.models import PhotoAiSuggestion

        session_factory = build_session_factory(build_engine())
        with session_factory() as db:
            rows = db.query(PhotoAiSuggestion.photo_id).filter(
                PhotoAiSuggestion.status == "pending"
            ).all()
            return {r[0] for r in rows}
    except Exception as e:
        print(f"  [warn] could not query pending suggestions: {e}", file=sys.stderr)
        return set()


def submit(
    *,
    base_url: str,
    token: str,
    api_key: str,
    run_id: str,
    limit: int | None,
    thin_prior: bool,
    include_pending: bool,
    dry_run: bool,
) -> None:
    from anthropic import Anthropic
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    print("Fetching unclassified photos…")
    photos = _get_photos(base_url, token)
    photos.sort(key=lambda p: p["captured_at"])
    print(f"  {len(photos)} unclassified photo(s)")

    if not include_pending:
        pending_ids = _pending_photo_ids()
        before = len(photos)
        photos = [p for p in photos if p["id"] not in pending_ids]
        skipped = before - len(photos)
        if skipped:
            print(f"  skipped {skipped} photo(s) with existing pending suggestions (--include-pending to override)")

    if limit is not None:
        photos = photos[:limit]

    if not photos:
        print("Nothing to submit.")
        return

    # Session-group ordering for provenance (we don't use the grouping for batching)
    sys.path.insert(0, str(SCRIPTS_DIR))
    from prepare_tagging_run import group_into_sessions
    sessions = group_into_sessions(photos, gap_minutes=15)
    print(f"  → {len(photos)} photo(s) across {len(sessions)} session(s)")

    system_prompt = SYSTEM_PROMPT_THIN if thin_prior else SYSTEM_PROMPT_RICH
    prior_label = "thin" if thin_prior else "rich"

    print(f"\nReading and resizing photos (max {MAX_LONG_EDGE}px long edge)…")
    requests = []
    skipped_files = []
    for i, photo in enumerate(photos, 1):
        filename = photo.get("filename") or photo.get("id")
        photo_path = PHOTOS_DIR / (filename if "." in str(filename) else f"{filename}.jpg")

        # Try common extensions if exact match not found
        if not photo_path.exists():
            for ext in (".jpg", ".jpeg", ".JPG", ".JPEG"):
                candidate = PHOTOS_DIR / (str(filename).rsplit(".", 1)[0] + ext)
                if candidate.exists():
                    photo_path = candidate
                    break

        if not photo_path.exists():
            print(f"  [warn] photo file not found: {photo_path.name}", file=sys.stderr)
            skipped_files.append(photo["id"])
            continue

        rotation = photo.get("rotation") or 0
        b64 = _resize_and_encode(photo_path, rotation=rotation)
        if b64 is None:
            skipped_files.append(photo["id"])
            continue

        if i % 50 == 0 or i == len(photos):
            print(f"  {i}/{len(photos)} photos encoded")

        captured_at = photo.get("captured_at", "")
        requests.append(Request(
            custom_id=str(photo["id"]),
            params=MessageCreateParamsNonStreaming(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=[{
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": f"Captured: {captured_at}",
                        },
                    ],
                }],
            ),
        ))

    if skipped_files:
        print(f"  [warn] skipped {len(skipped_files)} photo(s) due to missing/unreadable files")

    if not requests:
        print("No requests to submit.")
        return

    photo_ids = [int(r.custom_id) for r in requests]
    print(f"\n{len(requests)} request(s) ready  |  prior: {prior_label}  |  model: {MODEL}")

    if dry_run:
        print("\n[dry-run] Would submit batch — exiting without submitting.")
        return

    print("Submitting batch…")
    client = Anthropic(api_key=api_key)
    batch = client.messages.batches.create(requests=requests)
    batch_id = batch.id
    print(f"  batch_id: {batch_id}")
    print(f"  status:   {batch.processing_status}")

    out_dir = RUNS_DIR / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "run_id": run_id,
        "batch_id": batch_id,
        "prior": prior_label,
        "model": MODEL,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "total_photos": len(requests),
        "photo_ids": photo_ids,
        "status": "submitted",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nRun saved → {out_dir}/manifest.json")
    print(f"Ingest when ready:  python scripts/ingest_tagging_batch.py --run-id {run_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-id", metavar="ID", help="Run ID slug (default: YYYYMMDD_HHMMSS)")
    parser.add_argument("--limit", type=int, metavar="N", help="Only process first N photos")
    parser.add_argument("--thin-prior", action="store_true", help="Omit container map (A/B test)")
    parser.add_argument("--include-pending", action="store_true", help="Include photos with existing pending suggestions")
    parser.add_argument("--backend-url", metavar="URL", help="Backend base URL")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without submitting")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key and not args.dry_run:
        sys.exit("error: ANTHROPIC_API_KEY environment variable not set")

    token = os.environ.get("ASSISTANT_API_TOKEN", "")
    if not token:
        sys.exit("error: ASSISTANT_API_TOKEN environment variable not set")

    port = os.environ.get("BACKEND_PORT", "8000")
    base_url = (args.backend_url or f"http://localhost:{port}").rstrip("/")

    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = RUNS_DIR / run_id
    if out_dir.exists() and not args.dry_run:
        sys.exit(f"error: run directory already exists: {out_dir}  (pass --run-id to use a different ID)")

    submit(
        base_url=base_url,
        token=token,
        api_key=api_key,
        run_id=run_id,
        limit=args.limit,
        thin_prior=args.thin_prior,
        include_pending=args.include_pending,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()

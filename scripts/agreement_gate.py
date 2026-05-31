#!/usr/bin/env python3
"""Agreement gate: submit flagged Sonnet suggestions to Opus for cross-validation.

Two-step flow:
  Step 1 — submit Opus batch:
    python scripts/agreement_gate.py --run-id <sonnet_run_id>

  Step 2 — ingest Opus results and reconcile:
    python scripts/agreement_gate.py --run-id <sonnet_run_id> --ingest-opus-run <opus_run_id>

Flagged rows (sent to Opus):
  - has options (confusable group)
  - confidence is low or medium
  - suggested_plant_name == "SEEDLINGS"

Reconciliation:
  - Agree: update confidence to "high", add prompt_context.opus_agrees=true
  - Disagree: add prompt_context.opus_disagrees=true + question describing the conflict

Reads ANTHROPIC_API_KEY and ASSISTANT_API_TOKEN from environment.
"""

import argparse
import base64
import io
import json
import os
import sys
import time
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
REPO_ROOT = SCRIPTS_DIR.parent
PHOTOS_DIR = REPO_ROOT / "data" / "photos"
RUNS_DIR = REPO_ROOT / "data" / "tagging-runs"

for _p in (REPO_ROOT / "backend", REPO_ROOT):
    if (_p / "app").is_dir():
        sys.path.insert(0, str(_p))
        break
sys.path.insert(0, str(SCRIPTS_DIR))

from PIL import Image

MODEL_OPUS = os.environ.get("AGREEMENT_MODEL", "claude-opus-4-8")
MAX_LONG_EDGE = 1024
MAX_TOKENS = int(os.environ.get("TAGGING_MAX_TOKENS", "2048"))

# Reuse the same system prompt from submit_tagging_batch
from submit_tagging_batch import SYSTEM_PROMPT_RICH, _resize_and_encode
from ingest_tagging_batch import _parse_model_output, _region_to_coords


def _is_flagged(row) -> bool:
    """Return True if this suggestion should go to the Opus agreement gate."""
    return (
        (row.suggested_options and len(row.suggested_options) > 0)
        or row.confidence in ("low", "medium")
        or row.suggested_plant_name == "SEEDLINGS"
    )


def _get_photo_meta(photo_id: int, db) -> tuple[Path | None, int, str]:
    """Return (disk_path, rotation, captured_at_iso) for a photo, querying the DB once."""
    from app.models import Photo
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        return None, 0, ""
    filename = photo.filename
    rotation = photo.rotation or 0
    captured_at = photo.captured_at.isoformat() if photo.captured_at else ""
    path = PHOTOS_DIR / filename
    if path.exists():
        return path, rotation, captured_at
    for ext in (".jpg", ".jpeg", ".JPG"):
        candidate = PHOTOS_DIR / (str(filename).rsplit(".", 1)[0] + ext)
        if candidate.exists():
            return candidate, rotation, captured_at
    return None, rotation, captured_at


def submit_opus_batch(sonnet_run_id: str, api_key: str, dry_run: bool) -> None:
    from anthropic import Anthropic
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    from app.database import build_engine, build_session_factory
    from app.models import PhotoAiSuggestion

    run_dir = RUNS_DIR / sonnet_run_id
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        sys.exit(f"error: Sonnet manifest not found: {manifest_path}")

    session_factory = build_session_factory(build_engine())

    print(f"Querying flagged suggestions from run {sonnet_run_id}…")
    with session_factory() as db:
        all_suggestions = (
            db.query(PhotoAiSuggestion)
            .filter(
                PhotoAiSuggestion.status == "pending",
                PhotoAiSuggestion.prompt_context["run_id"].astext == sonnet_run_id,
            )
            .all()
        )
        flagged = [s for s in all_suggestions if _is_flagged(s)]
        print(f"  {len(all_suggestions)} pending suggestions → {len(flagged)} flagged for Opus")

        if not flagged:
            print("Nothing to submit to Opus.")
            return

        # Collect unique photo IDs needed
        photo_ids_needed = list({s.photo_id for s in flagged})
        print(f"  {len(photo_ids_needed)} unique photo(s) to re-encode")

        photo_b64: dict[int, str] = {}
        photo_captured_at: dict[int, str] = {}
        for photo_id in photo_ids_needed:
            path, rotation, captured_at = _get_photo_meta(photo_id, db)
            if path is None:
                print(f"  [warn] photo {photo_id} not found on disk", file=sys.stderr)
                continue
            b64 = _resize_and_encode(path, rotation=rotation)
            if b64:
                photo_b64[photo_id] = b64
                photo_captured_at[photo_id] = captured_at

        # One request per unique photo (Opus sees the full image, not per-region)
        seen_photos = set()
        requests = []
        for suggestion in flagged:
            pid = suggestion.photo_id
            if pid in seen_photos or pid not in photo_b64:
                continue
            seen_photos.add(pid)
            requests.append(Request(
                custom_id=str(pid),
                params=MessageCreateParamsNonStreaming(
                    model=MODEL_OPUS,
                    max_tokens=MAX_TOKENS,
                    system=[{
                        "type": "text",
                        "text": SYSTEM_PROMPT_RICH,
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
                                    "data": photo_b64[pid],
                                },
                            },
                            {
                                "type": "text",
                                "text": f"Captured: {photo_captured_at.get(pid, '')}",
                            },
                        ],
                    }],
                ),
            ))

    print(f"\n{len(requests)} Opus request(s)  |  model: {MODEL_OPUS}")

    if dry_run:
        print("[dry-run] Would submit Opus batch — exiting.")
        return

    print("Submitting Opus batch…")
    client = Anthropic(api_key=api_key)
    batch = client.messages.batches.create(requests=requests)
    opus_run_id = f"{sonnet_run_id}_opus"
    opus_dir = RUNS_DIR / opus_run_id
    opus_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "run_id": opus_run_id,
        "sonnet_run_id": sonnet_run_id,
        "batch_id": batch.id,
        "model": MODEL_OPUS,
        "prior": "rich",
        "photo_ids": list(seen_photos),
        "status": "submitted",
    }
    (opus_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"  batch_id: {batch.id}")
    print(f"  status:   {batch.processing_status}")
    print(f"\nOpus run saved → {opus_dir}/manifest.json")
    print(f"\nReconcile when ready:")
    print(f"  python scripts/agreement_gate.py --run-id {sonnet_run_id} --ingest-opus-run {opus_run_id}")


def _plants_agree(sonnet_plant: str | None, sonnet_opts: list, opus_plant: str | None, opus_opts: list) -> bool:
    """Return True if Sonnet and Opus unambiguously agree about what's in the image.

    Agreement requires an exact, confident match — overlapping option sets do NOT count.
    If either model is still listing candidates (options non-empty), it hasn't committed to
    a single answer, so the result still needs human review even if the sets overlap.
    (E.g. Sonnet=Peppermint/Moroccan, Opus=Moroccan/Spearmint overlap on Moroccan but the
    models haven't agreed — a human must choose.)
    """
    def norm(s):
        return (s or "").strip().lower()

    sp, op = norm(sonnet_plant), norm(opus_plant)

    # Both null → agree (both say delete/non-plant)
    if not sp and not op:
        return True

    # Both say SEEDLINGS (known-unknown; agreement is meaningful even without species)
    if sp == "seedlings" and op == "seedlings":
        return True

    # Exact plant name match AND neither model is uncertain (no options on either side)
    if sp and sp == op and not sonnet_opts and not opus_opts:
        return True

    return False


def ingest_opus_and_reconcile(sonnet_run_id: str, opus_run_id: str, api_key: str, poll: bool) -> None:
    from anthropic import Anthropic
    from app.database import build_engine, build_session_factory
    from app.models import PhotoAiSuggestion

    opus_manifest_path = RUNS_DIR / opus_run_id / "manifest.json"
    if not opus_manifest_path.exists():
        sys.exit(f"error: Opus manifest not found: {opus_manifest_path}")

    opus_manifest = json.loads(opus_manifest_path.read_text())
    batch_id = opus_manifest["batch_id"]

    client = Anthropic(api_key=api_key)
    batch = client.messages.batches.retrieve(batch_id)
    print(f"Opus batch {batch_id}: {batch.processing_status}")

    if batch.processing_status != "ended":
        if not poll:
            print("Batch not yet complete. Run with --poll to wait.")
            return
        print("Waiting for Opus batch to complete…")
        while batch.processing_status != "ended":
            time.sleep(60)
            batch = client.messages.batches.retrieve(batch_id)
            print(f"  {batch.processing_status}: {batch.request_counts.processing} processing")

    print("Fetching Opus results…")
    # Collect Opus output keyed by photo_id
    opus_by_photo: dict[int, list[dict]] = {}
    for result in client.messages.batches.results(batch_id):
        photo_id = int(result.custom_id)
        if result.result.type != "succeeded":
            continue
        raw_text = next((b.text for b in result.result.message.content if b.type == "text"), "")
        regions = _parse_model_output(raw_text, photo_id)
        opus_by_photo[photo_id] = regions

    print(f"  Opus results for {len(opus_by_photo)} photo(s)")

    session_factory = build_session_factory(build_engine())
    agreed = disagreed = skipped = 0

    with session_factory() as db:
        flagged_suggestions = (
            db.query(PhotoAiSuggestion)
            .filter(
                PhotoAiSuggestion.status == "pending",
                PhotoAiSuggestion.prompt_context["run_id"].astext == sonnet_run_id,
            )
            .all()
        )

        for row in flagged_suggestions:
            if not _is_flagged(row):
                continue

            opus_regions = opus_by_photo.get(row.photo_id)
            if not opus_regions:
                skipped += 1
                continue

            # Find the Opus region that best matches this Sonnet row (closest to same bbox or first)
            best_opus = opus_regions[0]
            if row.x is not None and len(opus_regions) > 1:
                # Pick the Opus region whose bbox centre is closest
                sx, sy = (row.x + (row.x2 or row.x)) / 2, (row.y + (row.y2 or row.y)) / 2
                def dist(r):
                    reg = r.get("region")
                    if not reg or len(reg) != 4:
                        return float("inf")
                    cx, cy = (reg[0] + reg[2]) / 2, (reg[1] + reg[3]) / 2
                    return (cx - sx) ** 2 + (cy - sy) ** 2
                best_opus = min(opus_regions, key=dist)

            opus_plant = best_opus.get("plant")
            opus_opts = best_opus.get("options") or []
            opus_confidence = best_opus.get("confidence", "low")

            agree = _plants_agree(
                row.suggested_plant_name, row.suggested_options or [],
                opus_plant, opus_opts,
            )

            ctx = dict(row.prompt_context or {})
            ctx["opus_run_id"] = opus_run_id
            ctx["opus_plant"] = opus_plant
            ctx["opus_confidence"] = opus_confidence

            if agree:
                ctx["opus_agrees"] = True
                row.confidence = "high"
                row.prompt_context = ctx
                agreed += 1
            else:
                ctx["opus_disagrees"] = True
                row.prompt_context = ctx
                if not row.question:
                    sonnet_label = row.suggested_plant_name or str(row.suggested_options)
                    opus_label = opus_plant or str(opus_opts)
                    row.question = f"Conflict: Sonnet={sonnet_label!r}, Opus={opus_label!r}"
                disagreed += 1

        db.commit()

    opus_manifest["status"] = "reconciled"
    opus_manifest_path.write_text(json.dumps(opus_manifest, indent=2))

    print(f"\nReconciliation complete:")
    print(f"  {agreed} agreed (confidence promoted to high)")
    print(f"  {disagreed} disagreed (question set for human review)")
    print(f"  {skipped} skipped (no Opus result for photo)")
    print(f"\nReview agreed rows first in the review tab — they have opus_agrees=true in prompt_context.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-id", required=True, metavar="ID", help="Sonnet run ID")
    parser.add_argument("--ingest-opus-run", metavar="OPUS_RUN_ID",
                        help="Reconcile against this Opus run instead of submitting a new batch")
    parser.add_argument("--poll", action="store_true", help="Wait for Opus batch to finish")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without submitting")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key and not args.dry_run:
        sys.exit("error: ANTHROPIC_API_KEY environment variable not set")

    if args.ingest_opus_run:
        ingest_opus_and_reconcile(
            sonnet_run_id=args.run_id,
            opus_run_id=args.ingest_opus_run,
            api_key=api_key,
            poll=args.poll,
        )
    else:
        submit_opus_batch(
            sonnet_run_id=args.run_id,
            api_key=api_key,
            dry_run=args.dry_run,
        )


if __name__ == "__main__":
    main()

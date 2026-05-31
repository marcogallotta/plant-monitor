#!/usr/bin/env python3
"""Fetch Batch API results and ingest them into photo_ai_suggestions.

Usage:
    python scripts/ingest_tagging_batch.py --run-id <run_id> [options]

Options:
    --run-id ID     Run ID (required) — reads data/tagging-runs/<run_id>/manifest.json
    --poll          Wait for the batch to finish before ingesting (checks every 60s)
    --status        Print batch status and exit

Reads ANTHROPIC_API_KEY from environment.
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
REPO_ROOT = SCRIPTS_DIR.parent
RUNS_DIR = REPO_ROOT / "data" / "tagging-runs"

# Inside Docker the backend is mounted at /app (== REPO_ROOT); on the host it lives at
# <repo>/backend/.  Insert whichever contains the `app` package.
for _p in (REPO_ROOT / "backend", REPO_ROOT):
    if (_p / "app").is_dir():
        sys.path.insert(0, str(_p))
        break
sys.path.insert(0, str(SCRIPTS_DIR))


def _parse_model_output(text: str, photo_id: int) -> list[dict]:
    """Extract JSON array from model output, tolerating minor preamble/postamble."""
    text = text.strip()
    # Try direct parse first
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    # Extract first [...] block
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if m:
        try:
            result = json.loads(m.group())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
    print(f"  [warn] could not parse JSON for photo {photo_id}: {text[:120]!r}", file=sys.stderr)
    return []


def _region_to_coords(region) -> tuple[float | None, float | None, float | None, float | None]:
    if not region or not isinstance(region, list) or len(region) != 4:
        return None, None, None, None
    try:
        x, y, x2, y2 = [float(v) for v in region]
        # clamp to [0,1]
        x, y, x2, y2 = [max(0.0, min(1.0, v)) for v in (x, y, x2, y2)]
        return x, y, x2, y2
    except (TypeError, ValueError):
        return None, None, None, None


def _is_duplicate(db, photo_id: int, run_id: str, plant_name: str | None, x, y, x2, y2) -> bool:
    from sqlalchemy import text
    result = db.execute(
        text(
            "SELECT 1 FROM photo_ai_suggestions "
            "WHERE photo_id = :pid "
            "AND prompt_context->>'run_id' = :run_id "
            "AND suggested_plant_name IS NOT DISTINCT FROM :plant "
            "AND x IS NOT DISTINCT FROM :x "
            "AND y IS NOT DISTINCT FROM :y "
            "AND x2 IS NOT DISTINCT FROM :x2 "
            "AND y2 IS NOT DISTINCT FROM :y2 "
            "LIMIT 1"
        ),
        {"pid": photo_id, "run_id": run_id, "plant": plant_name, "x": x, "y": y, "x2": x2, "y2": y2},
    ).fetchone()
    return result is not None


def ingest_batch(run_id: str, api_key: str, poll: bool, status_only: bool) -> None:
    from anthropic import Anthropic
    from app.database import build_engine, build_session_factory
    from ingest_suggestions import ingest_rows, IngestError

    run_dir = RUNS_DIR / run_id
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        sys.exit(f"error: manifest not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text())
    batch_id = manifest["batch_id"]
    prior = manifest.get("prior", "rich")
    model = manifest.get("model", "claude-sonnet-4-6")

    client = Anthropic(api_key=api_key)

    # Status check
    batch = client.messages.batches.retrieve(batch_id)
    print(f"Batch {batch_id}")
    print(f"  status:   {batch.processing_status}")
    counts = batch.request_counts
    print(f"  requests: {counts.processing} processing / {counts.succeeded} succeeded / {counts.errored} errored")

    if status_only:
        return

    if batch.processing_status != "ended":
        if not poll:
            print("\nBatch not yet complete. Run with --poll to wait, or try again later.")
            return
        print("\nWaiting for batch to complete (checking every 60s)…")
        while batch.processing_status != "ended":
            time.sleep(60)
            batch = client.messages.batches.retrieve(batch_id)
            counts = batch.request_counts
            print(f"  {batch.processing_status}: {counts.processing} processing / {counts.succeeded} succeeded")

    print("\nFetching results…")
    session_factory = build_session_factory(build_engine())

    rows_to_insert = []
    errored = []
    duplicates = 0

    with session_factory() as db:
        for result in client.messages.batches.results(batch_id):
            photo_id = int(result.custom_id)
            prompt_ctx = {"run_id": run_id, "batch_id": batch_id, "prior": prior}

            if result.result.type != "succeeded":
                errored.append((photo_id, result.result.type))
                continue

            msg = result.result.message
            raw_text = next((b.text for b in msg.content if b.type == "text"), "")
            regions = _parse_model_output(raw_text, photo_id)

            if not regions:
                # Treat as a single null region (model produced nothing useful)
                regions = [{"plant": None, "options": [], "confidence": "low",
                            "photo_type": None, "labels": ["parse_error"],
                            "region": None, "observation": "model output unparseable"}]

            for region in regions:
                if not isinstance(region, dict):
                    continue

                plant = region.get("plant")
                options = region.get("options") or []
                confidence = region.get("confidence")
                photo_type = region.get("photo_type")
                labels = region.get("labels") or []
                raw_region = region.get("region")
                observation = region.get("observation")
                suggested_rotation = region.get("suggested_rotation")

                x, y, x2, y2 = _region_to_coords(raw_region)

                # Validate confidence
                if confidence not in ("high", "medium", "low"):
                    confidence = "low"

                # Validate rotation
                if suggested_rotation not in (0, 90, 180, 270):
                    suggested_rotation = None

                # Deduplicate
                if _is_duplicate(db, photo_id, run_id, plant, x, y, x2, y2):
                    duplicates += 1
                    continue

                rows_to_insert.append({
                    "photo_id": photo_id,
                    "model": model,
                    "batch_hint": None,
                    "suggested_plant_name": plant,
                    "suggested_options": options if options else None,
                    "confidence": confidence,
                    "suggested_photo_type": photo_type,
                    "suggested_labels": labels if labels else None,
                    "suggested_rotation": suggested_rotation,
                    "observation": observation,
                    "x": x, "y": y, "x2": x2, "y2": y2,
                    "prompt_context": prompt_ctx,
                    "status": "pending",
                })

        if rows_to_insert:
            try:
                inserted = ingest_rows(rows_to_insert, db)
                db.commit()
                print(f"  inserted {inserted} suggestion(s)")
            except IngestError as e:
                sys.exit(f"error: {e}")
        else:
            print("  0 new rows to insert")

    if duplicates:
        print(f"  skipped {duplicates} duplicate(s)")
    if errored:
        print(f"  [warn] {len(errored)} request(s) errored: {errored[:5]}", file=sys.stderr)

    # Update manifest status
    manifest["status"] = "ingested"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"\nManifest updated → {manifest_path}")

    if manifest.get("prior") == "rich":
        print("\nNext: run agreement gate on flagged rows:")
        print(f"  python scripts/agreement_gate.py --run-id {run_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-id", required=True, metavar="ID")
    parser.add_argument("--poll", action="store_true", help="Wait for batch to finish")
    parser.add_argument("--status", action="store_true", help="Print batch status and exit")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        sys.exit("error: ANTHROPIC_API_KEY environment variable not set")

    ingest_batch(run_id=args.run_id, api_key=api_key, poll=args.poll, status_only=args.status)


if __name__ == "__main__":
    main()

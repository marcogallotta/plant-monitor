#!/usr/bin/env python3
"""Prepare a tagging run: group unclassified photos into sessions, batch, fetch contact sheets.

Usage:
    python scripts/prepare_tagging_run.py [options]

Options:
    --batch-size N       Photos per batch, 1–25 (default: 12)
    --gap-minutes M      Session boundary gap in minutes (default: 15)
    --ref-sheet          Build a confusable-only reference sheet (from Appendix A examples)
    --run-id ID          Run ID (default: YYYYMMDD_HHMMSS)
    --backend-url URL    Backend URL (default: http://localhost:<BACKEND_PORT>)
    --limit N            Only prepare the first N unclassified photos (for calibration)
    --cell-size PX       Contact sheet cell size in pixels, 64–512 (default: 256)
    --include-pending    Include photos that already have a pending suggestion
    --dry-run            Print the batching plan without writing files

Writes to data/tagging-runs/<run_id>/:
    manifest.json         — batch list with status (prepared|ingested|reviewed)
    batch_NNN_sheet.jpg   — contact sheet JPEG for batch NNN
    batch_NNN_prompt.md   — classification prompt for a Claude Code session
    ref_sheet.jpg         — confusable reference sheet (if --ref-sheet)

Reads ASSISTANT_API_TOKEN from the environment; BACKEND_PORT sets the default port.

WARNING — ref sheet coverage gap:
    The Appendix A pool lacks clean single-subject examples for the other half of several
    confusable pairs: Moroccan mint, spearmint, Welsh onion, garlic chives, sorrel, lemongrass.
    Those species appear only in multi-species shots. --ref-sheet is still useful for the pairs
    that ARE covered (peppermint, rau ram, chilli/basil, chives, parsley/cilantro), but curate
    clean crops for the missing halves before relying on the ref sheet for mint/allium/sorrel
    disambiguation.
"""

import argparse
import base64
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

# Confusable reference examples from Appendix A (confirmed by calibration rounds).
# Only covers ONE SIDE of several pairs — see module docstring for the gap.
_CONFUSABLE_FILENAMES = [
    "19af7b97567d47f8bf32f2a57db45334.jpg",  # peppermint (stressed/propagating; NO Moroccan mint / spearmint)
    "7236f3ff21474d17be7ab0e287f728a5.jpg",  # rau ram, sprawling/stressed (NO sorrel)
    "db60aae6b3e6418f99c107c3bf2bc039.jpg",  # rau ram, severely wilted (NO lemongrass)
    "b2d470329a6f43c9b3f78bd3a5e47837.jpg",  # chilli seedling (≠ basil)
    "291ff4b9585540eab4f55c00347d02ca.jpg",  # Thai basil seedlings
    "457790d2c20d4d2090dbf1a87242dcf0.jpg",  # genovese basil seedling
    "892b874e1bac4f25821c8f744ee3dd9e.jpg",  # chives clump (NO Welsh onion / garlic chives)
    "9b523deb3f3b46db9ecbb8b25916e713.jpg",  # parsley/cilantro seedlings (hard binary)
]

_PROMPT_TEMPLATE = """\
# Batch {batch_num} of {total_batches} — {session_date} ({n_photos} photos)

Run: `{run_id}`  Batch ID: `{batch_id}`

## Session context

Photos captured: {captured_range}
Batch photo IDs (capture order): {photo_ids_inline}

## Timestamps

{timestamp_table}

## Contact sheet

Attached: `{sheet_filename}` — cells labeled with photo ID, left-to-right top-to-bottom.
{ref_line}

## Task

For each photo in this batch, output a **JSON array** of suggestion objects. One object per
**region** — a multi-plant photo yields multiple rows, one per distinct species/area.

```json
[
  {{
    "photo_id": <int>,
    "model": "claude-sonnet-4-6",
    "run_id": "{run_id}",
    "batch_id": "{batch_id}",
    "batch_hint": "<optional: session context note, e.g. delivery day / repotting session>",
    "suggested_plant_name": "<species name, or null if junk/delete>",
    "suggested_photo_type": "<overview|health_check|closeup|null>",
    "confidence": "<high|medium|low>",
    "suggested_options": ["<option1>", "<option2>"],
    "suggested_labels": ["<label>"],
    "suggested_rotation": <0|90|180|270|null>,
    "observation": "<one-sentence visual note>",
    "question": "<if low confidence and no option set fits, else null>",
    "x": <0.0–1.0|null>, "y": <0.0–1.0|null>,
    "x2": <0.0–1.0|null>, "y2": <0.0–1.0|null>
  }}
]
```

**Classification rules:**
- **Confusables → `suggested_options`**, not a confident single pick. The offered set must bracket the truth.
- **Junk/non-plant shots** (soil tests, process photos, empty pots): emit one row with
  `suggested_plant_name: null, suggested_photo_type: null, suggested_labels: ["delete_candidate"]`.
  The human then hits Delete in the review tab — do NOT use `suggested_photo_type: "delete"`.
- **Zone undercounting** is the top miss — always scan all four frame edges for secondary species.
- **Use capture timestamps + sequence order** to infer plant age/stage (don't rely on pixels alone).
- Mints: **pot = peppermint**, **trough = Moroccan mint**; offer spearmint as 3rd option when uncertain.
- Allium clumps: offer **chives / Welsh onion / garlic chives**.
- Lobed Apiaceae seedlings: offer **parsley / cilantro**.
- Broad oval seedlings: offer **basil / chilli** — resolution won't resolve this; use date/sequence.
- Reddish sprawling stems, poor condition: **rau ram**.

Output **only** the JSON array, no prose before or after.
"""


def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _get(client: httpx.Client, base_url: str, path: str, **params) -> object:
    r = client.get(f"{base_url}{path}", params=params)
    r.raise_for_status()
    return r.json()


def group_into_sessions(photos: list[dict], gap_minutes: int) -> list[list[dict]]:
    """Split a captured_at-sorted photo list into sessions by time gap."""
    if not photos:
        return []
    gap = timedelta(minutes=gap_minutes)
    sessions: list[list[dict]] = []
    current = [photos[0]]
    for photo in photos[1:]:
        if _parse_dt(photo["captured_at"]) - _parse_dt(current[-1]["captured_at"]) > gap:
            sessions.append(current)
            current = [photo]
        else:
            current.append(photo)
    sessions.append(current)
    return sessions


def make_batches(sessions: list[list[dict]], batch_size: int) -> list[list[dict]]:
    """Split sessions into fixed-size batches (batches do not cross session boundaries)."""
    batches: list[list[dict]] = []
    for session in sessions:
        for i in range(0, len(session), batch_size):
            batches.append(session[i : i + batch_size])
    return batches


def fetch_jpeg(client: httpx.Client, base_url: str, photo_ids: list[int], cell_size: int) -> bytes:
    """Call GET /assistant/contact-sheet, return decoded JPEG bytes."""
    data = _get(client, base_url, "/assistant/contact-sheet",
                ids=",".join(str(i) for i in photo_ids), cell_size=cell_size)
    _, b64 = data["image_data_url"].split(",", 1)
    return base64.b64decode(b64)


def resolve_ref_ids(client: httpx.Client, base_url: str) -> list[int]:
    """Look up confusable reference photo IDs by filename. Warns on missing."""
    all_photos = _get(client, base_url, "/assistant/photos")
    by_filename = {p["filename"]: p["id"] for p in all_photos}
    found, missing = [], []
    for fn in _CONFUSABLE_FILENAMES:
        if fn in by_filename:
            found.append(by_filename[fn])
        else:
            missing.append(fn)
    if missing:
        print(f"  [ref] {len(missing)} confusable example(s) not found in DB (skipped): {missing}",
              file=sys.stderr)
    return found


def _timestamp_table(batch: list[dict]) -> str:
    lines = ["| Photo ID | Captured at (UTC) |", "|----------|-------------------|"]
    for p in batch:
        dt = _parse_dt(p["captured_at"]).strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"| {p['id']} | {dt} |")
    return "\n".join(lines)


def prepare_run(
    *,
    base_url: str,
    token: str,
    dashboard_password: str,
    batch_size: int,
    gap_minutes: int,
    use_ref_sheet: bool,
    run_id: str,
    limit: int | None,
    include_pending: bool,
    dry_run: bool,
    cell_size: int,
    out_dir: Path,
) -> None:
    client = httpx.Client(headers={"Authorization": f"Bearer {token}"}, timeout=60)

    print("Fetching unclassified photos…")
    photos: list[dict] = _get(client, base_url, "/assistant/unclassified")
    photos.sort(key=lambda p: p["captured_at"])

    if not include_pending:
        if dashboard_password:
            dash_client = httpx.Client(auth=("admin", dashboard_password), timeout=60)
            pending = _get(dash_client, base_url, "/suggestions", status="pending")
            pending_ids = {s["photo_id"] for s in pending}
            before = len(photos)
            photos = [p for p in photos if p["id"] not in pending_ids]
            skipped = before - len(photos)
            if skipped:
                print(f"  skipped {skipped} photo(s) already in pending suggestions (--include-pending to override)")
        else:
            print("  WARNING: DASHBOARD_PASSWORD not set — cannot exclude photos with pending suggestions.",
                  file=sys.stderr)
            print("  Set DASHBOARD_PASSWORD or pass --include-pending to suppress this warning.", file=sys.stderr)

    if limit is not None:
        photos = photos[:limit]
    print(f"  {len(photos)} photo(s) to process")

    if not photos:
        print("Nothing to prepare.")
        return

    sessions = group_into_sessions(photos, gap_minutes)
    batches = make_batches(sessions, batch_size)
    print(f"  → {len(sessions)} session(s), {len(batches)} batch(es) at size {batch_size}")

    if dry_run:
        print()
        for i, batch in enumerate(batches, 1):
            ids = [p["id"] for p in batch]
            dt = _parse_dt(batch[0]["captured_at"]).strftime("%Y-%m-%d %H:%M")
            print(f"  batch_{i:03d}: {len(batch):2d} photos  {dt}  ids={ids}")
        return

    out_dir.mkdir(parents=True, exist_ok=True)

    # Build reference sheet once (shared across all batches)
    ref_sheet_name: str | None = None
    if use_ref_sheet:
        print("Building confusable reference sheet…")
        ref_ids = resolve_ref_ids(client, base_url)
        if ref_ids:
            jpeg = fetch_jpeg(client, base_url, ref_ids[:25], cell_size)
            (out_dir / "ref_sheet.jpg").write_bytes(jpeg)
            ref_sheet_name = "ref_sheet.jpg"
            print(f"  ref_sheet.jpg  ({len(ref_ids)} example(s))")
            print("  NOTE: ref sheet has coverage gaps — see script docstring before trusting mint/allium/sorrel disambiguation")
        else:
            print("  No confusable reference photos found in DB — skipping ref sheet")

    manifest_batches: list[dict] = []

    for i, batch in enumerate(batches, 1):
        batch_id = f"batch_{i:03d}"
        photo_ids = [p["id"] for p in batch]

        print(f"  {batch_id}: {len(batch)} photos… ", end="", flush=True)
        jpeg = fetch_jpeg(client, base_url, photo_ids, cell_size)
        sheet_name = f"{batch_id}_sheet.jpg"
        (out_dir / sheet_name).write_bytes(jpeg)

        first_dt = _parse_dt(batch[0]["captured_at"])
        last_dt = _parse_dt(batch[-1]["captured_at"])
        session_date = first_dt.strftime("%Y-%m-%d")
        if first_dt.date() == last_dt.date():
            captured_range = f"{first_dt.strftime('%H:%M')}–{last_dt.strftime('%H:%M')} UTC on {session_date}"
        else:
            captured_range = f"{first_dt.isoformat()} – {last_dt.isoformat()}"

        ref_line = (
            f"Attached: `{ref_sheet_name}` — confusable reference examples."
            if ref_sheet_name
            else "(no reference sheet for this run)"
        )

        prompt = _PROMPT_TEMPLATE.format(
            batch_num=i,
            total_batches=len(batches),
            session_date=session_date,
            n_photos=len(batch),
            captured_range=captured_range,
            photo_ids_inline=", ".join(str(pid) for pid in photo_ids),
            timestamp_table=_timestamp_table(batch),
            sheet_filename=sheet_name,
            ref_line=ref_line,
            run_id=run_id,
            batch_id=batch_id,
        )
        prompt_name = f"{batch_id}_prompt.md"
        (out_dir / prompt_name).write_text(prompt)

        manifest_batches.append({
            "batch_id": batch_id,
            "status": "prepared",
            "photo_ids": photo_ids,
            "session_date": session_date,
            "captured_range": [batch[0]["captured_at"], batch[-1]["captured_at"]],
            "sheet_path": sheet_name,
            "prompt_path": prompt_name,
        })
        print("done")

    manifest = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "batch_size": batch_size,
        "gap_minutes": gap_minutes,
        "cell_size": cell_size,
        "total_photos": len(photos),
        "total_batches": len(batches),
        "ref_sheet": ref_sheet_name is not None,
        "ref_sheet_path": ref_sheet_name,
        "batches": manifest_batches,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    print(f"\nRun prepared → {out_dir}/")
    print(f"  manifest: manifest.json")
    print(f"  {len(batches)} prompt file(s): batch_NNN_prompt.md")
    if ref_sheet_name:
        print(f"  reference sheet: {ref_sheet_name}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--batch-size", type=int, default=12, metavar="N",
                        help="Photos per batch, 1–25 (default: 12)")
    parser.add_argument("--gap-minutes", type=int, default=15, metavar="M",
                        help="Session gap in minutes (default: 15)")
    parser.add_argument("--ref-sheet", action="store_true",
                        help="Build a confusable-only reference sheet from Appendix A examples")
    parser.add_argument("--run-id", metavar="ID",
                        help="Run ID slug (default: YYYYMMDD_HHMMSS)")
    parser.add_argument("--backend-url", metavar="URL",
                        help="Backend base URL (default: http://localhost:<BACKEND_PORT>)")
    parser.add_argument("--limit", type=int, metavar="N",
                        help="Only prepare the first N unclassified photos")
    parser.add_argument("--cell-size", type=int, default=256, metavar="PX",
                        help="Contact sheet cell size in pixels, 64–512 (default: 256)")
    parser.add_argument("--include-pending", action="store_true",
                        help="Include photos that already have a pending suggestion (default: skip them)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print batching plan without writing files")
    args = parser.parse_args()

    errors = []
    if not (1 <= args.batch_size <= 25):
        errors.append("--batch-size must be 1–25")
    if not (64 <= args.cell_size <= 512):
        errors.append("--cell-size must be 64–512")
    if args.limit is not None and args.limit < 1:
        errors.append("--limit must be >= 1")
    if errors:
        sys.exit("error: " + "; ".join(errors))

    token = os.environ.get("ASSISTANT_API_TOKEN", "")
    if not token:
        sys.exit("error: ASSISTANT_API_TOKEN environment variable not set")

    port = os.environ.get("BACKEND_PORT", "8000")
    base_url = (args.backend_url or f"http://localhost:{port}").rstrip("/")
    dashboard_password = os.environ.get("DASHBOARD_PASSWORD", "")

    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path("data/tagging-runs") / run_id

    if out_dir.exists() and not args.dry_run:
        sys.exit(f"error: run directory already exists: {out_dir}  (pass --run-id to use a different ID)")

    prepare_run(
        base_url=base_url,
        token=token,
        dashboard_password=dashboard_password,
        batch_size=args.batch_size,
        gap_minutes=args.gap_minutes,
        use_ref_sheet=args.ref_sheet,
        run_id=run_id,
        limit=args.limit,
        include_pending=args.include_pending,
        dry_run=args.dry_run,
        cell_size=args.cell_size,
        out_dir=out_dir,
    )


if __name__ == "__main__":
    main()

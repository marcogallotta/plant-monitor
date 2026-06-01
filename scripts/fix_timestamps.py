#!/usr/bin/env python3
"""Scan all photos, read EXIF DateTimeOriginal, and fix captured_at where it differs.

Usage:
    python scripts/fix_timestamps.py [--apply]

Without --apply, runs as a dry run and prints what would change.
"""

import sys
from pathlib import Path
from datetime import timezone

SCRIPTS_DIR = Path(__file__).parent
REPO_ROOT = SCRIPTS_DIR.parent
PHOTOS_DIR = REPO_ROOT / "data" / "photos"

for _p in (REPO_ROOT / "backend", REPO_ROOT):
    if (_p / "app").is_dir():
        sys.path.insert(0, str(_p))
        break

import argparse
from PIL import Image
from PIL.ExifTags import TAGS


def read_exif_captured_at(path: Path):
    """Return a timezone-aware datetime from EXIF DateTimeOriginal, or None."""
    try:
        img = Image.open(path)
        exif = img._getexif()
        if not exif:
            return None

        tag_map = {TAGS.get(k, k): v for k, v in exif.items()}

        dto_raw = tag_map.get("DateTimeOriginal")
        if not dto_raw:
            return None

        offset_raw = tag_map.get("OffsetTimeOriginal") or tag_map.get("OffsetTime")

        from datetime import datetime, timedelta, timezone as tz
        dt = datetime.strptime(dto_raw.strip(), "%Y:%m:%d %H:%M:%S")

        if offset_raw:
            sign = 1 if offset_raw[0] != "-" else -1
            parts = offset_raw.strip("+-").split(":")
            hours = int(parts[0])
            mins = int(parts[1]) if len(parts) > 1 else 0
            offset = tz(timedelta(hours=sign * hours, minutes=sign * mins))
            dt = dt.replace(tzinfo=offset).astimezone(timezone.utc)
        else:
            # No offset — leave as naive, treat as UTC (best we can do)
            dt = dt.replace(tzinfo=timezone.utc)

        return dt
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write changes to DB (default: dry run)")
    args = parser.parse_args()

    from app.database import build_engine, build_session_factory
    from app.models import Photo

    engine = build_engine()
    SessionFactory = build_session_factory(engine)

    mismatch = []
    no_exif = 0
    ok = 0

    with SessionFactory() as db:
        photos = db.query(Photo).order_by(Photo.captured_at).all()
        print(f"Scanning {len(photos)} photos…")

        for photo in photos:
            path = PHOTOS_DIR / photo.filename
            if not path.exists():
                continue

            exif_dt = read_exif_captured_at(path)
            if exif_dt is None:
                no_exif += 1
                continue

            stored = photo.captured_at
            if stored.tzinfo is None:
                from datetime import timezone as tz
                stored = stored.replace(tzinfo=tz.utc)
            else:
                stored = stored.astimezone(timezone.utc)

            diff_seconds = abs((exif_dt - stored).total_seconds())
            if diff_seconds > 60:
                mismatch.append((photo, exif_dt, stored, diff_seconds))
            else:
                ok += 1

        print(f"  OK (within 60s): {ok}")
        print(f"  No EXIF:         {no_exif}")
        print(f"  Mismatch:        {len(mismatch)}")
        print()

        if not mismatch:
            print("Nothing to fix.")
            return

        for photo, exif_dt, stored, diff in sorted(mismatch, key=lambda x: x[0].id):
            print(f"  [{photo.id}] {photo.filename}")
            print(f"    stored:  {stored.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            print(f"    exif:    {exif_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC  (diff {diff/3600:.1f}h)")

        if not args.apply:
            print(f"\nDry run — pass --apply to write {len(mismatch)} fix(es) to the DB.")
            return

        print(f"\nApplying {len(mismatch)} fix(es)…")
        for photo, exif_dt, stored, diff in mismatch:
            photo.captured_at = exif_dt
        db.commit()
        print("Done.")


if __name__ == "__main__":
    main()

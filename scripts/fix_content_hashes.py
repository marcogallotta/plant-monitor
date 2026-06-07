#!/usr/bin/env python3
"""Backfill photos.content_hash for existing rows.

Usage:
    python scripts/fix_content_hashes.py [--apply]

Without --apply, runs as a dry run and prints what would change. Computes the
SHA-256 of each photo's image file and stores it in content_hash so the
content-based dedup (unique index added in migration 0012) applies to historical
rows too. Rows whose file is missing are skipped. If two rows share identical
bytes the hash can only be assigned to one (the unique index forbids the rest);
such collisions are reported and left for manual dedup rather than crashing.
"""

import sys
import hashlib
from collections import defaultdict
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
REPO_ROOT = SCRIPTS_DIR.parent
PHOTOS_DIR = REPO_ROOT / "data" / "photos"

for _p in (REPO_ROOT / "backend", REPO_ROOT):
    if (_p / "app").is_dir():
        sys.path.insert(0, str(_p))
        break

import argparse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write changes to DB (default: dry run)")
    args = parser.parse_args()

    from app.database import build_engine, build_session_factory
    from app.models import Photo

    engine = build_engine()
    SessionFactory = build_session_factory(engine)

    already = 0
    missing = 0
    to_set = []  # (photo, hash)
    collisions = []  # (photo, hash, keeper_id)

    with SessionFactory() as db:
        photos = db.query(Photo).order_by(Photo.id).all()
        print(f"Scanning {len(photos)} photos…")

        # Hashes already claimed — either pre-existing in the DB or assigned
        # earlier in this run — so we never try to set a duplicate.
        claimed = {}  # hash -> photo id
        for p in photos:
            if p.content_hash:
                claimed.setdefault(p.content_hash, p.id)

        for photo in photos:
            if photo.content_hash:
                already += 1
                continue
            path = PHOTOS_DIR / photo.filename
            if not path.exists():
                missing += 1
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest in claimed:
                collisions.append((photo, digest, claimed[digest]))
                continue
            claimed[digest] = photo.id
            to_set.append((photo, digest))

        print(f"  Already hashed: {already}")
        print(f"  Missing file:   {missing}")
        print(f"  To backfill:    {len(to_set)}")
        print(f"  Collisions:     {len(collisions)}  (byte-identical to another row — left alone)")
        print()

        for photo, digest, keeper in collisions:
            print(f"  [collision] photo {photo.id} ({photo.filename}) == photo {keeper}")

        if not to_set:
            print("Nothing to backfill.")
            return

        if not args.apply:
            print(f"Dry run — pass --apply to write {len(to_set)} hash(es) to the DB.")
            return

        print(f"Applying {len(to_set)} hash(es)…")
        for photo, digest in to_set:
            photo.content_hash = digest
        db.commit()
        print("Done.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Compute per-frame tilt/drift stabilization transforms for Pi overhead frames.

The Pi mount drifts (wind-nudged rig), so timelapse/compare wobble. This job
registers every `source='pi'` frame onto a canonical reference and stores the
resulting 2x3 affine on the photo row; the dashboard then warps frames to a
common alignment client-side (see backend/static/stabilize.js).

The actual pipeline (night filter -> chain -> quality gate) lives in
scripts/stabilize_core.py so it can be unit-tested without a DB. This wrapper
just loads the Pi rows, runs it, and writes the results.

cv2 lives only in the laptop venv (not the backend/Pi image), so run offline:

    DATABASE_URL=... .venv/bin/python scripts/compute_stabilization.py [--apply]

Without --apply it is a dry run (prints the plan, writes nothing).
"""
import sys
import re
import argparse
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
REPO_ROOT = SCRIPTS_DIR.parent
PHOTOS_DIR = REPO_ROOT / "data" / "photos"
for _p in (REPO_ROOT / "backend", REPO_ROOT):
    if (_p / "app").is_dir():
        sys.path.insert(0, str(_p))
        break
sys.path.insert(0, str(REPO_ROOT))

import scripts.frame_registration as fr
from scripts.stabilize_core import compute_transforms, needs_recompute

REFERENCE_FRAME = "2026-06-07T130010Z.jpg"
TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{6}Z)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write to DB (default: dry run)")
    ap.add_argument("--reference", default=REFERENCE_FRAME, help="anchor frame filename")
    ap.add_argument("--full", action="store_true",
                    help="recompute every frame (ignore prior); default is incremental")
    args = ap.parse_args()

    from app.database import build_engine, build_session_factory
    from app.models import Photo

    SessionFactory = build_session_factory(build_engine())
    with SessionFactory() as db:
        photos = [p for p in db.query(Photo).filter(Photo.source == "pi")
                  .order_by(Photo.captured_at).all()
                  if TS_RE.search(p.filename) and (PHOTOS_DIR / p.filename).exists()]
        if not photos:
            print("no Pi frames on disk to stabilize")
            return

        # Incremental: reuse settled frames, only (re)compute new / pending /
        # stale ones (stale = produced by a different algorithm/param fingerprint).
        db_prior = {p.filename: {"status": p.stab_status, "matrix": p.stab_matrix,
                                 "version": p.stab_version} for p in photos}
        recs = compute_transforms([PHOTOS_DIR / p.filename for p in photos],
                                  args.reference, prior=None if args.full else db_prior)

        def changed(p, r):
            return args.full or needs_recompute(db_prior[p.filename], r["version"])

        ref_w, ref_h = recs[0]["ref_w"], recs[0]["ref_h"]
        pending = sum(1 for p, r in zip(photos, recs) if changed(p, r))
        print(f"{len(photos)} Pi frames; {pending} to (re)compute; "
              f"anchor={args.reference}  ref {ref_w}x{ref_h}  fp={recs[0]['version']}")

        counts, written = {}, 0
        for p, r in zip(photos, recs):
            counts[r["status"]] = counts.get(r["status"], 0) + 1
            if not changed(p, r):          # reused unchanged -> don't rewrite
                continue
            M = r["matrix"]
            detail = "no transform"
            if M is not None:
                rot, sc, tx, ty = fr.decompose(M)
                detail = f"rot={rot:+5.2f} sc={sc:.3f} t=({tx:+5.0f},{ty:+5.0f})"
            print(f"  {TS_RE.search(p.filename).group(1)}  {r['status']:<11} {detail}")
            written += 1
            if args.apply:
                p.stab_matrix = None if M is None else [float(v) for v in M.reshape(-1)]
                p.stab_ref_w = r["ref_w"] if M is not None else None
                p.stab_ref_h = r["ref_h"] if M is not None else None
                p.stab_status = r["status"]
                p.stab_version = r["version"]

        print("\nsummary:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
        if args.apply:
            db.commit()
            print(f"committed {written} updated frame(s)")
        else:
            print(f"dry run — pass --apply to write ({written} would change)")


if __name__ == "__main__":
    sys.exit(main() or 0)

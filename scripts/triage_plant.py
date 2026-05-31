#!/usr/bin/env python3
"""Generate an HTML triage page for all pending suggestions of a given plant name.

Usage:
    python scripts/triage_plant.py --plant lemongrass [--run-id ab_rich] [--output /tmp/triage.html]

Output defaults to data/tagging-runs/triage_<plant>.html.
Reads ASSISTANT_API_TOKEN and BACKEND_URL (or BACKEND_PORT) from environment.
"""

import argparse
import base64
import os
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
REPO_ROOT = SCRIPTS_DIR.parent
RUNS_DIR = REPO_ROOT / "data" / "tagging-runs"

for _p in (REPO_ROOT / "backend", REPO_ROOT):
    if (_p / "app").is_dir():
        sys.path.insert(0, str(_p))
        break
sys.path.insert(0, str(SCRIPTS_DIR))


def _fetch_thumbnail(base_url: str, token: str, photo_id: int) -> str | None:
    import httpx
    try:
        r = httpx.get(
            f"{base_url}/assistant/photos/{photo_id}/thumbnail",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if r.status_code == 200:
            return base64.b64encode(r.content).decode()
    except Exception as e:
        print(f"  [warn] thumbnail {photo_id}: {e}", file=sys.stderr)
    return None


def _get_suggestions(db, plant: str, run_id: str | None) -> list[dict]:
    from sqlalchemy import text
    run_filter = "AND prompt_context->>'run_id' = :run_id" if run_id else ""
    rows = db.execute(
        text(
            f"SELECT id, photo_id, suggested_plant_name, suggested_options, confidence, "
            f"suggested_photo_type, suggested_labels, observation, x, y, x2, y2, "
            f"prompt_context->>'run_id' AS run_id "
            f"FROM photo_ai_suggestions "
            f"WHERE status = 'pending' "
            f"AND lower(suggested_plant_name) = lower(:plant) "
            f"{run_filter} "
            f"ORDER BY photo_id, id"
        ),
        {"plant": plant, "run_id": run_id} if run_id else {"plant": plant},
    ).fetchall()
    return [dict(r._mapping) for r in rows]


_CSS = """
body{font-family:system-ui,sans-serif;font-size:13px;margin:0;background:#111;color:#ddd}
h1{padding:14px 16px;margin:0;background:#1a1a1a;font-size:15px;border-bottom:1px solid #2a2a2a}
.summary{padding:6px 16px 10px;background:#1a1a1a;color:#888;font-size:12px;border-bottom:1px solid #2a2a2a}
.summary strong{color:#ddd}
.ids-box{margin-top:8px;padding:6px 10px;background:#222;border-radius:4px;font-size:11px;color:#aaa;
  font-family:monospace;max-height:60px;overflow-y:auto;word-break:break-all}
.bar{padding:8px 16px;background:#1a1a1a;border-bottom:1px solid #333;display:flex;gap:8px;align-items:center}
.bar button{background:#2a2a2a;border:1px solid #444;color:#ccc;padding:4px 12px;border-radius:4px;
  cursor:pointer;font-size:12px}
.bar button:hover{background:#3a3a3a}
.grid{display:flex;flex-wrap:wrap;gap:12px;padding:16px}
.card{background:#1e1e1e;border-radius:6px;overflow:hidden;width:220px;border:2px solid transparent;
  cursor:pointer;transition:border-color .15s}
.card.selected{border-color:#c8a000}
.card:hover{border-color:#444}
.thumb-wrap{position:relative;width:220px;height:165px;background:#111;flex-shrink:0}
.thumb-wrap img{width:220px;height:165px;object-fit:cover;display:block}
.region-box{position:absolute;border:2px solid #c8a000;box-sizing:border-box;pointer-events:none}
.no-thumb{width:220px;height:165px;display:flex;align-items:center;justify-content:center;color:#444;font-size:11px}
.meta{padding:8px 10px}
.plant{font-weight:600;font-size:14px}
.ch{color:#4caf50;font-size:11px;margin-left:4px}
.cm{color:#ff9800;font-size:11px;margin-left:4px}
.cl{color:#f44336;font-size:11px;margin-left:4px}
.detail{font-size:11px;color:#777;margin-top:3px}
.pid{font-size:10px;color:#444;margin-top:4px}
.sel-count{color:#c8a000;font-weight:600}
"""

_JS = """
let selected = new Set();

function toggle(card, suggId) {
  if (selected.has(suggId)) {
    selected.delete(suggId);
    card.classList.remove('selected');
  } else {
    selected.add(suggId);
    card.classList.add('selected');
  }
  updateBar();
}

function selectAll() {
  document.querySelectorAll('.card').forEach(c => {
    c.classList.add('selected');
    selected.add(parseInt(c.dataset.id));
  });
  updateBar();
}

function clearSel() {
  document.querySelectorAll('.card').forEach(c => c.classList.remove('selected'));
  selected.clear();
  updateBar();
}

function updateBar() {
  document.getElementById('sel-count').textContent = selected.size;
  document.getElementById('sel-ids').textContent =
    selected.size ? [...selected].sort((a,b)=>a-b).join(', ') : '(none)';
}
"""


def _render_card(s: dict, b64: str | None) -> str:
    sid = s["id"]
    pid = s["photo_id"]
    plant = s["suggested_plant_name"] or "null"
    conf = s["confidence"] or "low"
    conf_cls = {"high": "ch", "medium": "cm", "low": "cl"}.get(conf, "cl")
    opts = s["suggested_options"] or []
    obs = s["observation"] or ""
    run_id = s.get("run_id") or ""

    if b64:
        thumb = f'<img src="data:image/jpeg;base64,{b64}" alt="">'
    else:
        thumb = '<div class="no-thumb">no image</div>'

    region_box = ""
    x, y, x2, y2 = s.get("x"), s.get("y"), s.get("x2"), s.get("y2")
    if x is not None and x2 is not None:
        left = x * 100
        top = y * 100
        width = (x2 - x) * 100
        height = (y2 - y) * 100
        region_box = (f'<div class="region-box" style="'
                      f'left:{left:.1f}%;top:{top:.1f}%;'
                      f'width:{width:.1f}%;height:{height:.1f}%"></div>')

    detail_parts = []
    if opts:
        detail_parts.append(f'opts: {", ".join(opts)}')
    if obs:
        detail_parts.append(obs)
    if run_id:
        detail_parts.append(run_id)
    detail_html = "".join(f'<div class="detail">{p}</div>' for p in detail_parts)

    return f"""<div class="card" data-id="{sid}" onclick="toggle(this,{sid})">
  <div class="thumb-wrap">{thumb}{region_box}</div>
  <div class="meta">
    <span class="plant">{plant}</span><span class="{conf_cls}">{conf}</span>
    {detail_html}
    <div class="pid">sugg #{sid} · photo #{pid}</div>
  </div>
</div>"""


def generate(plant: str, run_id: str | None, base_url: str, token: str, output: Path) -> None:
    from app.database import build_engine, build_session_factory

    with build_session_factory(build_engine())() as db:
        suggestions = _get_suggestions(db, plant, run_id)

    if not suggestions:
        print(f"No pending suggestions found for plant={plant!r}" +
              (f" run_id={run_id!r}" if run_id else ""))
        return

    photo_ids = sorted({s["photo_id"] for s in suggestions})
    print(f"  {len(suggestions)} suggestion(s) across {len(photo_ids)} photo(s)")

    thumbnails: dict[int, str | None] = {}
    for i, pid in enumerate(photo_ids, 1):
        if i % 10 == 0 or i == len(photo_ids):
            print(f"  thumbnails {i}/{len(photo_ids)}")
        thumbnails[pid] = _fetch_thumbnail(base_url, token, pid)

    all_ids = [s["id"] for s in suggestions]
    cards = "".join(_render_card(s, thumbnails.get(s["photo_id"])) for s in suggestions)
    run_label = f" · run: {run_id}" if run_id else ""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8">
<title>Triage: {plant}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>Triage: <strong>{plant}</strong>{run_label}</h1>
<div class="summary">
  <strong>{len(suggestions)}</strong> pending suggestion(s) across
  <strong>{len(photo_ids)}</strong> photo(s) &nbsp;·&nbsp;
  Click cards to select · use IDs below to bulk-reassign<br>
  <div class="ids-box">All IDs: {", ".join(str(i) for i in all_ids)}</div>
</div>
<div class="bar">
  <button onclick="selectAll()">Select all</button>
  <button onclick="clearSel()">Clear</button>
  &nbsp; <span class="sel-count" id="sel-count">0</span> selected &nbsp;
  IDs: <span id="sel-ids" style="font-family:monospace;font-size:11px;color:#aaa">(none)</span>
</div>
<div class="grid">{cards}</div>
<script>{_JS}</script>
</body></html>"""

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    print(f"\n→ {output}  ({output.stat().st_size // 1024} KB)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--plant", required=True, metavar="NAME", help="Plant name to triage (case-insensitive)")
    parser.add_argument("--run-id", metavar="RUN_ID", help="Limit to a specific run ID")
    parser.add_argument("--output", metavar="PATH", help="Output HTML path")
    args = parser.parse_args()

    token = os.environ.get("ASSISTANT_API_TOKEN", "")
    if not token:
        sys.exit("error: ASSISTANT_API_TOKEN not set")

    base_url = os.environ.get("BACKEND_URL") or \
               f"http://localhost:{os.environ.get('BACKEND_PORT', '8000')}"

    slug = args.plant.lower().replace(" ", "_").replace("'", "")
    output = Path(args.output) if args.output else RUNS_DIR / f"triage_{slug}.html"

    print(f"Triaging '{args.plant}'" + (f" in run {args.run_id}" if args.run_id else "") + "…")
    generate(plant=args.plant, run_id=args.run_id, base_url=base_url, token=token, output=output)


if __name__ == "__main__":
    main()

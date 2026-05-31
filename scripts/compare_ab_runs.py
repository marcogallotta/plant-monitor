#!/usr/bin/env python3
"""Generate a side-by-side HTML comparison of two A/B tagging runs.

Usage:
    python scripts/compare_ab_runs.py --rich ab_rich --thin ab_thin
    python scripts/compare_ab_runs.py --rich ab_rich --thin ab_thin --output /tmp/compare.html

Output defaults to data/tagging-runs/ab_compare.html.
Reads ASSISTANT_API_TOKEN and BACKEND_PORT from environment.
"""

import argparse
import base64
import json
import os
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
REPO_ROOT = SCRIPTS_DIR.parent
RUNS_DIR = REPO_ROOT / "data" / "tagging-runs"

sys.path.insert(0, str(REPO_ROOT / "backend"))


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


def _get_suggestions(db, run_id: str) -> dict[int, list[dict]]:
    from sqlalchemy import text
    rows = db.execute(
        text(
            "SELECT photo_id, suggested_plant_name, suggested_options, confidence, "
            "suggested_photo_type, suggested_labels, observation, x, y, x2, y2 "
            "FROM photo_ai_suggestions "
            "WHERE prompt_context->>'run_id' = :run_id "
            "ORDER BY photo_id, id"
        ),
        {"run_id": run_id},
    ).fetchall()
    result: dict[int, list[dict]] = {}
    for row in rows:
        pid = row.photo_id
        result.setdefault(pid, []).append(dict(row._mapping))
    return result


def _plants_differ(rich_rows: list[dict], thin_rows: list[dict]) -> bool:
    return {r.get("suggested_plant_name") for r in rich_rows} != \
           {r.get("suggested_plant_name") for r in thin_rows}


def _render_region(s: dict) -> str:
    plant = s.get("suggested_plant_name") or "<em>null</em>"
    confidence = s.get("confidence", "low")
    options = s.get("suggested_options") or []
    observation = s.get("observation") or ""
    photo_type = s.get("suggested_photo_type") or ""
    labels = s.get("suggested_labels") or []
    x, y, x2, y2 = s.get("x"), s.get("y"), s.get("x2"), s.get("y2")

    conf_class = {"high": "ch", "medium": "cm", "low": "cl"}.get(confidence, "cl")
    region_str = f' <span class="reg">[{x:.2f},{y:.2f}→{x2:.2f},{y2:.2f}]</span>' \
                 if x is not None else ""

    parts = [f'<span class="plant">{plant}</span> <span class="{conf_class}">{confidence}</span>{region_str}']
    if options:
        parts.append(f'<div class="meta">opts: {", ".join(options)}</div>')
    if observation:
        parts.append(f'<div class="meta">{observation}</div>')
    if photo_type:
        parts.append(f'<div class="meta">{photo_type}</div>')
    if labels:
        parts.append(f'<div class="meta">labels: {", ".join(labels)}</div>')
    return '<div class="region">' + "".join(parts) + "</div>"


_CSS = """
body{font-family:system-ui,sans-serif;font-size:13px;margin:0;background:#111;color:#ddd}
h1{padding:14px 16px;margin:0;background:#1a1a1a;font-size:15px;border-bottom:1px solid #2a2a2a}
.summary{padding:6px 16px;background:#1a1a1a;color:#888;font-size:12px;border-bottom:1px solid #2a2a2a}
.bar{padding:8px 16px;background:#1a1a1a;border-bottom:1px solid #333}
.bar button{background:#2a2a2a;border:1px solid #444;color:#ccc;padding:4px 12px;border-radius:4px;cursor:pointer;margin-right:6px;font-size:12px}
.bar button.on{background:#9a7100;border-color:#9a7100;color:#fff}
table{width:100%;border-collapse:collapse}
thead th{background:#1e1e1e;padding:8px;text-align:left;border-bottom:2px solid #333;position:sticky;top:0;z-index:1}
td{padding:8px;vertical-align:top;border-bottom:1px solid #222}
.ct{width:170px}
.cc,.cd{width:calc(50% - 85px)}
img.thumb{width:160px;height:120px;object-fit:cover;border-radius:4px;display:block}
.pid{color:#555;font-size:11px;margin-top:3px}
tr.diff{background:#18130000}
tr.diff td{background:#1a1300}
.region{margin-bottom:6px;padding:5px 8px;background:#222;border-radius:4px;border-left:3px solid #444}
tr.diff .region{border-left-color:#9a7100}
.plant{font-weight:600;font-size:14px}
.ch{color:#4caf50;font-size:11px;margin-left:4px}
.cm{color:#ff9800;font-size:11px;margin-left:4px}
.cl{color:#f44336;font-size:11px;margin-left:4px}
.meta{font-size:11px;color:#777;margin-top:2px}
.reg{font-size:10px;color:#555}
.no-thumb{width:160px;height:120px;background:#1a1a1a;border-radius:4px;display:flex;align-items:center;justify-content:center;color:#444;font-size:11px}
"""

_JS = """
function filter(mode){
  document.querySelectorAll('tbody tr').forEach(r=>{
    r.style.display=(mode==='all'||r.classList.contains('diff'))?'':'none';
  });
  document.querySelectorAll('.bar button').forEach(b=>b.classList.remove('on'));
  document.getElementById('btn-'+mode).classList.add('on');
}
"""


def generate(rich_run_id: str, thin_run_id: str, base_url: str, token: str, output: Path) -> None:
    from app.database import build_engine, build_session_factory

    with build_session_factory(build_engine())() as db:
        rich = _get_suggestions(db, rich_run_id)
        thin = _get_suggestions(db, thin_run_id)

    common = sorted(set(rich) & set(thin))
    only_rich = sorted(set(rich) - set(thin))
    only_thin = sorted(set(thin) - set(rich))
    print(f"  {len(common)} photos in both, {len(only_rich)} rich-only, {len(only_thin)} thin-only")

    rows = []
    ndiff = 0
    for i, pid in enumerate(common, 1):
        if i % 10 == 0 or i == len(common):
            print(f"  thumbnails {i}/{len(common)}")
        b64 = _fetch_thumbnail(base_url, token, pid)
        thumb = f'<img class="thumb" src="data:image/jpeg;base64,{b64}">' if b64 \
                else '<div class="no-thumb">no image</div>'
        r_rows, t_rows = rich[pid], thin[pid]
        diff = _plants_differ(r_rows, t_rows)
        if diff:
            ndiff += 1
        cls = "diff" if diff else ""
        rows.append(f"""<tr class="{cls}">
  <td class="ct">{thumb}<div class="pid">#{pid}</div></td>
  <td class="cc">{"".join(_render_region(s) for s in r_rows)}</td>
  <td class="cd">{"".join(_render_region(s) for s in t_rows)}</td>
</tr>""")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8">
<title>A/B: {rich_run_id} vs {thin_run_id}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>A/B &nbsp;·&nbsp; <strong>{rich_run_id}</strong> (rich) vs <strong>{thin_run_id}</strong> (thin)</h1>
<div class="summary">
  {len(common)} photos &nbsp;·&nbsp; <span style="color:#c8a000">{ndiff} plant-name differences</span>
  &nbsp;·&nbsp; {len(only_rich)} rich-only &nbsp;·&nbsp; {len(only_thin)} thin-only
</div>
<div class="bar">
  <button id="btn-all" class="on" onclick="filter('all')">All ({len(common)})</button>
  <button id="btn-diff" onclick="filter('diff')">Differences only ({ndiff})</button>
</div>
<table>
<thead><tr>
  <th>Photo</th>
  <th>Rich prior</th>
  <th>Thin prior</th>
</tr></thead>
<tbody>
{"".join(rows)}
</tbody>
</table>
<script>{_JS}</script>
</body></html>"""

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    print(f"\n→ {output}  ({output.stat().st_size // 1024} KB)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rich", required=True, metavar="RUN_ID")
    parser.add_argument("--thin", required=True, metavar="RUN_ID")
    parser.add_argument("--output", metavar="PATH")
    args = parser.parse_args()

    token = os.environ.get("ASSISTANT_API_TOKEN", "")
    if not token:
        sys.exit("error: ASSISTANT_API_TOKEN not set")

    port = os.environ.get("BACKEND_PORT", "8000")
    base_url = f"http://localhost:{port}"
    output = Path(args.output) if args.output else RUNS_DIR / "ab_compare.html"

    print(f"Comparing {args.rich} (rich) vs {args.thin} (thin)…")
    generate(rich_run_id=args.rich, thin_run_id=args.thin, base_url=base_url, token=token, output=output)


if __name__ == "__main__":
    main()

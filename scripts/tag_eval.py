#!/usr/bin/env python3
"""Phase-3 non-Pi tagging — priors-first tagger + held-out accuracy check (roadmap Track B).

Validated 2026-06-08: the rich (priors-first) prompt beat a thin closed-set-only
baseline decisively (kind-level 16 vs 13 of 17, overconfident-wrong 3 -> 0, fixed
the lemongrass<->garlic-chives swap), so the thin arm is dropped. This now runs
ONE prompt and scores it against ground truth (existing single-unit photo links).

The tagger resolves identity only as far as it is confident — a 3-tier ladder,
falling back coarse rather than guessing (see vision-tagging.md "closed set policy"):

  SPECIFIC  — distinctive plants -> the exact unit.
  KIND      — confusable groups -> the GROUP (variety is pot/position, not pixels),
              upgraded to a variety only on a hard feature.
  SEEDLINGS — seedling-stage -> "SEEDLINGS", + a kind ("chilli seedlings") only if
              highly confident; never guess a seedling's species.

    docker compose run --rm backend python scripts/tag_eval.py            # real (API)
    docker compose run --rm backend python scripts/tag_eval.py --dry      # build only
"""
import os, sys, io, json, base64, random, argparse, re
from collections import defaultdict
sys.path.insert(0, "/app")
from sqlalchemy import select
from app.database import _get_session_factory
from app.models import Photo, PhotoGrowingUnit, GrowingUnit
from PIL import Image

MODEL = os.environ.get("TAGGING_MODEL", "claude-sonnet-4-6")
MAX_PX = 1024
PLANTS_DATA = "/app/docs/plants-data.md"

# --- the agreed taxonomy (vision-tagging.md owns the policy) ----------------
DISTINCTIVE = ["Dill", "Rocket", "Rosemary", "Sage", "Sorrel", "French tarragon",
               "Lemongrass", "Rau ram"]
GROUPS = {  # group -> (members, hint shown to the model)
    "basil": (["Genovese basil", "Thai basil", "Thai basil vendita"],
              "variety by pot; upgrade to Thai basil vendita ONLY on purple flower spikes"),
    "mint": (["Peppermint", "Moroccan Mint"], "Spearmint is dead/retired — never the answer"),
    "chive-allium": (["Chives", "Garlic chives", "Welsh onion"],
                     "garlic chives = mature/thin flat blades; welsh onion = young/seedlings; chives = finest wisps"),
    "parsley/cilantro": (["Parsley", "Cilantro", "Cilantro root"], "variety by pot"),
    "thyme": (["Thyme", "Lemon Thyme"], "not separable by leaf — needs scent"),
    "chilli": (["Hangijiao 4", "Hangijiao 7", "Birdseye Italico"], "visually identical — variety/unit is position-only"),
}
SEEDLING_KIND_GROUP = {"chilli seedlings": "chilli", "basil seedlings": "basil",
                       "umbellifer seedlings": "parsley/cilantro", "allium seedlings": "chive-allium",
                       "mint seedlings": "mint"}
SEEDLING_STAGE_UNITS = {"Welsh onion"}   # units whose photos are seedling-stage (plants-data status)

_MEMBER2GROUP = {m.lower(): g for g, (members, _) in GROUPS.items() for m in members}


def group_of(label):
    """Resolution key for scoring: group name (grouped/sibling/seedling-kind),
    the unit itself (distinctive), or SEEDLINGS (bare)."""
    n = (label or "").strip().lower()
    if n in ("seedlings", "seedling"):
        return "SEEDLINGS"
    if n in SEEDLING_KIND_GROUP:
        return SEEDLING_KIND_GROUP[n]
    if n in GROUPS:
        return n
    if n in _MEMBER2GROUP:
        return _MEMBER2GROUP[n]
    return n   # distinctive unit (or unknown / chilli variants)


def taxonomy_text():
    lines = ["DISTINCTIVE (answer the exact unit): " + ", ".join(DISTINCTIVE), "",
             "GROUPS (answer the GROUP unless a hard feature/position pins the variety):"]
    for g, (members, hint) in GROUPS.items():
        lines.append(f"  - {g}  [{', '.join(members)}] — {hint}")
    lines.append("")
    lines.append("SEEDLING kinds (only if highly confident, else bare SEEDLINGS): "
                 + ", ".join(SEEDLING_KIND_GROUP))
    return "\n".join(lines)


def _plants_data():
    with open(PLANTS_DATA) as f:
        return f.read()


# --- sampling (curated confusable-heavy strata) ----------------------------
STRATA = {
    "Thai basil": 2, "Genovese basil": 2, "Lemongrass": 2, "Rau ram": 2,
    "Welsh onion": 1, "Garlic chives": 1, "Moroccan Mint": 1, "Peppermint": 1,
    "Lemon Thyme": 1, "Parsley": 1, "Dill": 1, "Rosemary": 1, "French tarragon": 1,
}


def _single_unit_phone(db):
    rows = db.execute(
        select(Photo.storage_path, Photo.captured_at, GrowingUnit.name)
        .join(PhotoGrowingUnit, PhotoGrowingUnit.photo_id == Photo.id)
        .join(GrowingUnit, GrowingUnit.id == PhotoGrowingUnit.growing_unit_id)
        .where(Photo.source == "phone")).all()
    by_path = defaultdict(list)
    for path, ts, name in rows:
        by_path[(path, ts)].append(name)
    return [(p, ts, names[0]) for (p, ts), names in by_path.items() if len(names) == 1]


def sample(db, n, curated=True):
    pool = _single_unit_phone(db)
    if not curated:
        random.shuffle(pool); return pool[:n]
    by_unit = defaultdict(list)
    for rec in pool:
        by_unit[rec[2]].append(rec)
    out = []
    for unit, cap in STRATA.items():
        recs = by_unit.get(unit, []); random.shuffle(recs); out.extend(recs[:cap])
    random.shuffle(out)
    return out


def encode(path):
    im = Image.open(path).convert("RGB"); im.thumbnail((MAX_PX, MAX_PX))
    buf = io.BytesIO(); im.save(buf, format="JPEG", quality=85)
    return base64.standard_b64encode(buf.getvalue()).decode()


def prompt(date, plants_md):
    return (
        f"Identify the plant in this photo. RESOLVE ONLY AS FAR AS YOU ARE CONFIDENT — "
        f"fall back to a coarser label rather than guess; coarse-but-right beats precise-but-wrong.\n\n"
        f"{taxonomy_text()}\n\n"
        f"PHOTO CAPTURED: {date}.\n\n"
        f"USE THESE PRIORS FIRST, before leaf shape — identity is usually decided by stage, pot, "
        f"position, count, and date:\n\n{plants_md}\n\n"
        f"Rules: never a confident single on a within-group variety unless a hard feature shows. A unit "
        f"marked dead/retired, or at a different growth stage on the photo date, can be ruled out. For "
        f"seedlings answer SEEDLINGS (add a kind only if highly confident).\n\n"
        f'Output ONLY JSON: {{"label": "<distinctive unit | group | SEEDLINGS | \'<kind> seedlings\'>", '
        f'"options": ["<other candidates>"], "confidence": "high|medium|low"}}.')


def call(client, b64, text):
    msg = client.messages.create(model=MODEL, max_tokens=400, messages=[{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
        {"type": "text", "text": text}]}])
    out = "".join(b.text for b in msg.content if b.type == "text")
    m = re.search(r"\{.*\}", out, re.S)
    try:
        return json.loads(m.group(0)) if m else {"label": "UNKNOWN", "options": [], "confidence": "low"}
    except json.JSONDecodeError:
        return {"label": "PARSE_FAIL", "options": [], "confidence": "low"}


def verdict(true, pred):
    """-> (kind_ok, specific_ok, in_options)."""
    tk = group_of(true)
    pk = group_of(pred.get("label", ""))
    specific = pred.get("label", "").strip().lower() == true.lower()
    if pk == "SEEDLINGS":
        kind = true in SEEDLING_STAGE_UNITS
    else:
        kind = pk == tk
    in_opts = any(group_of(o) == tk for o in pred.get("options", []))
    return kind, specific, in_opts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n", type=int, nargs="?", default=8, help="cap (random mode only)")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--random", action="store_true")
    ap.add_argument("--seed", type=int)
    a = ap.parse_args()
    if a.seed is not None:
        random.seed(a.seed)
    Session = _get_session_factory()
    with Session() as db:
        samp = sample(db, a.n, curated=not a.random)
    plants_md = _plants_data()
    print(f"{len(samp)} held-out photos; plants-data {len(plants_md)} chars; model={MODEL}"
          f"{'  [DRY]' if a.dry else ''}")
    if a.dry:
        p, ts, true = samp[0]
        print(f"\n--- {os.path.basename(p)}  true={true}  date={str(ts)[:10]} ---\n")
        print(prompt(str(ts)[:10], plants_md)[:1100] + " ...")
        return

    from anthropic import Anthropic
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    nk = ns = no = nx = 0
    for p, ts, true in samp:
        pred = call(client, encode(p), prompt(str(ts)[:10], plants_md))
        kind, spec, inopt = verdict(true, pred)
        conf = pred.get("confidence", "?")
        ns += spec; nk += kind; no += (inopt and not kind)
        bad = not kind and conf == "high"
        nx += bad
        mark = "SPEC" if spec else ("kind" if kind else ("opt" if inopt else "MISS"))
        print(f"  {true:<18} -> {pred.get('label',''):<20}({conf[:1]}) [{mark}]"
              f"{('  opts='+','.join(pred.get('options',[]))) if pred.get('options') else ''}"
              f"{'  <<OVERCONFIDENT' if bad else ''}")
    n = len(samp)
    print(f"\nkind-correct {nk}/{n}  (of which exact-specific {ns})   "
          f"true-only-in-options {no}   overconfident-wrong {nx}")


if __name__ == "__main__":
    main()

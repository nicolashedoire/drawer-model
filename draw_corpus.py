#!/usr/bin/env python3
"""draw-corpus — la FABRIQUE : pose les graines, raffine chacune via CLIP,
construit le corpus (prompt → programme → score) pour distiller le modèle final.

  python3 draw_corpus.py --baseline          # juste scorer les graines (rapide)
  python3 draw_corpus.py --iters 90          # apprendre tous les sujets
  python3 draw_corpus.py --iters 90 sun star # sous-ensemble
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json

from PIL import Image

from cdp_session import CDPSession
from draw_lab import CANVAS_URL, OUT, warm_up, draw_stroke
from draw_figure import PROGRAMS, op_to_points
import draw_critic
import draw_learn

LEARNED = OUT / "learned"
# sujets du corpus (graines dans draw_seeds + horse/house)
SUBJECTS = ["horse", "house", "sun", "star", "tree", "flower", "fish",
            "sailboat", "cat", "umbrella", "ladder", "car"]


async def render(s, prog):
    await s.eval("window.__clear()")
    for op in prog:
        await draw_stroke(s, op_to_points(op))
    await s.eval("1")
    res = await s.send("Page.captureScreenshot", {"format": "png"})
    return Image.open(io.BytesIO(base64.b64decode(res["data"]))).convert("RGB")


async def baseline(subjects):
    draw_critic._load()
    s = CDPSession(headless=True, width=1040, height=700)
    s.launch_chrome(); await s.connect(); await s.navigate(CANVAS_URL)
    await s.wait_for("window.__ready === true", timeout=12); await warm_up(s)
    print("=== BASELINE des graines (avant apprentissage) ===")
    rows = []
    for name in subjects:
        prog = PROGRAMS.get(name)
        if not prog:
            print(f"  {name:10} (pas de graine)"); continue
        img = await render(s, prog)
        p, ranking, _ = draw_critic.score(img, name)
        top = ranking[0][0]
        mark = "✓" if top == name and p >= 0.5 else ("≈" if top == name else f"→{top}")
        rows.append((name, p, mark))
        print(f"  {name:10} P={p:.2f}  {mark}")
    await s.close()
    ok = sum(1 for _, p, m in rows if m == "✓")
    print(f"\n{ok}/{len(rows)} graines déjà reconnues ; les autres seront tirées vers le haut par l'apprentissage.")


async def build(subjects, iters):
    print(f"=== APPRENTISSAGE du corpus ({len(subjects)} sujets × {iters} pas) ===", flush=True)
    results = {}
    for name in subjects:
        if name not in PROGRAMS:
            continue
        try:
            score = await draw_learn.learn(name, name, iters)
            results[name] = round(score, 3)
        except Exception as exc:
            print(f"  ⚠ {name}: {exc}", flush=True)
    print("\n=== CORPUS CONSTRUIT ===", flush=True)
    for name, sc in sorted(results.items(), key=lambda x: -x[1]):
        print(f"  {name:10} P={sc}", flush=True)
    n_ok = sum(1 for v in results.values() if v >= 0.5)
    print(f"\n{n_ok}/{len(results)} sujets ≥0.50 → corpus dans {LEARNED}", flush=True)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("subjects", nargs="*", default=None)
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--iters", type=int, default=90)
    a = ap.parse_args()
    subjects = a.subjects or SUBJECTS
    if a.baseline:
        await baseline(subjects)
    else:
        await build(subjects, a.iters)


if __name__ == "__main__":
    asyncio.run(main())

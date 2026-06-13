#!/usr/bin/env python3
"""draw-recipe — RECETTE d'illustration : combiner les techniques par couches de valeur.

De la lumière vers l'ombre, on EMPILE les techniques apprises selon le ton :
  clair        → rien (blanc)
  clair-moyen  → stippling blue-noise (Lloyd)
  moyen        → + hachure simple
  sombre       → + hachures croisées
  très sombre  → + 3e direction (triple hachure)
Chaque couche s'ajoute quand le ton dépasse son seuil → un dégradé tonal continu,
construit en combinant stipple + hachures (comme un illustrateur).

  python3 draw_recipe.py --capture
  python3 draw_recipe.py --live
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import math

import numpy as np

from cdp_session import CDPSession
from draw_lab import CANVAS_URL, OUT, warm_up, draw_stroke
from draw_figure import op_to_points
from draw_live import draw_program_live
from draw_shapes import CAT_SIL
from draw_stipple import cat_density, weighted_voronoi_stipple
from draw_hatch_flow import field_and_tone

W, H = 1000, 640


def recipe_ops(n_stipple=1200, hatch_step=7.0, seed=4):
    rng = np.random.default_rng(seed)
    mask, tone = field_and_tone()
    ops = []
    # couche 1 — stippling (Lloyd) dans clair→moyen, fond du dégradé
    dens_light = np.where(tone < 0.56, cat_density(), 0.0)
    pts = weighted_voronoi_stipple(dens_light, n_stipple)
    ops += [{"op": "circle", "c": [float(x), float(y)], "r": 1.5} for x, y in pts]
    # couches 2-4 — hachures empilées selon le ton (simple → croisée → triple)
    layers = [(0.40, 0.6), (0.58, 0.6 + math.pi / 2), (0.74, 0.6 + math.pi / 4)]
    y = 4
    while y < H:
        x = 4
        while x < W:
            iy, ix = int(y), int(x)
            if mask[iy, ix]:
                t = tone[iy, ix]
                for thr, a in layers:
                    if t > thr:
                        L = 6.5
                        jx, jy = rng.uniform(-2, 2), rng.uniform(-2, 2)
                        ops.append({"op": "line",
                                    "a": [x + jx - L / 2 * math.cos(a), y + jy - L / 2 * math.sin(a)],
                                    "b": [x + jx + L / 2 * math.cos(a), y + jy + L / 2 * math.sin(a)]})
            x += hatch_step
        y += hatch_step
    ops.append({"op": "polyline", "pts": [list(p) for p in CAT_SIL], "close": True})
    return ops


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--capture", action="store_true")
    a = ap.parse_args()
    ops = recipe_ops(n_stipple=620 if a.live else 1200, hatch_step=9.0 if a.live else 7.0)
    print(f"· recette multi-couches : {len(ops)} formes (stipple + 3 niveaux de hachures par valeur)", flush=True)

    s = CDPSession(headless=not a.live, width=1040, height=730)
    s.launch_chrome(); await s.connect(); await s.navigate(CANVAS_URL)
    await s.wait_for("window.__ready === true", timeout=12); await warm_up(s)
    if a.live:
        await s.eval("window.__penShow(true)")
        await s.eval("window.__caption('RECETTE : stipple + hachures empilees par couches de valeur')")
        await asyncio.sleep(1.0)
        await draw_program_live(s, ops)
        await asyncio.sleep(15)
    else:
        await s.eval("window.__clear()")
        for op in ops:
            await draw_stroke(s, op_to_points(op))
        await s.eval("1")
        res = await s.send("Page.captureScreenshot", {"format": "png"})
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "recipe_cat.png").write_bytes(base64.b64decode(res["data"]))
        print(f"✓ rendu → {OUT / 'recipe_cat.png'}", flush=True)
    await s.close()


if __name__ == "__main__":
    asyncio.run(main())

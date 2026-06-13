#!/usr/bin/env python3
"""draw-gallery — DÉMO LIVE DE TOUT : toutes les techniques enchaînées.

Une seule fenêtre visible ; chaque technique est calculée (vrai algorithme) puis
tracée en direct, avec sa légende, densité allégée pour rester regardable.

  python3 draw_gallery.py
"""
from __future__ import annotations

import asyncio
import base64
import io
import json

from PIL import Image

from cdp_session import CDPSession
from draw_lab import CANVAS_URL, warm_up
from draw_live import draw_program_live
from draw_shapes import CAT_SIL, generate_lowpoly_shaded
from draw_stipple import cat_density, weighted_voronoi_stipple
from draw_tsp import nn_tour, two_opt
from draw_hatch_flow import hatch_ops
from draw_flow import flow_ops
from draw_recipe import recipe_ops
from draw_photo import xdog_lines, placement, SRC

W, H = 1000, 640


def stipple_g(n):
    pts = weighted_voronoi_stipple(cat_density(), n)
    return [{"op": "circle", "c": [float(x), float(y)], "r": 1.6} for x, y in pts]


def tsp_g(n):
    pts = weighted_voronoi_stipple(cat_density(), n)
    tour = two_opt(nn_tour(pts), pts)
    line = [[float(pts[i, 0]), float(pts[i, 1])] for i in tour]
    return [{"op": "polyline", "pts": line, "close": False},
            {"op": "polyline", "pts": [list(p) for p in CAT_SIL], "close": True}]


GALLERY = [
    ("Low-poly ombre (maille de triangles)", lambda: generate_lowpoly_shaded(CAT_SIL, cell=32), False),
    ("Weighted Voronoi stippling (Lloyd)", lambda: stipple_g(340), False),
    ("Une seule ligne continue (TSP)", lambda: tsp_g(300), False),
    ("Hachures tonales croisees", lambda: hatch_ops(step=12), False),
    ("Lignes de flux (streamlines)", lambda: flow_ops(step=14), False),
    ("Recette : stipple + hachures par valeur", lambda: recipe_ops(n_stipple=320, hatch_step=12), False),
    ("Vraie photo : XDoG trace par-dessus", lambda: xdog_lines(), True),
]


async def show_photo_bg(s):
    x0, y0, nw, nh = placement(640)
    im = Image.open(SRC).convert("RGB").resize((nw, nh))
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=82)
    durl = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    await s.eval("window.__bg(" + json.dumps(durl) + f", 0.5, {x0}, {y0}, {nw}, {nh})")


async def main():
    s = CDPSession(headless=False, width=1040, height=730)
    print("· GALERIE — fenêtre visible", flush=True)
    s.launch_chrome(); await s.connect(); await s.navigate(CANVAS_URL)
    await s.wait_for("window.__ready === true", timeout=12); await warm_up(s)
    await s.eval("window.__penShow(true)")

    for i, (label, gen, photo) in enumerate(GALLERY, 1):
        await s.eval("window.__clear()")
        await s.eval(f"window.__caption('{i}/{len(GALLERY)} — calcul : {label}…')")
        print(f"  {i}. {label}", flush=True)
        ops = gen()
        if photo:
            await show_photo_bg(s)
        await s.eval(f"window.__caption('{i}/{len(GALLERY)} — {label} ({len(ops)} traits)')")
        await asyncio.sleep(0.6)
        await draw_program_live(s, ops)
        await asyncio.sleep(2.5)

    await s.eval("window.__caption('Galerie complete : 7 techniques apprises, demontrees en direct')")
    print("· galerie terminée — fenêtre ouverte ~15s", flush=True)
    await asyncio.sleep(15)
    await s.close()


if __name__ == "__main__":
    asyncio.run(main())

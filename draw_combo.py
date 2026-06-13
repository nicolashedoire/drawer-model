#!/usr/bin/env python3
"""draw-combo — COMBINER plusieurs techniques par bande de valeur.

Comme un illustrateur : une base de ton + des couches plus fortes dans l'ombre.
Ici on superpose la TECHNIQUE 1 (weighted Voronoi stippling, base blue-noise sur
toute la gamme) et la TECHNIQUE 3 (hachures croisées, ajoutées seulement dans les
ombres profondes). Stipple partout + hachures dans le noir = profondeur.

  python3 draw_combo.py --capture
  python3 draw_combo.py --live
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import math

from cdp_session import CDPSession
from draw_lab import CANVAS_URL, OUT, warm_up, draw_stroke
from draw_figure import op_to_points
from draw_live import draw_program_live
from draw_shapes import CAT_SIL
from draw_stipple import cat_density, weighted_voronoi_stipple
from draw_hatch_flow import field_and_tone

W, H = 1000, 640


def combo_ops(n_stipple=1100, hatch_step=8.0):
    import numpy as np
    ops = []
    mask, tone = field_and_tone()
    # base : stippling blue-noise (technique 1) — SEULEMENT dans les clairs/moyens
    dens_light = np.where(tone < 0.5, cat_density(), 0.0)
    pts = weighted_voronoi_stipple(dens_light, n_stipple)
    ops += [{"op": "circle", "c": [float(x), float(y)], "r": 1.5} for x, y in pts]
    # couche d'ombre : hachures croisées (technique 3) — SEULEMENT dans le sombre
    layers = [(0.45, 0.6), (0.62, 0.6 + math.pi / 2)]      # (ton seuil, angle)
    y = 4
    while y < H:
        x = 4
        while x < W:
            iy, ix = int(y), int(x)
            if mask[iy, ix]:
                t = tone[iy, ix]
                for thr, a in layers:
                    if t > thr:
                        L = 7
                        ops.append({"op": "line",
                                    "a": [x - L / 2 * math.cos(a), y - L / 2 * math.sin(a)],
                                    "b": [x + L / 2 * math.cos(a), y + L / 2 * math.sin(a)]})
            x += hatch_step
        y += hatch_step
    ops.append({"op": "polyline", "pts": [list(p) for p in CAT_SIL], "close": True})
    return ops


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--capture", action="store_true")
    a = ap.parse_args()
    ops = combo_ops(n_stipple=550 if a.live else 1100, hatch_step=10.0 if a.live else 8.0)
    print(f"· combo stipple+hachures : {len(ops)} formes (base blue-noise + ombres hachurées)", flush=True)

    s = CDPSession(headless=not a.live, width=1040, height=730)
    s.launch_chrome(); await s.connect(); await s.navigate(CANVAS_URL)
    await s.wait_for("window.__ready === true", timeout=12); await warm_up(s)
    if a.live:
        await s.eval("window.__penShow(true)")
        await s.eval("window.__caption('COMBO : stippling (Lloyd) + hachures croisees dans les ombres')")
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
        (OUT / "combo_cat.png").write_bytes(base64.b64decode(res["data"]))
        print(f"✓ rendu → {OUT / 'combo_cat.png'}", flush=True)
    await s.close()


if __name__ == "__main__":
    asyncio.run(main())

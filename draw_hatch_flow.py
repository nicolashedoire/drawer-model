#!/usr/bin/env python3
"""draw-hatch-flow — TECHNIQUE 3 : hachures ORIENTÉES par un champ de flux.

Vraies hachures de dessin (pas aléatoires) : la DIRECTION des traits suit la
forme (tangente aux contours, dérivée du champ de distance lissé), et on
SUPERPOSE des couches selon le ton — 1 sens en demi-teinte, 2 sens croisés dans
l'ombre, 3 sens dans le plus sombre. C'est l'idée des Tonal Art Maps (Praun 2001)
et du image-space hatching : orientation + densité = valeur.

  python3 draw_hatch_flow.py --capture
  python3 draw_hatch_flow.py --live
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import math

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import distance_transform_edt, gaussian_filter

from cdp_session import CDPSession
from draw_lab import CANVAS_URL, OUT, warm_up, draw_stroke
from draw_figure import op_to_points
from draw_live import draw_program_live
from draw_shapes import CAT_SIL
from draw_stipple import cat_density

W, H = 1000, 640


def field_and_tone():
    img = Image.new("L", (W, H), 0)
    ImageDraw.Draw(img).polygon([tuple(p) for p in CAT_SIL], fill=255)
    mask = np.array(img) > 0
    ys, xs = np.mgrid[0:H, 0:W]
    bright = 1.0 - (0.45 * xs / W + 0.55 * ys / H)        # lumière en haut-gauche
    dist = distance_transform_edt(mask); edge = np.clip(dist / 40.0, 0, 1)
    tone = np.clip((1 - bright) * 0.95 + (1 - edge) * 0.25 - 0.14, 0, 1)
    return mask, np.where(mask, tone, 0.0)


def hatch_ops(step=7.0, seed=3):
    rng = np.random.default_rng(seed)
    mask, tone = field_and_tone()
    ops = []
    layers = [(0.28, 0.6), (0.52, 0.6 + math.pi / 2), (0.76, 0.6 + math.pi / 4)]   # ton seuil, angle FIXE
    y = 4
    while y < H:
        x = 4
        while x < W:
            iy, ix = int(y), int(x)
            if mask[iy, ix]:
                t = tone[iy, ix]
                for thr, a in layers:
                    if t > thr:
                        L = 6 + t * 7
                        jx, jy = rng.uniform(-2.2, 2.2), rng.uniform(-2.2, 2.2)
                        ops.append({"op": "line",
                                    "a": [x + jx - L / 2 * math.cos(a), y + jy - L / 2 * math.sin(a)],
                                    "b": [x + jx + L / 2 * math.cos(a), y + jy + L / 2 * math.sin(a)]})
            x += step
        y += step
    ops.append({"op": "polyline", "pts": [list(p) for p in CAT_SIL], "close": True})
    return ops


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--capture", action="store_true")
    a = ap.parse_args()
    ops = hatch_ops(step=8.5 if a.live else 6.0)
    print(f"· hachures orientées : {len(ops)} traits (direction = flux de la forme, couches = ton)", flush=True)

    s = CDPSession(headless=not a.live, width=1040, height=730)
    s.launch_chrome(); await s.connect(); await s.navigate(CANVAS_URL)
    await s.wait_for("window.__ready === true", timeout=12); await warm_up(s)
    if a.live:
        await s.eval("window.__penShow(true)")
        await s.eval("window.__caption('Hachures orientees par le flux (image-space hatching / Tonal Art Maps)')")
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
        (OUT / "hatchflow_cat.png").write_bytes(base64.b64decode(res["data"]))
        print(f"✓ rendu → {OUT / 'hatchflow_cat.png'}", flush=True)
    await s.close()


if __name__ == "__main__":
    asyncio.run(main())

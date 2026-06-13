#!/usr/bin/env python3
"""draw-portrait — COMBINER lignes + tons sur une VRAIE photo (le niveau au-dessus).

Sur la même image alignée :
  - XDoG (Winnemöller 2012) → les LIGNES (contours, traits, structure)
  - weighted Voronoi stippling → les TONS (ombre/volume, densité = ton réel)
Lignes + valeur = un vrai portrait à l'encre, tiré d'une photo.

  python3 draw_portrait.py --capture
  python3 draw_portrait.py --live          # tracé en direct
  python3 draw_portrait.py --live --over   # tracé par-dessus la photo
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json

import cv2
import numpy as np
from PIL import Image, ImageOps

from cdp_session import CDPSession
from draw_lab import CANVAS_URL, OUT, warm_up, draw_stroke
from draw_figure import op_to_points
from draw_live import draw_program_live
from draw_stipple import weighted_voronoi_stipple

W, H = 1000, 640
SRC = OUT / "source_cat2.jpg"
TW = 600


def load_gray():
    im = ImageOps.autocontrast(Image.open(SRC).convert("L"))
    iw, ih = im.size
    nw = TW; nh = int(ih * nw / iw)
    if nh > H - 20:
        nh = H - 20; nw = int(iw * nh / ih)
    g = np.asarray(im.resize((nw, nh)), float) / 255.0
    return g, (W - nw) // 2, (H - nh) // 2, nw, nh


def xdog_lines(g, x0, y0, sigma=1.0, k=1.6, p=22.0, eps=0.62, phi=18.0):
    g1 = cv2.GaussianBlur(g, (0, 0), sigma)
    g2 = cv2.GaussianBlur(g, (0, 0), sigma * k)
    u = (1 + p) * g1 - p * g2
    T = np.where(u >= eps, 1.0, 1.0 + np.tanh(phi * (u - eps)))
    edges = ((T < 0.5).astype(np.uint8)) * 255
    edges = cv2.medianBlur(edges, 3)
    cnts, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    ops = []
    for c in cnts:
        if len(c) < 7:
            continue
        c2 = cv2.approxPolyDP(c, 1.2, False)
        pts = [[float(pt[0][0] + x0), float(pt[0][1] + y0)] for pt in c2]
        if len(pts) >= 2:
            ops.append({"op": "polyline", "pts": pts, "close": False})
    return ops


def stipple_tone(g, x0, y0, nw, nh, n):
    dens = np.zeros((H, W))
    di = np.clip((1 - g ** 0.9) * 1.05 - 0.06, 0, 1)          # sombre = dense
    dens[y0:y0 + nh, x0:x0 + nw] = di
    pts = weighted_voronoi_stipple(dens, n, iters=26)
    return [{"op": "circle", "c": [float(x), float(y)], "r": 1.4} for x, y in pts]


def portrait_ops(n_stipple):
    g, x0, y0, nw, nh = load_gray()
    tone = stipple_tone(g, x0, y0, nw, nh, n_stipple)         # tons d'abord
    lines = xdog_lines(g, x0, y0)                             # lignes par-dessus
    return tone + lines


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--capture", action="store_true")
    ap.add_argument("--over", action="store_true")
    a = ap.parse_args()
    n = 1400 if a.live else 2600
    print(f"· portrait combiné : stipple({n}) + XDoG…", flush=True)
    ops = portrait_ops(n)
    print(f"· {len(ops)} formes (tons + lignes)", flush=True)

    s = CDPSession(headless=not a.live, width=1040, height=730)
    s.launch_chrome(); await s.connect(); await s.navigate(CANVAS_URL)
    await s.wait_for("window.__ready === true", timeout=12); await warm_up(s)
    await s.eval("window.__clear()")
    if a.over:
        g, x0, y0, nw, nh = load_gray()
        im = Image.open(SRC).convert("RGB").resize((nw, nh))
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=82)
        durl = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        await s.eval("window.__bg(" + json.dumps(durl) + f", 0.45, {x0}, {y0}, {nw}, {nh})")
    if a.live:
        await s.eval("window.__penShow(true)")
        await s.eval("window.__caption('Portrait combine : stipple (tons) + XDoG (lignes) sur photo reelle')")
        await asyncio.sleep(1.0)
        await draw_program_live(s, ops)
        await asyncio.sleep(15)
    else:
        for op in ops:
            await draw_stroke(s, op_to_points(op))
        await s.eval("1")
        res = await s.send("Page.captureScreenshot", {"format": "png"})
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "portrait_cat.png").write_bytes(base64.b64decode(res["data"]))
        print(f"✓ rendu → {OUT / 'portrait_cat.png'}", flush=True)
    await s.close()


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""draw-photo — dessiner À PARTIR D'UNE VRAIE PHOTO (apprentissage réel).

On part d'une photo (pas d'une silhouette synthétique) : niveaux de gris →
densité (sombre = dense) → on applique les techniques apprises. Ici la photo
fournit le vrai ton et le vrai détail.

  tech=stipple : weighted Voronoi stippling de la photo (portrait pointilliste)

  python3 draw_photo.py stipple --capture
  python3 draw_photo.py stipple --live
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json

import numpy as np
from PIL import Image, ImageOps

from cdp_session import CDPSession
from draw_lab import CANVAS_URL, OUT, warm_up, draw_stroke
from draw_figure import op_to_points
from draw_live import draw_program_live
from draw_stipple import weighted_voronoi_stipple

W, H = 1000, 640
SRC = OUT / "source_cat2.jpg"


def photo_density(target_w=560, gamma=0.9):
    im = ImageOps.autocontrast(Image.open(SRC).convert("L"))
    iw, ih = im.size
    nw = target_w
    nh = int(ih * nw / iw)
    if nh > H - 20:
        nh = H - 20; nw = int(iw * nh / ih)
    im = im.resize((nw, nh))
    g = (np.asarray(im, float) / 255.0) ** gamma
    dens_img = np.clip((1 - g) * 1.1 - 0.04, 0, 1)            # sombre = dense
    dens = np.zeros((H, W))
    x0 = (W - nw) // 2
    y0 = (H - nh) // 2
    dens[y0:y0 + nh, x0:x0 + nw] = dens_img
    return dens, (x0, y0, nw, nh)


def placement(target_w):
    iw, ih = Image.open(SRC).size
    nw = target_w; nh = int(ih * nw / iw)
    if nh > H - 20:
        nh = H - 20; nw = int(iw * nh / ih)
    return (W - nw) // 2, (H - nh) // 2, nw, nh


def stipple_ops(n):
    dens, _ = photo_density()
    pts = weighted_voronoi_stipple(dens, n, iters=30)
    return [{"op": "circle", "c": [float(x), float(y)], "r": 1.5} for x, y in pts]


def xdog_lines(target_w=640, sigma=1.0, k=1.6, p=22.0, eps=0.62, phi=18.0):
    """XDoG (Winnemöller 2012) : (1+p)·G_sigma − p·G_ksigma, seuil tanh → bords,
    puis cv2.findContours pour vectoriser en traits."""
    import cv2
    im = ImageOps.autocontrast(Image.open(SRC).convert("L"))
    iw, ih = im.size
    nw = target_w; nh = int(ih * nw / iw)
    if nh > H - 20:
        nh = H - 20; nw = int(iw * nh / ih)
    g = np.asarray(im.resize((nw, nh)), float) / 255.0
    g1 = cv2.GaussianBlur(g, (0, 0), sigma)
    g2 = cv2.GaussianBlur(g, (0, 0), sigma * k)
    u = (1 + p) * g1 - p * g2                                  # DoG étendu (sharpened)
    T = np.where(u >= eps, 1.0, 1.0 + np.tanh(phi * (u - eps)))
    edges = ((T < 0.5).astype(np.uint8)) * 255
    edges = cv2.medianBlur(edges, 3)                           # nettoie le bruit
    cnts, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    x0, y0 = (W - nw) // 2, (H - nh) // 2
    ops = []
    for c in cnts:
        if len(c) < 5:
            continue
        c2 = cv2.approxPolyDP(c, 1.2, False)
        pts = [[float(pt[0][0] + x0), float(pt[0][1] + y0)] for pt in c2]
        if len(pts) >= 2:
            ops.append({"op": "polyline", "pts": pts, "close": False})
    return ops


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tech", nargs="?", default="stipple")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--capture", action="store_true")
    ap.add_argument("--over", action="store_true")
    a = ap.parse_args()
    if a.tech == "xdog":
        ops = xdog_lines()
        print(f"· photo → XDoG : {len(ops)} traits de lignes (extraction de contours)", flush=True)
    else:
        n = 1100 if a.live else 4200
        ops = stipple_ops(n)
        print(f"· photo → stipple : {len(ops)} points (densité = ton réel)", flush=True)

    s = CDPSession(headless=not a.live, width=1040, height=730)
    s.launch_chrome(); await s.connect(); await s.navigate(CANVAS_URL)
    await s.wait_for("window.__ready === true", timeout=12); await warm_up(s)
    await s.eval("window.__clear()")
    if a.over:
        x0, y0, nw, nh = placement(640 if a.tech == "xdog" else 560)
        im = Image.open(SRC).convert("RGB").resize((nw, nh))
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=82)
        durl = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        await s.eval("window.__bg(" + json.dumps(durl) + f", 0.5, {x0}, {y0}, {nw}, {nh})")
    cap = "Photo reelle : XDoG trace par-dessus" if a.tech == "xdog" else "Photo reelle : stippling"
    if a.live:
        await s.eval("window.__penShow(true)")
        await s.eval("window.__caption(" + json.dumps(cap) + ")")
        await asyncio.sleep(1.0)
        await draw_program_live(s, ops)
        await asyncio.sleep(15)
    else:
        for op in ops:
            await draw_stroke(s, op_to_points(op))
        await s.eval("1")
        res = await s.send("Page.captureScreenshot", {"format": "png"})
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"photo_{a.tech}.png").write_bytes(base64.b64decode(res["data"]))
        print(f"✓ rendu → {OUT / ('photo_' + a.tech + '.png')}", flush=True)
    await s.close()


if __name__ == "__main__":
    asyncio.run(main())

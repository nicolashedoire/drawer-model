#!/usr/bin/env python3
"""draw-lines — dessin au TRAIT (lignes), sans aucun point.

Extraction de lignes propres d'une image (XDoG, Winnemöller 2012) puis tracé des
contours en polylignes. Pré-filtre bilatéral pour lisser la fourrure sans tuer
les bords ; on ne garde que les traits assez longs (pas le bruit). Lignes seules.

  python3 draw_lines.py --src .state/draw/gen_cat2.png --capture
  python3 draw_lines.py --src .state/draw/gen_cat2.png --live
"""
from __future__ import annotations

import argparse
import asyncio
import base64

import cv2
import numpy as np
from PIL import Image, ImageOps

from cdp_session import CDPSession
from draw_lab import CANVAS_URL, OUT, warm_up, draw_stroke
from draw_figure import op_to_points
from draw_live import draw_program_live

W, H = 1000, 640


def cat_lines(src, target_w=620, sigma=1.5, k=1.6, p=20.0, eps=0.58, phi=15.0, min_len=22):
    im = ImageOps.autocontrast(Image.open(src).convert("L"))
    iw, ih = im.size
    nw = target_w; nh = int(ih * nw / iw)
    if nh > H - 20:
        nh = H - 20; nw = int(iw * nh / ih)
    g = np.asarray(im.resize((nw, nh)), np.float32) / 255.0
    g = cv2.bilateralFilter(g, 7, 0.12, 6)                    # lisse la fourrure, garde les bords
    g1 = cv2.GaussianBlur(g, (0, 0), sigma)
    g2 = cv2.GaussianBlur(g, (0, 0), sigma * k)
    u = (1 + p) * g1 - p * g2
    T = np.where(u >= eps, 1.0, 1.0 + np.tanh(phi * (u - eps)))
    edges = ((T < 0.5).astype(np.uint8)) * 255
    edges = cv2.medianBlur(edges, 3)
    cnts, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    x0, y0 = (W - nw) // 2, (H - nh) // 2
    ops = []
    for c in cnts:
        if cv2.arcLength(c, False) < min_len:
            continue
        c2 = cv2.approxPolyDP(c, 1.0, False)
        pts = [[float(pt[0][0] + x0), float(pt[0][1] + y0)] for pt in c2]
        if len(pts) >= 2:
            ops.append({"op": "polyline", "pts": pts, "close": False})
    return ops, (x0, y0, nw, nh)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(OUT / "gen_cat2.png"))
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--capture", action="store_true")
    a = ap.parse_args()
    ops, _ = cat_lines(a.src)
    print(f"· dessin au trait : {len(ops)} lignes (XDoG, sans points)", flush=True)

    s = CDPSession(headless=not a.live, width=1040, height=730)
    s.launch_chrome(); await s.connect(); await s.navigate(CANVAS_URL)
    await s.wait_for("window.__ready === true", timeout=12); await warm_up(s)
    await s.eval("window.__clear()")
    if a.live:
        await s.eval("window.__penShow(true)")
        await s.eval("window.__caption('Dessin au trait (lignes XDoG), sans aucun point')")
        await asyncio.sleep(1.0)
        await draw_program_live(s, ops)
        await asyncio.sleep(15)
    else:
        for op in ops:
            await draw_stroke(s, op_to_points(op))
        await s.eval("1")
        res = await s.send("Page.captureScreenshot", {"format": "png"})
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "lines_cat.png").write_bytes(base64.b64decode(res["data"]))
        print(f"✓ rendu → {OUT / 'lines_cat.png'}", flush=True)
    await s.close()


if __name__ == "__main__":
    asyncio.run(main())

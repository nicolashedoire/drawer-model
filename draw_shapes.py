#!/usr/bin/env python3
"""draw-shapes — nouvelle méthode : une MULTITUDE de petites formes → du détail.

Au lieu de ~25 contours, le cerveau écrit un GÉNÉRATEUR PROCÉDURAL qui produit des
centaines de petites formes (feuilles, touches, hachures) pour composer un résultat
riche. La main les trace toutes. Beaucoup de formes = beaucoup de détail.

  python3 draw_shapes.py tree --capture   # rend (headless) pour vérifier
  python3 draw_shapes.py tree --live       # me regarder le construire forme par forme
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import math
import random

from cdp_session import CDPSession
from draw_lab import CANVAS_URL, OUT, warm_up, draw_stroke
from draw_figure import op_to_points
from draw_live import draw_program_live


def leaf(x, y, s, ang):
    dx, dy = s * math.cos(ang), s * math.sin(ang)
    return {"op": "cubic", "p": [[x, y], [x + dx * .4, y + dy * .4 - 3],
                                 [x + dx * .7, y + dy * .7 + 3], [x + dx, y + dy]]}


def generate_tree(seed=3):
    rng = random.Random(seed)
    ops = []
    ops.append({"op": "cubic", "p": [[484, 562], [490, 460], [492, 380], [498, 312]]})   # tronc G
    ops.append({"op": "cubic", "p": [[516, 562], [510, 460], [508, 380], [502, 312]]})   # tronc D
    for _ in range(10):                                                                  # écorce
        x, y = rng.uniform(490, 510), rng.uniform(360, 545)
        ops.append({"op": "line", "a": [x, y], "b": [x + rng.uniform(-2, 2), y + rng.uniform(12, 22)]})
    for bx, by, tx, ty in [(500, 330, 418, 248), (500, 330, 582, 248), (500, 312, 500, 196),
                           (500, 348, 440, 300), (500, 348, 560, 300)]:                  # branches
        ops.append({"op": "line", "a": [bx, by], "b": [tx, ty]})
    for cx, cy, rad in [(500, 206, 96), (428, 248, 74), (572, 248, 74),
                        (468, 168, 62), (540, 176, 62), (500, 262, 82)]:                 # feuillage
        for _ in range(int(rad * 0.5)):
            a = rng.uniform(0, 6.283)
            r = rad * math.sqrt(rng.uniform(0, 1))
            x, y = cx + r * math.cos(a), cy + r * math.sin(a)
            ops.append(leaf(x, y, rng.uniform(7, 15), rng.uniform(0, 6.283)))
    return ops


def generate_cat(seed=5):
    from draw_now import CAT as _CAT
    rng = random.Random(seed)
    ops = list(_CAT[:-3])                                   # contour lisse (sans rayures)
    cx, cy, rx, ry = 500, 428, 112, 116                    # fourrure du corps : touches vers le bas
    for _ in range(230):
        t = rng.uniform(0, 6.283); rr = math.sqrt(rng.uniform(0, 1))
        x, y = cx + rx * rr * math.cos(t), cy + ry * rr * math.sin(t)
        if y < 314:
            continue
        ang = math.pi / 2 + rng.uniform(-0.5, 0.5)
        L = rng.uniform(8, 16)
        ops.append({"op": "line", "a": [x, y], "b": [x + L * math.cos(ang), y + L * math.sin(ang)]})
    hx, hy, hr = 500, 206, 100                              # fourrure des joues (bas de la tête)
    for _ in range(90):
        t = rng.uniform(0.2, 2.94); rr = rng.uniform(0.72, 1.0)
        x, y = hx + hr * rr * math.cos(t), hy + hr * rr * math.sin(t)
        ang = math.atan2(y - hy, x - hx) + rng.uniform(-0.3, 0.3)
        L = rng.uniform(6, 12)
        ops.append({"op": "line", "a": [x, y], "b": [x + L * math.cos(ang), y + L * math.sin(ang)]})
    return ops


def _in_poly(x, y, poly):
    inside = False
    n = len(poly); j = n - 1
    for i in range(n):
        xi, yi = poly[i]; xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-9) + xi):
            inside = not inside
        j = i
    return inside


def generate_lowpoly(poly, cell=30, jitter=7, seed=4):
    """Maille de petits triangles remplissant la silhouette (low-poly)."""
    rng = random.Random(seed)
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    cols = int((x1 - x0) / cell) + 3
    rows = int((y1 - y0) / cell) + 3
    pts = {}
    for r in range(rows):
        for c in range(cols):
            pts[(r, c)] = (x0 - cell + c * cell + rng.uniform(-jitter, jitter),
                           y0 - cell + r * cell + rng.uniform(-jitter, jitter))
    ops = []
    for r in range(rows - 1):
        for c in range(cols - 1):
            a, b = pts[(r, c)], pts[(r, c + 1)]
            d, e = pts[(r + 1, c)], pts[(r + 1, c + 1)]
            for tri in ((a, b, e), (a, e, d)):
                gx = (tri[0][0] + tri[1][0] + tri[2][0]) / 3
                gy = (tri[0][1] + tri[1][1] + tri[2][1]) / 3
                if _in_poly(gx, gy, poly):
                    ops.append({"op": "polyline", "pts": [list(tri[0]), list(tri[1]), list(tri[2])], "close": True})
    return ops


CAT_SIL = [
    (430, 150), (412, 52), (472, 118),          # oreille gauche (pointue)
    (500, 104),                                 # creux du sommet
    (528, 118), (588, 52), (570, 150),          # oreille droite
    (598, 202), (584, 264),                     # tête droite
    (558, 288),                                 # cou pincé droite
    (628, 362), (638, 472), (596, 538), (540, 556),   # corps droit → bas
    (460, 556), (404, 538), (362, 472), (372, 362),   # bas → corps gauche
    (442, 288),                                 # cou pincé gauche
    (416, 264), (402, 202),                     # tête gauche
]

GENERATORS = {
    "tree": generate_tree,
    "cat": generate_cat,
    "lowcat": lambda: generate_lowpoly(CAT_SIL, cell=26),
}


async def capture(prog, name, s):
    await s.eval("window.__clear()")
    for op in prog:
        await draw_stroke(s, op_to_points(op))
    await s.eval("1")
    res = await s.send("Page.captureScreenshot", {"format": "png"})
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"shapes_{name}.png"
    p.write_bytes(base64.b64decode(res["data"]))
    return p


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("subject", nargs="?", default="tree")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--capture", action="store_true")
    a = ap.parse_args()
    prog = GENERATORS[a.subject]()
    print(f"· {a.subject} : {len(prog)} formes générées", flush=True)

    s = CDPSession(headless=not a.live, width=1040, height=730)
    s.launch_chrome(); await s.connect(); await s.navigate(CANVAS_URL)
    await s.wait_for("window.__ready === true", timeout=12); await warm_up(s)

    if a.live:
        await s.eval("window.__penShow(true)")
        await s.eval(f"window.__caption('je construis un arbre en {len(prog)} petites formes…')")
        await asyncio.sleep(1.2)
        await draw_program_live(s, prog)
        await s.eval("window.__caption('arbre — une multitude de formes ✎')")
        await asyncio.sleep(15)
    else:
        p = await capture(prog, a.subject, s)
        print(f"✓ rendu → {p}", flush=True)
    await s.close()


if __name__ == "__main__":
    asyncio.run(main())

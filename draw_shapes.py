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


GENERATORS = {"tree": generate_tree}


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

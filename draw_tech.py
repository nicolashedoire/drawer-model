#!/usr/bin/env python3
"""draw-tech — j'essaie plusieurs TECHNIQUES et je les teste devant toi.

Chaque technique remplit une silhouette avec un style différent, ombré selon une
lumière (haut-gauche). On compare ce qui marche.

  python3 draw_tech.py stipple --capture     # vérifier le rendu
  python3 draw_tech.py hatch --live           # me regarder dessiner
  python3 draw_tech.py stipple hatch pack --live   # enchaîne les 3 en direct
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
from draw_shapes import CAT_SIL, _in_poly


def _bbox(poly):
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    return min(xs), max(xs), min(ys), max(ys)


def _value(x, y, cx, cy, light=(0.7, 0.7)):
    vx, vy = x - cx, y - cy
    vl = math.hypot(vx, vy) or 1
    s = (vx / vl) * light[0] + (vy / vl) * light[1]      # -1 lumière .. 1 ombre
    return max(0.0, min(1.0, (s + 0.5) * 0.7))


def _outline(poly):
    return {"op": "polyline", "pts": [list(p) for p in poly], "close": True}


def stipple(poly, n=900, seed=2):
    rng = random.Random(seed)
    x0, x1, y0, y1 = _bbox(poly); cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    ops, placed, tries = [], 0, 0
    while placed < n and tries < n * 7:
        tries += 1
        x, y = rng.uniform(x0, x1), rng.uniform(y0, y1)
        if not _in_poly(x, y, poly):
            continue
        v = _value(x, y, cx, cy)
        if rng.random() < 0.18 + v * 0.95:
            ops.append({"op": "circle", "c": [x, y], "r": 1.3 + v * 2.0})
            placed += 1
    ops.append(_outline(poly))
    return ops


def hatch(poly, step=9, seed=2):
    rng = random.Random(seed)
    x0, x1, y0, y1 = _bbox(poly); cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    ops = []
    y = y0
    while y < y1:
        x = x0
        while x < x1:
            px, py = x + rng.uniform(-2, 2), y + rng.uniform(-2, 2)
            if _in_poly(px, py, poly):
                v = _value(px, py, cx, cy)
                if v > 0.12:
                    L = 5 + v * 9; a = 0.5
                    ops.append({"op": "line", "a": [px, py], "b": [px + L * math.cos(a), py + L * math.sin(a)]})
                if v > 0.55:                              # croisé dans l'ombre
                    L = 5 + v * 8; a = -0.7
                    ops.append({"op": "line", "a": [px, py], "b": [px + L * math.cos(a), py + L * math.sin(a)]})
            x += step
        y += step
    ops.append(_outline(poly))
    return ops


def pack(poly, tries=1400, seed=5):
    rng = random.Random(seed)
    x0, x1, y0, y1 = _bbox(poly)
    circles = []
    for _ in range(tries):
        r = rng.choice([20, 16, 13, 10, 8, 6, 5, 4])
        x, y = rng.uniform(x0, x1), rng.uniform(y0, y1)
        if not (_in_poly(x, y, poly) and _in_poly(x + r, y, poly) and _in_poly(x - r, y, poly)
                and _in_poly(x, y + r, poly) and _in_poly(x, y - r, poly)):
            continue
        if all(math.hypot(x - cx, y - cy) >= r + cr + 1.5 for cx, cy, cr in circles):
            circles.append((x, y, r))
    ops = [{"op": "circle", "c": [x, y], "r": r} for x, y, r in circles]
    ops.append(_outline(poly))
    return ops


TECHS = {"stipple": stipple, "hatch": hatch, "pack": pack}
FR = {"stipple": "pointillisme", "hatch": "hachures croisées", "pack": "circle packing"}


async def run(prog, name, s, live):
    await s.eval("window.__clear()")
    if live:
        await s.eval("window.__penShow(true)")
        await s.eval(f"window.__caption('technique : {FR[name]} ({len(prog)} formes)')")
        await asyncio.sleep(0.8)
        await draw_program_live(s, prog)
        await asyncio.sleep(2.5)
    else:
        for op in prog:
            await draw_stroke(s, op_to_points(op))
        await s.eval("1")
        res = await s.send("Page.captureScreenshot", {"format": "png"})
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"tech_{name}.png").write_bytes(base64.b64decode(res["data"]))


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("techs", nargs="*", default=["stipple"])
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--capture", action="store_true")
    a = ap.parse_args()
    techs = [t for t in a.techs if t in TECHS] or ["stipple"]

    s = CDPSession(headless=not a.live, width=1040, height=730)
    s.launch_chrome(); await s.connect(); await s.navigate(CANVAS_URL)
    await s.wait_for("window.__ready === true", timeout=12); await warm_up(s)
    light = {"stipple": dict(n=360), "hatch": dict(step=12), "pack": dict(tries=900)}
    for t in techs:
        prog = TECHS[t](CAT_SIL, **(light[t] if a.live else {}))
        print(f"· {t} ({FR[t]}) : {len(prog)} formes", flush=True)
        await run(prog, t, s, a.live)
    if a.live:
        await s.eval("window.__caption('techniques testées ✎')")
        await asyncio.sleep(12)
    await s.close()


if __name__ == "__main__":
    asyncio.run(main())

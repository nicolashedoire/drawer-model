#!/usr/bin/env python3
"""draw-flow — TECHNIQUE 4 : lignes de flux (streamlines) suivant un champ.

Famille flow-field / Edge Tangent Flow (Kang 2007). On construit un champ
d'orientation lisse (organique), puis on TRACE des streamlines : depuis des
graines, on intègre le champ pas à pas (avant + arrière) en restant dans la
silhouette ; la LONGUEUR et la densité des lignes suivent le ton → l'ombre est
faite de lignes longues qui se chevauchent, la lumière de lignes courtes/rares.

  python3 draw_flow.py --capture
  python3 draw_flow.py --live
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import math

import numpy as np
from scipy.ndimage import gaussian_filter, zoom

from cdp_session import CDPSession
from draw_lab import CANVAS_URL, OUT, warm_up, draw_stroke
from draw_figure import op_to_points
from draw_live import draw_program_live
from draw_shapes import CAT_SIL
from draw_hatch_flow import field_and_tone

W, H = 1000, 640


def flow_field(seed=7, cell=46):
    rng = np.random.default_rng(seed)
    gh, gw = H // cell + 2, W // cell + 2
    base = rng.uniform(0, 2 * math.pi, (gh, gw))
    cx = gaussian_filter(np.cos(base), 1.4)
    sy = gaussian_filter(np.sin(base), 1.4)
    ang = np.arctan2(sy, cx)
    return zoom(ang, (H / gh, W / gw), order=1)[:H, :W]


def streamline(x, y, field, mask, steps, sstep=3.6, back=False):
    pts = [(x, y)]
    sgn = -1 if back else 1
    for _ in range(steps):
        ix, iy = int(round(x)), int(round(y))
        if not (0 <= ix < W and 0 <= iy < H and mask[iy, ix]):
            break
        a = field[iy, ix]
        x += sgn * sstep * math.cos(a)
        y += sgn * sstep * math.sin(a)
        pts.append((x, y))
    return pts


def flow_ops(step=9):
    mask, tone = field_and_tone()
    field = flow_field()
    ops = []
    y = 4
    while y < H:
        x = 4
        while x < W:
            iy, ix = int(y), int(x)
            if mask[iy, ix] and tone[iy, ix] > 0.20:
                t = tone[iy, ix]
                n = int(1 + t * 4)
                fwd = streamline(x, y, field, mask, n)
                bwd = streamline(x, y, field, mask, n, back=True)
                line = bwd[::-1] + fwd[1:]
                if len(line) > 2:
                    ops.append({"op": "polyline", "pts": [[float(px), float(py)] for px, py in line], "close": False})
            x += step
        y += step
    ops.append({"op": "polyline", "pts": [list(p) for p in CAT_SIL], "close": True})
    return ops


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--capture", action="store_true")
    a = ap.parse_args()
    ops = flow_ops(step=11 if a.live else 8)
    print(f"· lignes de flux : {len(ops)} streamlines (champ lissé, longueur = ton)", flush=True)

    s = CDPSession(headless=not a.live, width=1040, height=730)
    s.launch_chrome(); await s.connect(); await s.navigate(CANVAS_URL)
    await s.wait_for("window.__ready === true", timeout=12); await warm_up(s)
    if a.live:
        await s.eval("window.__penShow(true)")
        await s.eval("window.__caption('Lignes de flux / streamlines (flow field, esprit Edge Tangent Flow)')")
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
        (OUT / "flow_cat.png").write_bytes(base64.b64decode(res["data"]))
        print(f"✓ rendu → {OUT / 'flow_cat.png'}", flush=True)
    await s.close()


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""draw-stipple — TECHNIQUE 1 : Weighted Voronoi Stippling (Secord 2002).

Le VRAI algorithme (pas le stipple aléatoire) : relaxation de Lloyd sur un
diagramme de Voronoï pondéré par la densité. Chaque point se déplace vers le
centroïde pondéré par la densité de sa cellule ; les zones sombres attirent plus
de points ; la distribution converge vers un bruit bleu (points espacés, sans
grille parasite). On s'arrête avant la sur-convergence (réseau hexagonal).

  python3 draw_stipple.py --capture        # rendu pleine qualité (vérif)
  python3 draw_stipple.py --live           # me regarder le tracer
"""
from __future__ import annotations

import argparse
import asyncio
import base64

import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial import cKDTree
from scipy.ndimage import distance_transform_edt

from cdp_session import CDPSession
from draw_lab import CANVAS_URL, OUT, warm_up, draw_stroke
from draw_figure import op_to_points
from draw_live import draw_program_live
from draw_shapes import CAT_SIL

W, H = 1000, 640


def cat_density():
    """Carte de densité (sombre = dense) : silhouette + ombrage directionnel + bord."""
    img = Image.new("L", (W, H), 0)
    ImageDraw.Draw(img).polygon([tuple(p) for p in CAT_SIL], fill=255)
    mask = np.array(img) > 0
    ys, xs = np.mgrid[0:H, 0:W]
    bright = 1.0 - (0.5 * xs / W + 0.5 * ys / H)          # lumière en haut-gauche
    darkness = np.clip(1.0 - bright, 0.0, 1.0)
    dist = distance_transform_edt(mask)                   # forme : bord plus sombre
    edge = np.clip(dist / 45.0, 0, 1)
    darkness = darkness * 0.8 + (1 - edge) * 0.45
    dens = np.where(mask, 0.12 + 0.9 * darkness, 0.0)
    return dens


def weighted_voronoi_stipple(density, n, iters=32, seed=1, step=2):
    """Relaxation de Lloyd pondérée par la densité → n points en bruit bleu."""
    h, w = density.shape
    ys, xs = np.mgrid[0:h:step, 0:w:step]
    px, py = xs.ravel().astype(float), ys.ravel().astype(float)
    wt = density[ys.ravel(), xs.ravel()]
    valid = wt > 1e-6
    px, py, wt = px[valid], py[valid], wt[valid]
    P = np.stack([px, py], axis=1)
    rng = np.random.default_rng(seed)
    prob = wt / wt.sum()
    idx = rng.choice(len(px), size=n, p=prob)
    pts = P[idx] + rng.uniform(-1.5, 1.5, (n, 2))
    for _ in range(iters):
        _, asg = cKDTree(pts).query(P)
        sw = np.bincount(asg, weights=wt, minlength=n)
        cx = np.bincount(asg, weights=wt * px, minlength=n)
        cy = np.bincount(asg, weights=wt * py, minlength=n)
        nz = sw > 0
        pts[nz, 0] = cx[nz] / sw[nz]
        pts[nz, 1] = cy[nz] / sw[nz]
        if (~nz).any():
            r = rng.choice(len(px), size=int((~nz).sum()), p=prob)
            pts[~nz] = P[r]
    return pts


def stipple_ops(pts, r=1.7):
    ops = [{"op": "circle", "c": [float(x), float(y)], "r": r} for x, y in pts]
    ops.append({"op": "polyline", "pts": [list(p) for p in CAT_SIL], "close": True})
    return ops


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--capture", action="store_true")
    ap.add_argument("--n", type=int, default=0)
    a = ap.parse_args()
    n = a.n or (650 if a.live else 1700)
    print(f"· weighted Voronoi stippling : {n} points, relaxation de Lloyd…", flush=True)
    dens = cat_density()
    pts = weighted_voronoi_stipple(dens, n)
    ops = stipple_ops(pts)
    print(f"· {len(pts)} points placés (bruit bleu, densité = ombre)", flush=True)

    s = CDPSession(headless=not a.live, width=1040, height=730)
    s.launch_chrome(); await s.connect(); await s.navigate(CANVAS_URL)
    await s.wait_for("window.__ready === true", timeout=12); await warm_up(s)
    if a.live:
        await s.eval("window.__penShow(true)")
        await s.eval("window.__caption('Weighted Voronoi Stippling (Secord 2002) — relaxation de Lloyd')")
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
        (OUT / "stipple_cat.png").write_bytes(base64.b64decode(res["data"]))
        print(f"✓ rendu → {OUT / 'stipple_cat.png'}", flush=True)
    await s.close()


if __name__ == "__main__":
    asyncio.run(main())

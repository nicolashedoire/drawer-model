#!/usr/bin/env python3
"""draw-tsp — TECHNIQUE 2 : Stipple → TSP, dessin en UNE seule ligne continue.

On reprend les points du weighted Voronoi stippling et on les relie en un seul
trajet (Travelling Salesman) : construction plus-proche-voisin puis amélioration
2-opt (limitée aux voisins proches) pour retirer les croisements. La sortie est
UNE polyligne unique — un trait qui ne se lève jamais — dont la densité forme
l'image ombrée. (TSP art ; Bosch & Herman, Bridges 2004.)

  python3 draw_tsp.py --capture
  python3 draw_tsp.py --live
"""
from __future__ import annotations

import argparse
import asyncio
import base64

import numpy as np
from scipy.spatial import cKDTree

from cdp_session import CDPSession
from draw_lab import CANVAS_URL, OUT, warm_up, draw_stroke
from draw_figure import op_to_points
from draw_live import draw_program_live
from draw_shapes import CAT_SIL
from draw_stipple import cat_density, weighted_voronoi_stipple


def _len(tour, pts):
    p = pts[tour]
    return float(np.hypot(*(p[1:] - p[:-1]).T).sum())


def nn_tour(pts):
    n = len(pts)
    tree = cKDTree(pts)
    visited = np.zeros(n, bool)
    tour = [0]; visited[0] = True
    cur = 0
    for _ in range(n - 1):
        k = 8
        while True:
            _, idx = tree.query(pts[cur], k=min(k, n))
            nxt = next((j for j in np.atleast_1d(idx) if not visited[j]), None)
            if nxt is not None or k >= n:
                break
            k *= 2
        if nxt is None:
            nxt = int(np.where(~visited)[0][0])
        visited[nxt] = True; tour.append(int(nxt)); cur = nxt
    return tour


def two_opt(tour, pts, rounds=5, k=10):
    n = len(tour)
    nbrs = cKDTree(pts).query(pts, k=min(k + 1, n))[1][:, 1:]
    pos = np.empty(n, int); pos[tour] = np.arange(n)
    tour = np.array(tour)
    for _ in range(rounds):
        improved = False
        for i in range(n - 1):
            a, b = tour[i], tour[i + 1]
            dab = np.hypot(*(pts[a] - pts[b]))
            for c in nbrs[a]:
                j = pos[c]
                if j <= i or j >= n - 1:
                    continue
                dn, e = tour[j], tour[j + 1]
                if dab + np.hypot(*(pts[dn] - pts[e])) > \
                   np.hypot(*(pts[a] - pts[dn])) + np.hypot(*(pts[b] - pts[e])) + 1e-9:
                    tour[i + 1:j + 1] = tour[i + 1:j + 1][::-1]
                    pos[tour[i + 1:j + 1]] = np.arange(i + 1, j + 1)
                    improved = True
                    b = tour[i + 1]; dab = np.hypot(*(pts[a] - pts[b]))
        if not improved:
            break
    return tour.tolist()


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--capture", action="store_true")
    ap.add_argument("--n", type=int, default=0)
    a = ap.parse_args()
    n = a.n or (480 if a.live else 950)
    print(f"· stippling {n} points → TSP…", flush=True)
    pts = weighted_voronoi_stipple(cat_density(), n)
    tour = nn_tour(pts)
    l0 = _len(tour, pts)
    tour = two_opt(tour, pts)
    l1 = _len(tour, pts)
    print(f"· tour : {l0:.0f}px (plus-proche-voisin) → {l1:.0f}px (2-opt, -{100*(l0-l1)/l0:.0f}%)", flush=True)
    line = [[float(pts[i, 0]), float(pts[i, 1])] for i in tour]
    ops = [{"op": "polyline", "pts": line, "close": False},
           {"op": "polyline", "pts": [list(p) for p in CAT_SIL], "close": True}]

    s = CDPSession(headless=not a.live, width=1040, height=730)
    s.launch_chrome(); await s.connect(); await s.navigate(CANVAS_URL)
    await s.wait_for("window.__ready === true", timeout=12); await warm_up(s)
    if a.live:
        await s.eval("window.__penShow(true)")
        await s.eval("window.__caption('Stipple → TSP : une seule ligne continue (TSP art)')")
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
        (OUT / "tsp_cat.png").write_bytes(base64.b64decode(res["data"]))
        print(f"✓ rendu → {OUT / 'tsp_cat.png'}", flush=True)
    await s.close()


if __name__ == "__main__":
    asyncio.run(main())

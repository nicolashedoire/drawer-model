#!/usr/bin/env python3
"""draw-lab — barreau 1 : la MAIN.

Primitives motrices déterministes (ligne, polyligne, cercle, bézier) tracées
dans une toile via des événements souris CDP synthétiques, puis CERTIFIÉES par
relecture des pixels dessinés (chaque trait doit coller au trait idéal au pixel
près). Aucun modèle : la formule, pas l'approximation.

Sortie : un bulletin de certification + une preuve visuelle (.state/draw/).

  python3 draw_lab.py            # certifie M0-M4 (headless, ne touche pas la souris)
  python3 draw_lab.py --show     # fenêtre visible
"""
from __future__ import annotations

import asyncio
import base64
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

from cdp_session import CDPSession

HERE = Path(__file__).resolve().parent
CANVAS_URL = "file://" + str(HERE / "draw_canvas.html")
OUT = HERE / ".state" / "draw"
LINE_WIDTH = 3
TOL = 5.0                       # px : tolérance (≈ demi-épaisseur + marge)
COVER_BAR = 0.98                # part des points idéaux couverts par un pixel peint
PRECISION_BAR = 0.95            # part des pixels peints proches du trait idéal


# ---------------------------------------------------------------- géométrie ---
def flatten_line(a, b, step=4.0):
    (x0, y0), (x1, y1) = a, b
    d = math.hypot(x1 - x0, y1 - y0)
    n = max(2, int(d / step) + 1)
    return [(x0 + (x1 - x0) * t / (n - 1), y0 + (y1 - y0) * t / (n - 1)) for t in range(n)]


def flatten_polyline(pts, step=4.0):
    out = [tuple(pts[0])]
    for i in range(1, len(pts)):
        out += flatten_line(pts[i - 1], pts[i], step)[1:]
    return out


def flatten_arc(cx, cy, r, a0_deg, a1_deg, step=4.0):
    a0, a1 = math.radians(a0_deg), math.radians(a1_deg)
    arc_len = abs(a1 - a0) * r
    n = max(8, int(arc_len / step) + 1)
    return [(cx + r * math.cos(a0 + (a1 - a0) * t / (n - 1)),
             cy + r * math.sin(a0 + (a1 - a0) * t / (n - 1))) for t in range(n)]


def flatten_circle(cx, cy, r, step=4.0):
    return flatten_arc(cx, cy, r, 0, 360, step)


def flatten_cubic(p0, p1, p2, p3, step=4.0):
    # rough length estimate from the control polygon
    L = (math.dist(p0, p1) + math.dist(p1, p2) + math.dist(p2, p3))
    n = max(12, int(L / step) + 1)
    out = []
    for i in range(n):
        t = i / (n - 1)
        u = 1 - t
        x = u*u*u*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t*t*t*p3[0]
        y = u*u*u*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t*t*t*p3[1]
        out.append((x, y))
    return out


# ---------------------------------------------------------------- exécuteur ---
async def draw_stroke(s: CDPSession, pts, pace=0.0015):
    """Trace une polyligne : amorce la position, pen-down, glissé, pen-up.

    Chrome ignore un mousePressed à froid et coalesce les mouseMoved trop rapides
    → on amorce avec un mouseMoved et on espace légèrement les événements.
    """
    x0, y0 = pts[0]
    await s._dispatch_mouse("mouseMoved", x0, y0)            # amorce la position du curseur
    await asyncio.sleep(0.004)
    await s._dispatch_mouse("mousePressed", x0, y0, button="left", buttons=1, clicks=1)
    await asyncio.sleep(0.004)
    for (x, y) in pts[1:]:
        await s._dispatch_mouse("mouseMoved", x, y, button="left", buttons=1)
        await asyncio.sleep(pace)
    xe, ye = pts[-1]
    await s._dispatch_mouse("mouseReleased", xe, ye, button="left", buttons=1, clicks=1)
    await asyncio.sleep(0.004)


async def draw_program(s: CDPSession, strokes):
    for pts in strokes:
        await draw_stroke(s, pts)
    await s.eval("1")  # flush : garantit que tous les événements sont traités


async def warm_up(s: CDPSession):
    """Amorce le pipeline d'input de Chrome (les 1ers événements sont perdus à froid)."""
    for _ in range(3):
        await s.eval("window.__clear()")
        await draw_stroke(s, flatten_line((200, 200), (800, 400)))
        painted = await read_painted(s)
        if len(painted) > 50:
            break
    await s.eval("window.__clear()")


# ---------------------------------------------------------------- vérificateur ---
async def read_painted(s: CDPSession):
    flat = await s.eval("window.__paintedPixels(1)")
    if not flat:
        return np.empty((0, 2))
    a = np.array(flat, dtype=float).reshape(-1, 2)
    return a


def _min_dists(src, dst, chunk=512):
    """Pour chaque point de src, distance au plus proche de dst."""
    if len(src) == 0 or len(dst) == 0:
        return np.full(len(src), 1e9)
    out = np.empty(len(src))
    for i in range(0, len(src), chunk):
        c = src[i:i + chunk]
        d = np.sqrt(((c[:, None, :] - dst[None, :, :]) ** 2).sum(-1))
        out[i:i + chunk] = d.min(axis=1)
    return out


def verify_strokes(painted, ideal_strokes, tol=TOL):
    ideal = np.array([p for st in ideal_strokes for p in st], dtype=float)
    cover_d = _min_dists(ideal, painted)            # idéal -> peint
    prec_d = _min_dists(painted, ideal)             # peint -> idéal
    coverage = float((cover_d <= tol).mean()) if len(ideal) else 0.0
    precision = float((prec_d <= tol).mean()) if len(painted) else 0.0
    passed = coverage >= COVER_BAR and precision >= PRECISION_BAR
    return {"passed": passed, "coverage": round(coverage, 3),
            "precision": round(precision, 3), "n_painted": len(painted)}


# ---------------------------------------------------------------- compétences ---
def skill_cases():
    """Chaque cas : (skill, label, [strokes] où chaque stroke est une polyligne idéale)."""
    cx, cy = 500, 320
    return [
        ("M1 line", "horizontale", [flatten_line((180, 160), (820, 160))]),
        ("M1 line", "verticale", [flatten_line((300, 90), (300, 560))]),
        ("M1 line", "diagonale ↘", [flatten_line((180, 120), (800, 540))]),
        ("M1 line", "diagonale ↗", [flatten_line((180, 540), (820, 120))]),
        ("M2 polyline", "carré", [flatten_polyline([(320, 160), (680, 160), (680, 480), (320, 480), (320, 160)])]),
        ("M2 polyline", "zigzag", [flatten_polyline([(180, 200), (320, 440), (460, 200), (600, 440), (740, 200)])]),
        ("M3 circle", "r=80", [flatten_circle(cx, cy, 80)]),
        ("M3 circle", "r=150", [flatten_circle(cx, cy, 150)]),
        ("M3 circle", "r=220", [flatten_circle(cx, cy, 220)]),
        ("M3 circle", "décentré", [flatten_circle(320, 300, 120)]),
        ("M4 bezier", "S-courbe", [flatten_cubic((180, 480), (360, 80), (640, 560), (820, 160))]),
        ("M4 bezier", "arche", [flatten_cubic((200, 460), (360, 80), (640, 80), (800, 460))]),
    ]


async def run_case(s, strokes):
    await s.eval("window.__clear()")
    await draw_program(s, strokes)
    painted = await read_painted(s)
    return verify_strokes(painted, strokes)


async def save_proof(s, strokes, name):
    await s.eval("window.__clear()")
    await draw_program(s, strokes)
    res = await s.send("Page.captureScreenshot", {"format": "png"})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_bytes(base64.b64decode(res["data"]))


# ---------------------------------------------------------------- main ---
async def main():
    show = "--show" in sys.argv
    s = CDPSession(headless=not show, width=1040, height=700)
    print(f"· lancement Chrome ({'visible' if show else 'headless'}) + toile", flush=True)
    s.launch_chrome()
    await s.connect()
    await s.navigate(CANVAS_URL)
    if not await s.wait_for("window.__ready === true", timeout=12):
        print("✗ la toile ne s'est pas chargée"); await s.close(); return
    w, h = await s.eval("window.__size()")
    print(f"· toile {w}×{h}, épaisseur {LINE_WIDTH}px, tolérance {TOL}px")
    print(f"· barres : couverture ≥{COVER_BAR}, précision ≥{PRECISION_BAR}")
    await warm_up(s)
    print("· pipeline d'input amorcé\n")

    t0 = time.time()
    cards = {}
    for skill, label, strokes in skill_cases():
        r = await run_case(s, strokes)
        c = cards.setdefault(skill, {"pass": 0, "total": 0, "min_cov": 1.0, "min_prec": 1.0})
        c["total"] += 1
        c["pass"] += int(r["passed"])
        c["min_cov"] = min(c["min_cov"], r["coverage"])
        c["min_prec"] = min(c["min_prec"], r["precision"])
        mark = "✓" if r["passed"] else "✗"
        print(f"  {mark} {skill:14} {label:14} couverture={r['coverage']:.3f} précision={r['precision']:.3f}")

    # preuve visuelle : un cercle + une étoile béziers
    await save_proof(s, [flatten_circle(500, 320, 200)], "proof_circle.png")
    await save_proof(s, skill_cases()[10][2] + skill_cases()[6][2], "proof_curve_circle.png")

    print("\n===== BULLETIN DE CERTIFICATION =====")
    all_ok = True
    for skill, c in cards.items():
        ok = c["pass"] == c["total"]
        all_ok &= ok
        tag = "CERTIFIÉ ✓" if ok else "ÉCHEC ✗"
        print(f"  [{tag:11}] {skill:14} {c['pass']}/{c['total']} "
              f"| couverture min {c['min_cov']:.3f} | précision min {c['min_prec']:.3f}")
    print(f"\n{'✅ MAIN CERTIFIÉE' if all_ok else '⚠️ certification incomplète'} "
          f"— {time.time()-t0:.1f}s — preuves → {OUT}")
    await s.close()


if __name__ == "__main__":
    asyncio.run(main())

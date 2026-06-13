#!/usr/bin/env python3
"""draw-figure — barreau « cerveau » (recette SketchAgent).

Un programme de traits (DSL) — émis par un LLM, ici par Claude — est tracé par
la MAIN certifiée (draw_lab) sur la toile, puis capturé. Format open-vocabulary :
le même DSL dessine un cheval, un chat, une maison… il suffit de changer le
programme.

DSL : liste d'ops, chacune = un trait (pen-down → pen-up) :
  {"op":"line","a":[x,y],"b":[x,y]}
  {"op":"polyline","pts":[[x,y],...],"close":bool}
  {"op":"circle","c":[x,y],"r":r}
  {"op":"ellipse","c":[x,y],"r":[rx,ry],"rot":deg}
  {"op":"arc","c":[x,y],"r":r,"a":[deg0,deg1]}
  {"op":"cubic","p":[[x,y]*4]}

  python3 draw_figure.py <nom>      # rend le programme nommé → .state/draw/fig_<nom>.png
"""
from __future__ import annotations

import asyncio
import base64
import math
import sys
from pathlib import Path

from cdp_session import CDPSession
from draw_lab import (CANVAS_URL, OUT, flatten_line, flatten_polyline,
                      flatten_circle, flatten_arc, flatten_cubic, draw_stroke, warm_up)


def flatten_ellipse(cx, cy, rx, ry, rot_deg=0.0, step=4.0):
    rot = math.radians(rot_deg)
    cr, sr = math.cos(rot), math.sin(rot)
    circ = 2 * math.pi * max(rx, ry)
    n = max(24, int(circ / step))
    out = []
    for i in range(n + 1):
        t = 2 * math.pi * i / n
        ex, ey = rx * math.cos(t), ry * math.sin(t)
        out.append((cx + ex * cr - ey * sr, cy + ex * sr + ey * cr))
    return out


def op_to_points(op):
    k = op["op"]
    if k == "line":
        return flatten_line(op["a"], op["b"])
    if k == "polyline":
        pts = [tuple(p) for p in op["pts"]]
        if op.get("close"):
            pts = pts + [pts[0]]
        return flatten_polyline(pts)
    if k == "circle":
        return flatten_circle(op["c"][0], op["c"][1], op["r"])
    if k == "ellipse":
        rx, ry = op["r"]
        return flatten_ellipse(op["c"][0], op["c"][1], rx, ry, op.get("rot", 0.0))
    if k == "arc":
        return flatten_arc(op["c"][0], op["c"][1], op["r"], op["a"][0], op["a"][1])
    if k == "cubic":
        p = op["p"]
        return flatten_cubic(p[0], p[1], p[2], p[3])
    raise ValueError(f"op inconnue: {k}")


async def render(program, name, show=False):
    s = CDPSession(headless=not show, width=1040, height=700)
    s.launch_chrome()
    await s.connect()
    await s.navigate(CANVAS_URL)
    if not await s.wait_for("window.__ready === true", timeout=12):
        print("✗ toile non chargée"); await s.close(); return
    await warm_up(s)
    await s.eval("window.__clear()")
    for op in program:
        await draw_stroke(s, op_to_points(op))
    await s.eval("1")
    res = await s.send("Page.captureScreenshot", {"format": "png"})
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"fig_{name}.png"
    path.write_bytes(base64.b64decode(res["data"]))
    print(f"✓ {name}: {len(program)} traits → {path}")
    await s.close()


# ----------------------------------------------------------------- programmes ---
# Cheval de profil (regarde à droite). Écrit par le LLM (Claude), itéré au vu du rendu.
HORSE = [
    {"op": "ellipse", "c": [462, 350], "r": [170, 60]},                     # corps (allongé)
    {"op": "polyline", "pts": [[598, 312], [664, 198], [694, 210], [618, 362]], "close": True},  # encolure
    {"op": "ellipse", "c": [710, 196], "r": [58, 32], "rot": -24},          # tête
    {"op": "polyline", "pts": [[750, 178], [772, 188], [752, 206]], "close": False},  # museau
    {"op": "polyline", "pts": [[678, 168], [686, 146], [700, 170]], "close": True},   # oreille
    {"op": "circle", "c": [716, 188], "r": 4},                              # œil
    {"op": "polyline", "pts": [[628, 350], [646, 300], [660, 250], [676, 210]], "close": False},  # crinière
    {"op": "line", "a": [372, 405], "b": [366, 522]},                       # patte AV gauche
    {"op": "line", "a": [414, 408], "b": [410, 524]},                       # patte AV droite
    {"op": "line", "a": [536, 408], "b": [544, 522]},                       # patte AR gauche
    {"op": "line", "a": [578, 405], "b": [588, 524]},                       # patte AR droite
    {"op": "line", "a": [358, 522], "b": [376, 522]},                       # sabots
    {"op": "line", "a": [402, 524], "b": [420, 524]},
    {"op": "line", "a": [536, 522], "b": [554, 522]},
    {"op": "line", "a": [580, 524], "b": [598, 524]},
    {"op": "cubic", "p": [[296, 330], [256, 370], [300, 440], [262, 478]]},  # queue
    {"op": "cubic", "p": [[298, 342], [276, 384], [306, 436], [286, 470]]},  # queue (mèche)
]

# Maison — prouve l'open-vocabulary : même DSL, même main, sujet tout autre.
HOUSE = [
    {"op": "polyline", "pts": [[360, 300], [660, 300], [660, 500], [360, 500]], "close": True},  # murs
    {"op": "polyline", "pts": [[338, 300], [510, 178], [682, 300]], "close": False},             # toit
    {"op": "polyline", "pts": [[470, 500], [470, 396], [560, 396], [560, 500]], "close": False}, # porte
    {"op": "circle", "c": [548, 450], "r": 5},                                                   # poignée
    {"op": "polyline", "pts": [[392, 336], [452, 336], [452, 392], [392, 392]], "close": True},  # fenêtre G
    {"op": "line", "a": [422, 336], "b": [422, 392]},
    {"op": "line", "a": [392, 364], "b": [452, 364]},
    {"op": "polyline", "pts": [[574, 336], [634, 336], [634, 392], [574, 392]], "close": True},  # fenêtre D
    {"op": "line", "a": [604, 336], "b": [604, 392]},
    {"op": "line", "a": [574, 364], "b": [634, 364]},
    {"op": "polyline", "pts": [[600, 250], [600, 206], [632, 206], [632, 272]], "close": False}, # cheminée
    {"op": "circle", "c": [840, 132], "r": 36},                                                  # soleil
    {"op": "line", "a": [840, 78], "b": [840, 60]},
    {"op": "line", "a": [792, 96], "b": [778, 84]},
    {"op": "line", "a": [888, 96], "b": [902, 84]},
    {"op": "line", "a": [786, 132], "b": [766, 132]},
]

# Cheval v2 — raffiné via le critique CLIP (réduire la confusion « vache » :
# corps plus élancé, pattes plus longues/fines, crinière et queue marquées).
HORSE2 = [
    {"op": "ellipse", "c": [468, 348], "r": [184, 48]},                     # corps élancé
    {"op": "polyline", "pts": [[602, 322], [668, 194], [700, 206], [624, 360]], "close": True},  # encolure
    {"op": "ellipse", "c": [718, 192], "r": [56, 29], "rot": -27},          # tête fine
    {"op": "polyline", "pts": [[758, 176], [780, 186], [760, 204]], "close": False},  # museau
    {"op": "polyline", "pts": [[684, 162], [692, 140], [706, 164]], "close": True},   # oreille
    {"op": "circle", "c": [724, 184], "r": 4},                              # œil
    {"op": "polyline", "pts": [[624, 356], [640, 318], [652, 282], [664, 246], [676, 212], [688, 192]], "close": False},  # crinière
    {"op": "line", "a": [368, 398], "b": [360, 542]},                       # pattes longues fines
    {"op": "line", "a": [412, 400], "b": [406, 544]},
    {"op": "line", "a": [540, 400], "b": [550, 542]},
    {"op": "line", "a": [586, 396], "b": [598, 544]},
    {"op": "line", "a": [350, 544], "b": [370, 544]},                       # sabots
    {"op": "line", "a": [396, 546], "b": [416, 546]},
    {"op": "line", "a": [540, 544], "b": [560, 544]},
    {"op": "line", "a": [588, 546], "b": [608, 546]},
    {"op": "cubic", "p": [[288, 330], [244, 372], [296, 452], [256, 502]]},  # queue fournie
    {"op": "cubic", "p": [[290, 344], [262, 392], [300, 452], [282, 496]]},
    {"op": "cubic", "p": [[286, 338], [250, 390], [284, 448], [262, 488]]},
]

PROGRAMS = {"horse": HORSE, "house": HOUSE, "horse2": HORSE2}
try:
    from draw_seeds import SEEDS
    PROGRAMS.update(SEEDS)
except Exception:
    pass


async def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "horse"
    show = "--show" in sys.argv
    prog = PROGRAMS.get(name)
    if not prog:
        print(f"programme inconnu: {name} (dispo: {list(PROGRAMS)})"); return
    await render(prog, name, show=show)


if __name__ == "__main__":
    asyncio.run(main())

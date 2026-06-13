#!/usr/bin/env python3
"""draw-live — démo PILOTÉE et VISIBLE : regarde-moi dessiner.

Ouvre une vraie fenêtre Chrome et trace le programme lentement, avec un
curseur-stylo rouge qui se déplace (pen-up entre les traits, pen-down pendant).
Le cerveau (le programme de traits) vient de draw_figure ; la main de draw_lab.

  python3 draw_live.py                 # cheval puis maison
  python3 draw_live.py horse           # juste le cheval
  python3 draw_live.py house horse cat # pilote l'ordre des sujets
"""
from __future__ import annotations

import asyncio
import sys

from cdp_session import CDPSession
from draw_lab import CANVAS_URL, warm_up, draw_stroke
from draw_figure import PROGRAMS, op_to_points

PACE = 0.012          # s/point pendant le tracé (regardable)
TRAVEL_STEPS = 14     # pas du déplacement pen-up entre deux traits


async def travel(s, frm, to):
    """Déplace le stylo (pen-up) de `frm` à `to`, visiblement."""
    x0, y0 = frm
    x1, y1 = to
    for i in range(1, TRAVEL_STEPS + 1):
        t = i / TRAVEL_STEPS
        await s._dispatch_mouse("mouseMoved", x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
        await asyncio.sleep(0.018)
    return to


async def draw_stroke_live(s, pts, cur):
    cur = await travel(s, cur, pts[0])
    x0, y0 = pts[0]
    await s._dispatch_mouse("mousePressed", x0, y0, button="left", buttons=1, clicks=1)
    await asyncio.sleep(0.03)
    for (x, y) in pts[1:]:
        await s._dispatch_mouse("mouseMoved", x, y, button="left", buttons=1)
        await asyncio.sleep(PACE)
    xe, ye = pts[-1]
    await s._dispatch_mouse("mouseReleased", xe, ye, button="left", buttons=1, clicks=1)
    await asyncio.sleep(0.09)
    return (xe, ye)


async def draw_program_live(s, program):
    cur = (40, 40)
    for op in program:
        cur = await draw_stroke_live(s, op_to_points(op), cur)


async def main():
    subjects = [a for a in sys.argv[1:] if not a.startswith("-")] or ["horse", "house"]
    subjects = [s for s in subjects if s in PROGRAMS] or ["horse"]

    s = CDPSession(headless=False, width=1040, height=720)
    print(f"· fenêtre Chrome visible — sujets : {', '.join(subjects)}", flush=True)
    s.launch_chrome()
    await s.connect()
    await s.navigate(CANVAS_URL)
    if not await s.wait_for("window.__ready === true", timeout=12):
        print("✗ toile non chargée"); await s.close(); return
    await warm_up(s)                       # amorce le pipeline (stylo caché)
    await s.eval("window.__clear()")
    await s.eval("window.__penShow(true)")
    await asyncio.sleep(2.0)               # laisse le temps de regarder

    for i, name in enumerate(subjects):
        print(f"  ✎ je dessine : {name}", flush=True)
        await draw_program_live(s, PROGRAMS[name])
        await asyncio.sleep(3.0)           # on admire
        if i < len(subjects) - 1:
            await s.eval("window.__clear()")
            await asyncio.sleep(0.6)

    print("· terminé — la fenêtre reste ouverte ~20s", flush=True)
    await asyncio.sleep(20.0)
    await s.close()


if __name__ == "__main__":
    asyncio.run(main())

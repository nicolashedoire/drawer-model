#!/usr/bin/env python3
"""draw-now — je dessine DEVANT TOI, en vrai, à la main (souris), en direct.

Pas de SVG, pas d'image qui apparaît : la main certifiée trace un programme de
traits DÉTAILLÉ, lentement, dans une fenêtre visible, avec le curseur-stylo.

  python3 draw_now.py            # dessine un chat détaillé, en direct
"""
from __future__ import annotations

import asyncio
import sys

from cdp_session import CDPSession
from draw_lab import CANVAS_URL, warm_up
from draw_live import draw_program_live

# Chat détaillé en LIGNE (tracé à la main) — contour lisse + détails.
CAT = [
    {"op": "cubic", "p": [[442, 300], [388, 358], [378, 432], [394, 500]]},   # flanc gauche
    {"op": "cubic", "p": [[394, 500], [440, 542], [560, 542], [606, 500]]},   # bas du corps
    {"op": "cubic", "p": [[606, 500], [622, 432], [612, 358], [558, 300]]},   # flanc droit
    {"op": "cubic", "p": [[474, 344], [456, 428], [470, 500], [500, 512]]},   # ventre gauche
    {"op": "cubic", "p": [[526, 344], [544, 428], [530, 500], [500, 512]]},   # ventre droit
    {"op": "cubic", "p": [[600, 452], [682, 446], [722, 386], [706, 322]]},   # queue (dessus)
    {"op": "cubic", "p": [[706, 322], [694, 366], [656, 404], [598, 476]]},   # queue (dessous)
    {"op": "polyline", "pts": [[452, 502], [452, 548], [460, 556], [482, 556], [490, 548], [490, 502]]},  # patte G
    {"op": "polyline", "pts": [[512, 502], [512, 548], [520, 556], [542, 556], [550, 548], [550, 502]]},  # patte D
    {"op": "line", "a": [464, 556], "b": [464, 548]}, {"op": "line", "a": [474, 556], "b": [474, 548]},
    {"op": "line", "a": [524, 556], "b": [524, 548]}, {"op": "line", "a": [534, 556], "b": [534, 548]},
    {"op": "circle", "c": [500, 206], "r": 102},                              # tête
    {"op": "polyline", "pts": [[430, 146], [412, 54], [498, 128]], "close": True},   # oreille G
    {"op": "polyline", "pts": [[570, 146], [588, 54], [502, 128]], "close": True},   # oreille D
    {"op": "polyline", "pts": [[438, 130], [428, 84], [470, 122]], "close": True},   # intérieur G
    {"op": "polyline", "pts": [[562, 130], [572, 84], [530, 122]], "close": True},   # intérieur D
    {"op": "ellipse", "c": [462, 200], "r": [27, 15]},                        # œil G
    {"op": "ellipse", "c": [538, 200], "r": [27, 15]},                        # œil D
    {"op": "circle", "c": [462, 200], "r": 8}, {"op": "circle", "c": [538, 200], "r": 8},  # pupilles
    {"op": "polyline", "pts": [[488, 236], [512, 236], [500, 251]], "close": True},  # nez
    {"op": "line", "a": [500, 251], "b": [500, 262]},
    {"op": "cubic", "p": [[500, 262], [488, 272], [478, 268], [470, 260]]},   # bouche G
    {"op": "cubic", "p": [[500, 262], [512, 272], [522, 268], [530, 260]]},   # bouche D
    {"op": "line", "a": [432, 228], "b": [350, 216]}, {"op": "line", "a": [434, 244], "b": [352, 248]},
    {"op": "line", "a": [432, 260], "b": [356, 274]},                         # moustaches G
    {"op": "line", "a": [568, 228], "b": [650, 216]}, {"op": "line", "a": [566, 244], "b": [648, 248]},
    {"op": "line", "a": [568, 260], "b": [644, 274]},                         # moustaches D
    {"op": "arc", "c": [500, 150], "r": 40, "a": [250, 290]},                 # rayure front
    {"op": "arc", "c": [418, 362], "r": 52, "a": [300, 352]},                 # rayure flanc G
    {"op": "arc", "c": [582, 362], "r": 52, "a": [188, 240]},                 # rayure flanc D
]

SUBJECTS = {"cat": ("un chat", CAT)}


async def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "cat"
    label, prog = SUBJECTS.get(name, SUBJECTS["cat"])
    s = CDPSession(headless=False, width=1040, height=730)
    print(f"· fenêtre visible — je dessine {label} ({len(prog)} traits)", flush=True)
    s.launch_chrome(); await s.connect(); await s.navigate(CANVAS_URL)
    if not await s.wait_for("window.__ready === true", timeout=12):
        print("✗ toile non chargée"); await s.close(); return
    await warm_up(s)
    await s.eval("window.__clear()"); await s.eval("window.__penShow(true)")
    await s.eval(f"window.__caption('je dessine {label} devant toi…')")
    await asyncio.sleep(1.5)
    await draw_program_live(s, prog)
    await s.eval(f"window.__caption('voilà {label} ✎')")
    print("· terminé — fenêtre ouverte ~20s", flush=True)
    await asyncio.sleep(20)
    await s.close()


if __name__ == "__main__":
    asyncio.run(main())

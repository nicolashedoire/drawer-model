#!/usr/bin/env python3
"""draw-loop — améliorations EN BOUCLE, en direct, devant toi.

Je redessine le sujet passe après passe, à la main, en ajoutant à chaque tour du
détail SENSÉ (pas du bruit) : marquages, poils, reflets, rayures. Tu vois le
dessin devenir meilleur, en continu, sans que je m'arrête pour demander.

  python3 draw_loop.py cat        # boucle d'améliorations du chat
  python3 draw_loop.py horse      # ... du cheval
  python3 draw_loop.py cat horse  # enchaîne plusieurs sujets sans s'arrêter
"""
from __future__ import annotations

import sys
import asyncio

from cdp_session import CDPSession
from draw_lab import CANVAS_URL, warm_up
from draw_live import draw_program_live
from draw_figure import PROGRAMS
from draw_now import CAT

# ----------------------------------------------------------------- CHAT ---
CAT_BASE = CAT[:-3]
CAT_G = [
    [{"op": "polyline", "pts": [[468, 172], [480, 150], [492, 170], [500, 154],
                                [508, 170], [520, 150], [532, 172]], "close": False}],
    [{"op": "line", "a": [446, 252], "b": [430, 266]}, {"op": "line", "a": [450, 262], "b": [434, 280]},
     {"op": "line", "a": [554, 252], "b": [570, 266]}, {"op": "line", "a": [550, 262], "b": [566, 280]},
     {"op": "line", "a": [490, 280], "b": [486, 292]}, {"op": "line", "a": [510, 280], "b": [514, 292]}],
    [{"op": "circle", "c": [458, 196], "r": 2.5}, {"op": "circle", "c": [534, 196], "r": 2.5},
     {"op": "line", "a": [495, 247], "b": [497, 250]}, {"op": "line", "a": [505, 247], "b": [503, 250]},
     {"op": "line", "a": [442, 122], "b": [454, 100]}, {"op": "line", "a": [558, 122], "b": [546, 100]}],
    [{"op": "cubic", "p": [[416, 356], [408, 376], [408, 398], [416, 418]]},
     {"op": "cubic", "p": [[440, 344], [434, 366], [434, 392], [442, 416]]},
     {"op": "cubic", "p": [[560, 344], [566, 366], [566, 392], [558, 416]]},
     {"op": "cubic", "p": [[584, 356], [592, 376], [592, 398], [584, 418]]},
     {"op": "arc", "c": [664, 402], "r": 30, "a": [206, 250]},
     {"op": "arc", "c": [694, 352], "r": 30, "a": [200, 248]}],
]
CAT_LABELS = ["contour net", "+ marquage du front", "+ poils aux joues",
              "+ reflets, narines, oreilles", "+ rayures corps & queue"]

# ----------------------------------------------------------------- CHEVAL ---
HORSE_BASE = PROGRAMS["horse2"]
HORSE_G = [
    [{"op": "line", "a": [610, 316], "b": [598, 300]}, {"op": "line", "a": [624, 290], "b": [610, 276]},
     {"op": "line", "a": [638, 262], "b": [624, 250]}, {"op": "line", "a": [652, 234], "b": [638, 222]},
     {"op": "line", "a": [664, 206], "b": [652, 196]}],                                   # crinière
    [{"op": "line", "a": [364, 470], "b": [372, 470]}, {"op": "line", "a": [408, 472], "b": [416, 472]},
     {"op": "line", "a": [544, 470], "b": [552, 470]}, {"op": "line", "a": [590, 470], "b": [598, 470]}],  # genoux
    [{"op": "cubic", "p": [[560, 312], [576, 330], [576, 360], [562, 382]]},              # muscle épaule
     {"op": "cubic", "p": [[372, 314], [356, 332], [356, 362], [372, 384]]},              # muscle croupe
     {"op": "line", "a": [300, 452], "b": [292, 482]}, {"op": "line", "a": [312, 452], "b": [306, 484]}],  # crins queue
    [{"op": "circle", "c": [742, 196], "r": 3},                                           # naseau
     {"op": "polyline", "pts": [[688, 186], [696, 162], [706, 184]], "close": False},     # toupet
     {"op": "line", "a": [360, 542], "b": [598, 542]}],                                   # sol
]
HORSE_LABELS = ["silhouette", "+ crinière", "+ genoux/jarrets",
                "+ muscles & crins", "+ naseau, toupet, sol"]


def stages(base, groups, labels):
    acc, out = list(base), []
    for i, g in enumerate([[]] + groups):
        acc = acc + g
        out.append((labels[i], list(acc)))
    return out


SUBJECTS = {
    "cat": stages(CAT_BASE, CAT_G, CAT_LABELS),
    "horse": stages(HORSE_BASE, HORSE_G, HORSE_LABELS),
}
FR = {"cat": "le chat", "horse": "le cheval"}


async def main():
    subs = [a for a in sys.argv[1:] if not a.startswith("-")] or ["cat"]
    subs = [s for s in subs if s in SUBJECTS] or ["cat"]
    s = CDPSession(headless=False, width=1040, height=730)
    print(f"· fenêtre visible — boucle d'améliorations : {', '.join(subs)}", flush=True)
    s.launch_chrome(); await s.connect(); await s.navigate(CANVAS_URL)
    if not await s.wait_for("window.__ready === true", timeout=12):
        print("✗ toile non chargée"); await s.close(); return
    await warm_up(s)
    await s.eval("window.__penShow(true)")

    for sub in subs:
        for i, (label, prog) in enumerate(SUBJECTS[sub], 1):
            await s.eval("window.__clear()")
            await s.eval(f"window.__caption('{FR[sub]} — amélioration #{i} : {label} ({len(prog)} traits)')")
            print(f"  {sub} passe {i}: {label} ({len(prog)} traits)", flush=True)
            await asyncio.sleep(0.6)
            await draw_program_live(s, prog)
            await asyncio.sleep(2.0)

    await s.eval("window.__caption('améliorations terminées ✎ — la boucle peut continuer')")
    print("· terminé — fenêtre ouverte ~15s", flush=True)
    await asyncio.sleep(15)
    await s.close()


if __name__ == "__main__":
    asyncio.run(main())

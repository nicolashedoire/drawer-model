#!/usr/bin/env python3
"""draw-agent — l'AGENT AUTONOME QUI S'AUTO-AMÉLIORE.

Pour une demande, il part d'une ébauche (récupérée), puis s'améliore tout seul :
chaque tour il propose des MUTATIONS — affiner des points, courber une ligne,
AJOUTER un petit trait de détail — les juge avec CLIP sous le garde anti-triche
(encre bornée, nb de traits plafonné, ancrage à l'ébauche), et garde ce qui
monte. Il accumule du détail au fil des tours → moins enfantin.

  python3 draw_agent.py cat --rounds 50
  python3 draw_agent.py "un chat" --rounds 50 --live   # rejoue l'amélioration en visible
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import copy
import io
import json
import random
from pathlib import Path

from PIL import Image

from cdp_session import CDPSession
from draw_lab import CANVAS_URL, OUT, warm_up, draw_stroke
from draw_figure import PROGRAMS, op_to_points
from draw_learn import Renderer, drift, extract_points, INK_LO, INK_HI, LAMBDA
from draw_live import draw_program_live
import draw_critic

AGENTS = OUT / "agent"
MAX_ADD = 10                 # traits de détail ajoutables au-delà de l'ébauche
CANDS = 6                    # mutations proposées par tour


def _pt(prog, rng):
    pts = extract_points(prog)
    return list(rng.choice(pts)) if pts else [500, 320]


def mut_jitter(prog, rng):
    from draw_learn import perturb
    return perturb(prog, rng.uniform(3, 7), rng, frac=0.35)


def mut_add_detail(prog, n_seed, rng):
    """Ajoute un petit trait près de la structure existante (si sous le plafond)."""
    if len(prog) >= n_seed + MAX_ADD:
        return None
    p = copy.deepcopy(prog)
    x, y = _pt(prog, rng)
    L = rng.uniform(14, 46)
    a = rng.uniform(0, 6.283)
    import math
    dx, dy = L * math.cos(a), L * math.sin(a)
    kind = rng.random()
    if kind < 0.5:
        p.append({"op": "line", "a": [x, y], "b": [x + dx, y + dy]})
    elif kind < 0.8:
        p.append({"op": "cubic", "p": [[x, y], [x + dx * .4, y + dy * .4 - 12],
                                       [x + dx * .7, y + dy * .7 + 12], [x + dx, y + dy]]})
    else:
        p.append({"op": "circle", "c": [x, y], "r": rng.uniform(4, 9)})
    return p


def mut_curve(prog, rng):
    """Transforme une ligne droite en légère courbe (plus organique)."""
    idx = [i for i, op in enumerate(prog) if op["op"] == "line"]
    if not idx:
        return None
    p = copy.deepcopy(prog)
    i = rng.choice(idx)
    a, b = p[i]["a"], p[i]["b"]
    import math
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    nx, ny = -(b[1] - a[1]), (b[0] - a[0])
    nl = math.hypot(nx, ny) or 1
    off = rng.uniform(-22, 22)
    cx, cy = mx + nx / nl * off, my + ny / nl * off
    p[i] = {"op": "cubic", "p": [a, [(a[0] + cx) / 2, (a[1] + cy) / 2],
                                 [(b[0] + cx) / 2, (b[1] + cy) / 2], b]}
    return p


def mutate(prog, n_seed, rng):
    roll = rng.random()
    if roll < 0.45:
        return mut_jitter(prog, rng)
    if roll < 0.78:
        return mut_add_detail(prog, n_seed, rng)
    return mut_curve(prog, rng)


def guard_ok(prog, n_seed, ink, ink0):
    if len(prog) > n_seed + MAX_ADD:
        return False
    if ink0 > 0 and not (INK_LO * ink0 <= ink <= INK_HI * ink0 * 1.25):
        return False
    return True


def obj_of(prog, seed, p):
    seed_part = prog[:len(seed)]
    return p - LAMBDA * drift(seed_part, seed)


async def improve(r, subject, seed_prog, rounds, rng):
    seed = copy.deepcopy(seed_prog)
    n_seed = len(seed)
    img0, ink0 = await r.render_reliable(seed)
    p0, _, _ = draw_critic.score(img0, subject)
    best, best_p, best_obj = seed, p0, p0
    checkpoints = [(copy.deepcopy(best), round(best_p, 3))]
    print(f"· ébauche « {subject} » → P={p0:.3f}  ({n_seed} traits, encre {int(ink0)})", flush=True)

    for rd in range(1, rounds + 1):
        improved = False
        for _ in range(CANDS):
            cand = mutate(best, n_seed, rng)
            if cand is None:
                continue
            img, ink = await r.render(cand)
            if not guard_ok(cand, n_seed, ink, ink0):
                continue
            p, _, _ = draw_critic.score(img, subject)
            o = obj_of(cand, seed, p)
            if o > best_obj + 1e-4:
                best, best_p, best_obj = cand, p, o
                improved = True
        if improved or rd % 10 == 0:
            checkpoints.append((copy.deepcopy(best), round(best_p, 3)))
            print(f"  tour {rd:3}  P={best_p:.3f}  traits={len(best)}", flush=True)
    return best, best_p, p0, checkpoints


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("subject")
    ap.add_argument("--rounds", type=int, default=50)
    ap.add_argument("--live", action="store_true")
    a = ap.parse_args()

    # demande → sujet (récupération si ce n'est pas déjà un nom de graine)
    if a.subject in PROGRAMS:
        subject, seed_prog = a.subject, PROGRAMS[a.subject]
    else:
        from draw_model import DrawModel, load_corpus
        m = DrawModel(load_corpus())
        subject, sim, _ = m.understand(a.subject)
        seed_prog = m.programs[subject]
        print(f"· « {a.subject} » → sujet {subject} (sim {sim:.2f})", flush=True)

    rng = random.Random(42)
    draw_critic._load()
    s = CDPSession(headless=not a.live, width=1040, height=730)
    s.launch_chrome(); await s.connect(); await s.navigate(CANVAS_URL)
    await s.wait_for("window.__ready === true", timeout=12); await warm_up(s)
    r = Renderer(s)

    best, best_p, p0, checks = await improve(r, subject, seed_prog, a.rounds, rng)

    AGENTS.mkdir(parents=True, exist_ok=True)
    (AGENTS / f"{subject}.json").write_text(json.dumps(
        {"subject": subject, "score": round(best_p, 4), "from": round(p0, 4), "program": best},
        ensure_ascii=False, indent=2), encoding="utf-8")
    img, _ = await r.render(best)
    img.save(AGENTS / f"{subject}_after.png")
    ib, _ = await r.render(seed_prog)
    ib.save(AGENTS / f"{subject}_before.png")
    print(f"\n✅ {subject} : {p0:.3f} → {best_p:.3f}  ({len(seed_prog)}→{len(best)} traits)  → {AGENTS}", flush=True)

    if a.live:
        await s.eval("window.__penShow(true)")
        for prog, sc in checks:
            await s.eval(f"window.__caption({json.dumps(f'auto-amélioration {subject} — P={sc}')})")
            await s.eval("window.__clear()")
            await draw_program_live(s, prog)
            await asyncio.sleep(1.2)
        await s.eval(f"window.__caption({json.dumps(f'{subject} : {p0:.2f} → {best_p:.2f} en autonomie')})")
        await asyncio.sleep(8)
    await s.close()


if __name__ == "__main__":
    asyncio.run(main())

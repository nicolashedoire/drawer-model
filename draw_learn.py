#!/usr/bin/env python3
"""draw-learn — la MACHINE D'APPRENTISSAGE (optimiseur de traits guidé par CLIP).

Part d'un programme-graine (écrit par le cerveau/LLM) et le RAFFINE tout seul :
à chaque pas, on perturbe les coordonnées, on redessine, CLIP juge « ressemble à
X ? », on garde si ça monte (recuit simulé léger). Sans gradient (l'exécuteur
n'est pas différentiable) → optimisation boîte-noire, 100 % local.

Produit le corpus de distillation : .state/draw/learned/<sujet>.json
  = {subject, program, score, history}  → matière du modèle final prompt→programme.

  python3 draw_learn.py horse --iters 150
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import copy
import io
import json
import math
import random
from pathlib import Path

from PIL import Image

from cdp_session import CDPSession
from draw_lab import CANVAS_URL, OUT, warm_up, draw_stroke
from draw_figure import PROGRAMS, op_to_points
import draw_critic

LEARNED = OUT / "learned"
COORD_KEYS = ("a", "b", "c", "pts", "p")     # champs contenant des coordonnées


def _jitter_value(v, sigma, rng):
    return v + rng.gauss(0, sigma)


def perturb(program, sigma, rng, frac=0.5):
    """Copie le programme en bougeant une fraction de ses coordonnées de ~sigma px."""
    prog = copy.deepcopy(program)
    for op in prog:
        for k in COORD_KEYS:
            if k not in op:
                continue
            val = op[k]
            if isinstance(val[0], (int, float)):                 # paire [x,y]
                if rng.random() < frac:
                    op[k] = [_jitter_value(val[0], sigma, rng), _jitter_value(val[1], sigma, rng)]
            else:                                                # liste de paires
                op[k] = [[_jitter_value(p[0], sigma, rng) if rng.random() < frac else p[0],
                          _jitter_value(p[1], sigma, rng) if rng.random() < frac else p[1]] for p in val]
        if "r" in op and isinstance(op["r"], list) and rng.random() < frac:    # ellipse [rx,ry]
            op["r"] = [max(6, _jitter_value(op["r"][0], sigma, rng)), max(6, _jitter_value(op["r"][1], sigma, rng))]
        elif "r" in op and isinstance(op["r"], (int, float)) and rng.random() < frac:
            op["r"] = max(2, _jitter_value(op["r"], sigma * 0.5, rng))
    return prog


class Renderer:
    def __init__(self, session):
        self.s = session

    async def render(self, program) -> Image.Image:
        await self.s.eval("window.__clear()")
        for op in program:
            await draw_stroke(self.s, op_to_points(op))
        await self.s.eval("1")
        res = await self.s.send("Page.captureScreenshot", {"format": "png"})
        return Image.open(io.BytesIO(base64.b64decode(res["data"]))).convert("RGB")


async def learn(subject, seed_name, iters, seed=7):
    rng = random.Random(seed)
    program = PROGRAMS[seed_name]
    s = CDPSession(headless=True, width=1040, height=700)
    s.launch_chrome(); await s.connect(); await s.navigate(CANVAS_URL)
    await s.wait_for("window.__ready === true", timeout=12)
    await warm_up(s)
    r = Renderer(s)

    best = copy.deepcopy(program)
    best_score, _, _ = draw_critic.score(await r.render(best), subject)
    history = [round(best_score, 4)]
    print(f"· graine « {seed_name} » → P({subject})={best_score:.3f}", flush=True)

    for i in range(1, iters + 1):
        sigma = 14 * (1 - i / iters) + 3                  # recuit : 17 → 3 px
        cand = perturb(best, sigma, rng)
        sc, _, _ = draw_critic.score(await r.render(cand), subject)
        # accept-if-better + petite tolérance de recuit pour s'échapper des plateaux
        T = 0.02 * (1 - i / iters)
        if sc > best_score or rng.random() < math.exp(min(0, (sc - best_score)) / max(T, 1e-6)) * 0.15:
            if sc > best_score - 1e-4:
                best, best_score = cand, max(best_score, sc)
        if i % 10 == 0:
            history.append(round(best_score, 4))
            print(f"  pas {i:3}  σ={sigma:4.1f}  meilleur P={best_score:.3f}", flush=True)

    LEARNED.mkdir(parents=True, exist_ok=True)
    (LEARNED / f"{subject}.json").write_text(json.dumps(
        {"subject": subject, "score": round(best_score, 4), "program": best, "history": history},
        ensure_ascii=False, indent=2), encoding="utf-8")
    img = await r.render(best)
    img.save(LEARNED / f"{subject}.png")
    print(f"\n✅ {subject} : {history[0]:.3f} → {best_score:.3f}  → {LEARNED/(subject+'.json')}", flush=True)
    await s.close()
    return best_score


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("subject")
    ap.add_argument("--seed-name", default=None, help="programme-graine (défaut = subject)")
    ap.add_argument("--iters", type=int, default=150)
    a = ap.parse_args()
    seed_name = a.seed_name or a.subject
    if seed_name not in PROGRAMS:
        print(f"pas de graine pour « {seed_name} » (dispo: {list(PROGRAMS)})"); return
    await learn(a.subject, seed_name, a.iters)


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""draw-learn — la MACHINE D'APPRENTISSAGE, avec garde ANTI-ADVERSARIAL.

Part d'un programme-graine et le raffine : perturbe les coordonnées, redessine,
CLIP juge, on garde si l'OBJECTIF monte. L'objectif n'est PAS le score CLIP brut
(qui se laisse berner par des gribouillis) mais :

    objectif = P_clip(sujet) − λ · dérive(programme, graine)

plus (a) un rendu de graine fiabilisé (anti rendu-vide-à-froid),
(b) une garde d'encre (rejet si la quantité de trait explose/s'effondre),
(c) des perturbations bridées. CLIP affine sans pouvoir tricher.

  python3 draw_learn.py horse --iters 120
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
COORD_KEYS = ("a", "b", "c", "pts", "p")
CANVAS_DIAG = math.hypot(1000, 640)
LAMBDA = 0.6                  # poids de l'ancrage structurel (anti-dérive)
SIGMA_HI, SIGMA_LO = 7.0, 2.0
INK_LO, INK_HI = 0.55, 1.8   # bornes admises sur le ratio d'encre vs graine


def extract_points(program):
    pts = []
    for op in program:
        for k in COORD_KEYS:
            if k not in op:
                continue
            v = op[k]
            if isinstance(v[0], (int, float)):
                pts.append((v[0], v[1]))
            else:
                pts.extend((p[0], p[1]) for p in v)
    return pts


def drift(program, seed):
    a, b = extract_points(program), extract_points(seed)
    if not a or len(a) != len(b):
        return 0.0
    d = sum(math.hypot(ax - bx, ay - by) for (ax, ay), (bx, by) in zip(a, b)) / len(a)
    return d / CANVAS_DIAG          # 0..~1


def perturb(program, sigma, rng, frac=0.4):
    prog = copy.deepcopy(program)
    j = lambda v: v + rng.gauss(0, sigma)
    for op in prog:
        for k in COORD_KEYS:
            if k not in op:
                continue
            v = op[k]
            if isinstance(v[0], (int, float)):
                if rng.random() < frac:
                    op[k] = [j(v[0]), j(v[1])]
            else:
                op[k] = [[j(p[0]) if rng.random() < frac else p[0],
                          j(p[1]) if rng.random() < frac else p[1]] for p in v]
        if "r" in op and isinstance(op["r"], list) and rng.random() < frac:
            op["r"] = [max(6, j(op["r"][0])), max(6, j(op["r"][1]))]
    return prog


class Renderer:
    def __init__(self, session):
        self.s = session

    async def render(self, program):
        await self.s.eval("window.__clear()")
        for op in program:
            await draw_stroke(self.s, op_to_points(op))
        await self.s.eval("1")
        ink = await self.s.eval("window.__paintedPixels(2).length/2") or 0
        res = await self.s.send("Page.captureScreenshot", {"format": "png"})
        img = Image.open(io.BytesIO(base64.b64decode(res["data"]))).convert("RGB")
        return img, float(ink)

    async def render_reliable(self, program, tries=3):
        """Anti rendu-vide-à-froid : re-tente si l'encre est anormalement basse."""
        best = None
        for _ in range(tries):
            img, ink = await self.render(program)
            if best is None or ink > best[1]:
                best = (img, ink)
            if ink > 150:
                return best
            await warm_up(self.s)
        return best


async def learn(subject, seed_name, iters, seed=7):
    rng = random.Random(seed)
    program = copy.deepcopy(PROGRAMS[seed_name])
    s = CDPSession(headless=True, width=1040, height=700)
    s.launch_chrome(); await s.connect(); await s.navigate(CANVAS_URL)
    await s.wait_for("window.__ready === true", timeout=12)
    await warm_up(s)
    r = Renderer(s)

    img0, ink0 = await r.render_reliable(program)
    p0, _, _ = draw_critic.score(img0, subject)
    best, best_p, best_obj = program, p0, p0
    history = [round(p0, 4)]
    print(f"· graine « {seed_name} » → P({subject})={p0:.3f}  (encre {int(ink0)})", flush=True)

    for i in range(1, iters + 1):
        sigma = SIGMA_HI * (1 - i / iters) + SIGMA_LO
        cand = perturb(best, sigma, rng)
        img, ink = await r.render(cand)
        if ink0 > 0 and not (INK_LO * ink0 <= ink <= INK_HI * ink0):
            continue                                   # garde d'encre
        p, _, _ = draw_critic.score(img, subject)
        obj = p - LAMBDA * drift(cand, program)        # ancrage à la GRAINE
        if obj > best_obj:
            best, best_p, best_obj = cand, p, obj
        if i % 15 == 0:
            history.append(round(best_p, 4))
            print(f"  pas {i:3}  σ={sigma:3.1f}  P={best_p:.3f}  dérive={drift(best, program):.3f}", flush=True)

    LEARNED.mkdir(parents=True, exist_ok=True)
    (LEARNED / f"{subject}.json").write_text(json.dumps(
        {"subject": subject, "score": round(best_p, 4), "program": best, "history": history},
        ensure_ascii=False, indent=2), encoding="utf-8")
    img, _ = await r.render(best)
    img.save(LEARNED / f"{subject}.png")
    print(f"\n✅ {subject} : {p0:.3f} → {best_p:.3f} (dérive {drift(best, program):.3f}) "
          f"→ {LEARNED/(subject+'.json')}", flush=True)
    await s.close()
    return best_p


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("subject")
    ap.add_argument("--seed-name", default=None)
    ap.add_argument("--iters", type=int, default=120)
    a = ap.parse_args()
    seed_name = a.seed_name or a.subject
    if seed_name not in PROGRAMS:
        print(f"pas de graine « {seed_name} » (dispo: {list(PROGRAMS)})"); return
    await learn(a.subject, seed_name, a.iters)


if __name__ == "__main__":
    asyncio.run(main())

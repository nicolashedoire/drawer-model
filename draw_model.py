#!/usr/bin/env python3
"""draw-model — LE MODÈLE : comprend la demande, choisit, et dessine.

Modèle de récupération sémantique : la demande (FR ou EN) est embarquée par
l'encodeur de texte CLIP, comparée au corpus appris, et le sujet le plus proche
est dessiné par la main certifiée. « Comprend la demande » (embeddings, gère
synonymes/paraphrases/2 langues) → « dessine » (exécute le programme appris).

Au fur et à mesure que le corpus grossit (via draw_corpus), le modèle couvre
plus de sujets. C'est l'étape avant la distillation générative.

  python3 draw_model.py "dessine-moi un poney"
  python3 draw_model.py --live "un chaton" "une automobile" "le soleil"
"""
from __future__ import annotations

import asyncio
import json
import sys

import torch

from cdp_session import CDPSession
from draw_lab import CANVAS_URL, OUT, warm_up
from draw_figure import PROGRAMS
from draw_live import draw_program_live
import draw_critic

LEARNED = OUT / "learned"
# étiquettes bilingues par sujet (le « vocabulaire » que le modèle comprend)
LABELS = {
    "horse": ["a horse", "un cheval", "a pony", "un poney"],
    "house": ["a house", "une maison", "a home"],
    "sun": ["the sun", "un soleil", "sunshine"],
    "star": ["a star", "une étoile"],
    "tree": ["a tree", "un arbre", "un sapin", "a fir tree"],
    "flower": ["a flower", "une fleur", "a tulip"],
    "fish": ["a fish", "un poisson"],
    "sailboat": ["a sailboat", "un voilier", "un bateau", "a boat"],
    "cat": ["a cat", "un chat", "a kitten", "un chaton"],
    "umbrella": ["an umbrella", "un parapluie"],
    "ladder": ["a ladder", "une échelle"],
    "car": ["a car", "une voiture", "une automobile", "a vehicle"],
}


def load_corpus():
    """Retourne {subject: program}, en préférant le programme APPRIS s'il existe."""
    corpus = {}
    for sub in LABELS:
        f = LEARNED / f"{sub}.json"
        if f.exists():
            corpus[sub] = json.loads(f.read_text(encoding="utf-8"))["program"]
        elif sub in PROGRAMS:
            corpus[sub] = PROGRAMS[sub]
    return corpus


class DrawModel:
    def __init__(self, corpus):
        self.subjects = list(corpus)
        self.programs = corpus
        variants, owner = [], []
        for sub in self.subjects:
            for lab in LABELS[sub]:
                variants.append(lab); owner.append(sub)
        self.variants, self.owner = variants, owner
        self.var_emb = draw_critic.embed_texts(variants)        # (V, D)

    def understand(self, prompt):
        """Demande → (sujet, similarité, top-3)."""
        q = draw_critic.embed_texts([prompt])                   # (1, D)
        sims = (q @ self.var_emb.T)[0]                          # cos par variante
        best = {}
        for s, sub in zip(sims.tolist(), self.owner):
            best[sub] = max(best.get(sub, -1), s)
        ranked = sorted(best.items(), key=lambda x: -x[1])
        return ranked[0][0], ranked[0][1], ranked[:3]


async def draw_for(model, prompts, live):
    s = CDPSession(headless=not live, width=1040, height=730)
    s.launch_chrome(); await s.connect(); await s.navigate(CANVAS_URL)
    await s.wait_for("window.__ready === true", timeout=12); await warm_up(s)
    await s.eval("window.__penShow(true)" if live else "1")
    if live:
        await asyncio.sleep(1.2)
    for prompt in prompts:
        sub, sim, top3 = model.understand(prompt)
        top_str = ", ".join(f"{t}={v:.2f}" for t, v in top3)
        print(f"  « {prompt} » → {sub}  (sim {sim:.2f} | {top_str})", flush=True)
        if live:
            await s.eval(f"window.__caption({json.dumps(f'« {prompt} » → je dessine : {sub}')})")
        await s.eval("window.__clear()")
        await draw_program_live(s, model.programs[sub]) if live else None
        if not live:
            from draw_lab import draw_stroke
            from draw_figure import op_to_points
            for op in model.programs[sub]:
                await draw_stroke(s, op_to_points(op))
            await s.eval("1")
        await asyncio.sleep(3.5 if live else 0.2)
    if live:
        await asyncio.sleep(8)
    await s.close()


async def main():
    args = sys.argv[1:]
    live = "--live" in args
    prompts = [a for a in args if not a.startswith("-")] or ["dessine-moi un poney"]
    print("· chargement du modèle (corpus + encodeur CLIP)…", flush=True)
    model = DrawModel(load_corpus())
    print(f"· vocabulaire : {len(model.subjects)} sujets — {', '.join(model.subjects)}\n", flush=True)
    await draw_for(model, prompts, live)


if __name__ == "__main__":
    asyncio.run(main())

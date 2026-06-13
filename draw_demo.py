#!/usr/bin/env python3
"""draw-demo — la démo live COMPLÈTE : je dessine, puis CLIP juge mon dessin.

Fenêtre visible. Pour chaque sujet : tracé lent (curseur-stylo rouge), puis le
critique CLIP note le dessin et le verdict s'affiche sous la toile. Utilise les
MEILLEURS programmes (cheval appris à 0.98, maison). Montre la chaîne entière :
cerveau → main certifiée → critique, en direct.

  python3 draw_demo.py
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
from pathlib import Path

from PIL import Image

from cdp_session import CDPSession
from draw_lab import CANVAS_URL, OUT, warm_up
from draw_figure import PROGRAMS
from draw_live import draw_program_live
import draw_critic

LEARNED = OUT / "learned"
FR = {"horse": "un cheval", "house": "une maison", "cat": "un chat",
      "tree": "un arbre", "fish": "un poisson", "boat": "un bateau"}


def load_program(name):
    f = LEARNED / f"{name}.json"
    if f.exists():
        d = json.loads(f.read_text(encoding="utf-8"))
        return d["program"], d.get("score")
    return PROGRAMS.get(name), None


async def clean_score(s, subject):
    """Capture une toile PROPRE (sans stylo ni légende) pour un jugement CLIP non biaisé."""
    await s.eval("window.__penShow(false)")
    await s.eval("window.__caption('')")
    await asyncio.sleep(0.06)
    res = await s.send("Page.captureScreenshot", {"format": "png"})
    img = Image.open(io.BytesIO(base64.b64decode(res["data"]))).convert("RGB")
    p, ranking, _ = draw_critic.score(img, subject)
    await s.eval("window.__penShow(true)")
    return p, ranking


async def main():
    subjects = ["horse", "house"]
    print("· chargement du critique CLIP…", flush=True)
    draw_critic._load()                       # précharge CLIP avant d'ouvrir la fenêtre

    s = CDPSession(headless=False, width=1040, height=730)
    s.launch_chrome(); await s.connect(); await s.navigate(CANVAS_URL)
    if not await s.wait_for("window.__ready === true", timeout=12):
        print("✗ toile non chargée"); await s.close(); return
    await warm_up(s)
    await s.eval("window.__clear()"); await s.eval("window.__penShow(true)")
    await asyncio.sleep(1.5)

    for name in subjects:
        prog, _ = load_program(name)
        if not prog:
            continue
        await s.eval(f"window.__caption('✎ je dessine {FR.get(name, name)}…')")
        print(f"  ✎ {name}", flush=True)
        await draw_program_live(s, prog)
        await asyncio.sleep(0.4)
        await s.eval("window.__caption('🤔 CLIP regarde mon dessin…')")
        await asyncio.sleep(0.4)
        p, ranking = await clean_score(s, name)
        top, second = ranking[0], ranking[1]
        ok = "✓" if top[0] == name and p >= 0.5 else "?"
        verdict = (f"CLIP : {FR.get(name, name)} {p*100:.0f}% {ok}   "
                   f"(2e : {second[0]} {second[1]*100:.0f}%)")
        await s.eval(f"window.__caption({json.dumps(verdict)})")
        print(f"     {verdict}", flush=True)
        await asyncio.sleep(4.5)
        await s.eval("window.__clear()"); await asyncio.sleep(0.5)

    await s.eval("window.__caption('✅ cerveau → main certifiée → critique CLIP — 100% local')")
    print("· démo terminée — fenêtre ouverte ~18s", flush=True)
    await asyncio.sleep(18.0)
    await s.close()


if __name__ == "__main__":
    asyncio.run(main())

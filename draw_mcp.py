#!/usr/bin/env python3
"""draw-mcp — la couche MCP du système de dessin.

Expose la MAIN (exécuteur de traits certifié), le CRITIQUE (CLIP) et la MACHINE
D'APPRENTISSAGE comme outils MCP, pour qu'un cerveau (un LLM agent, ou moi) pilote
le tout : dessiner un programme de traits, le faire juger, lancer un apprentissage,
lister/charger les compétences apprises.

Lancé par Claude Code via .mcp.json (python du venv agent-factory).
Tools : draw, critique, learn, list_skills, get_skill, save_skill.
"""
from __future__ import annotations

import base64
import io
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image
from mcp.server.fastmcp import FastMCP

from cdp_session import CDPSession
from draw_lab import CANVAS_URL, OUT, warm_up, draw_stroke
from draw_figure import PROGRAMS, op_to_points
import draw_critic

ROOT = Path(__file__).resolve().parent
LEARNED = OUT / "learned"
mcp = FastMCP("draw-lab")
_session = None


async def _get_session() -> CDPSession:
    global _session
    if _session is None:
        s = CDPSession(headless=True, width=1040, height=700,
                       port=9444, profile="/tmp/atlas-draw-mcp")   # port distinct de draw_learn
        s.launch_chrome()
        await s.connect()
        await s.navigate(CANVAS_URL)
        await s.wait_for("window.__ready === true", timeout=12)
        await warm_up(s)
        _session = s
    return _session


async def _render(prog) -> Image.Image:
    s = await _get_session()
    await s.eval("window.__clear()")
    for op in prog:
        await draw_stroke(s, op_to_points(op))
    await s.eval("1")
    res = await s.send("Page.captureScreenshot", {"format": "png"})
    return Image.open(io.BytesIO(base64.b64decode(res["data"]))).convert("RGB")


@mcp.tool()
async def draw(program: str, subject: str = "") -> dict:
    """Trace un programme de traits (JSON: liste d'ops line/polyline/circle/ellipse/arc/cubic)
    sur la toile certifiée. Si `subject` est fourni, CLIP juge « ça ressemble à <subject> ? ».
    Retourne le nb de traits, le score P, le top-1 et le chemin de l'image."""
    prog = json.loads(program)
    img = await _render(prog)
    path = OUT / "mcp_last.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    out = {"strokes": len(prog), "image": str(path)}
    if subject:
        p, ranking, cos = draw_critic.score(img, subject)
        out.update({"subject": subject, "p": round(p, 3), "cos": round(cos, 3),
                    "top": ranking[0][0], "recognized": ranking[0][0] == subject and p >= 0.5,
                    "ranking": [[l, round(v, 3)] for l, v in ranking[:5]]})
    return out


@mcp.tool()
def critique(image_path: str, subject: str) -> dict:
    """Juge une image existante avec CLIP : « ressemble à <subject> ? ». Retourne P + classement."""
    p, ranking, cos = draw_critic.score(image_path, subject)
    return {"subject": subject, "p": round(p, 3), "cos": round(cos, 3),
            "top": ranking[0][0], "recognized": ranking[0][0] == subject and p >= 0.5,
            "ranking": [[l, round(v, 3)] for l, v in ranking[:6]]}


@mcp.tool()
def learn(subject: str, seed_name: str = "", iters: int = 80) -> dict:
    """Lance la machine d'apprentissage : raffine un programme-graine guidé par CLIP
    (perturbe → dessine → juge → garde si ça monte). Retourne le score initial/final."""
    seed = seed_name or subject
    if seed not in PROGRAMS:
        return {"error": f"pas de graine « {seed} » (dispo: {list(PROGRAMS)})"}
    cmd = [sys.executable, str(ROOT / "draw_learn.py"), subject, "--seed-name", seed, "--iters", str(iters)]
    subprocess.run(cmd, cwd=str(ROOT), capture_output=True, timeout=900)
    f = LEARNED / f"{subject}.json"
    if not f.exists():
        return {"error": "apprentissage sans sortie"}
    d = json.loads(f.read_text(encoding="utf-8"))
    return {"subject": subject, "score": d["score"], "history": d["history"],
            "program_path": str(f), "image": str(LEARNED / f"{subject}.png")}


@mcp.tool()
def list_skills() -> dict:
    """Liste les compétences : programmes-graines + programmes appris (avec leur score CLIP)."""
    learned = {}
    if LEARNED.exists():
        for f in LEARNED.glob("*.json"):
            d = json.loads(f.read_text(encoding="utf-8"))
            learned[d["subject"]] = d["score"]
    return {"seeds": list(PROGRAMS.keys()), "learned": learned}


@mcp.tool()
def get_skill(name: str) -> dict:
    """Retourne le programme de traits d'une compétence (graine ou apprise)."""
    f = LEARNED / f"{name}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    if name in PROGRAMS:
        return {"subject": name, "program": PROGRAMS[name], "source": "seed"}
    return {"error": f"compétence inconnue: {name}"}


@mcp.tool()
def save_skill(name: str, program: str) -> dict:
    """Enregistre un programme de traits (JSON) comme compétence apprise."""
    prog = json.loads(program)
    LEARNED.mkdir(parents=True, exist_ok=True)
    f = LEARNED / f"{name}.json"
    f.write_text(json.dumps({"subject": name, "program": prog, "source": "saved"},
                            ensure_ascii=False, indent=2), encoding="utf-8")
    return {"saved": str(f), "strokes": len(prog)}


if __name__ == "__main__":
    mcp.run()

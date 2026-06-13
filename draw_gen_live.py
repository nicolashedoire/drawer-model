#!/usr/bin/env python3
"""draw-gen-live — DÉMO LIVE de la génération : du mot au dessin, sans photo.

Dans la fenêtre : (1) le système IMAGINE une image de chat (SD-Turbo, text→image,
local), (2) l'image générée s'affiche, (3) le système la DESSINE par-dessus en
direct (stipple + XDoG). Un chat réaliste généré ET dessiné, sans aucune photo.

  python3 draw_gen_live.py
  python3 draw_gen_live.py a fluffy white rabbit on a plain background
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import sys

import torch
from diffusers import AutoPipelineForText2Image
from PIL import Image

from cdp_session import CDPSession
from draw_lab import CANVAS_URL, OUT, warm_up
from draw_live import draw_program_live
import draw_portrait as P


def generate(prompt, seed=3):
    print(f"· j'imagine : « {prompt} » (SD-Turbo, local, sans photo)…", flush=True)
    pipe = AutoPipelineForText2Image.from_pretrained(
        "stabilityai/sd-turbo", torch_dtype=torch.float32, safety_checker=None)
    pipe = pipe.to("mps"); pipe.set_progress_bar_config(disable=True)
    g = torch.Generator(device="cpu").manual_seed(seed)
    img = pipe(prompt=prompt, num_inference_steps=3, guidance_scale=0.0,
               generator=g, height=512, width=512).images[0]
    out = OUT / "gen_live.png"; out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print("· image générée", flush=True)
    return str(out)


async def main():
    prompt = " ".join(sys.argv[1:]).strip() or \
        "a cute fluffy cat sitting on a plain white background, studio photo, soft even light, sharp, detailed"
    src = generate(prompt)
    P.SRC = src
    ops = P.portrait_ops(900)
    g, x0, y0, nw, nh = P.load_gray()
    im = Image.open(src).convert("RGB").resize((nw, nh))
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=85)
    durl = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

    s = CDPSession(headless=False, width=1040, height=730)
    print("· fenêtre visible", flush=True)
    s.launch_chrome(); await s.connect(); await s.navigate(CANVAS_URL)
    await s.wait_for("window.__ready === true", timeout=12); await warm_up(s)
    await s.eval("window.__clear()")
    await s.eval("window.__caption('1) J_ai imagine une image (SD-Turbo, sans photo)')")
    await asyncio.sleep(0.8)
    await s.eval("window.__bg(" + json.dumps(durl) + f", 1.0, {x0}, {y0}, {nw}, {nh})")
    await s.eval("window.__caption('Voila ce que j_imagine. 2) Maintenant je le dessine.')")
    await asyncio.sleep(3.5)
    await s.eval("window.__clear()")
    await s.eval("window.__bg(" + json.dumps(durl) + f", 0.4, {x0}, {y0}, {nw}, {nh})")
    await s.eval("window.__penShow(true)")
    await s.eval("window.__caption('Stipple (tons) + XDoG (lignes) par-dessus l_image imaginee')")
    await asyncio.sleep(0.6)
    await draw_program_live(s, ops)
    await s.eval("window.__caption('Chat realiste : genere ET dessine, sans aucune photo')")
    await asyncio.sleep(15)
    await s.close()


if __name__ == "__main__":
    asyncio.run(main())

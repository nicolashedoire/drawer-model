#!/usr/bin/env python3
"""app — interface web locale du drawer.

Tu tapes un sujet, tu choisis le style (cartoon / réaliste / minimaliste) et la
technique (lignes / pointillisme / portrait), tu cliques Dessiner :
  1) le système génère une image (SD-Turbo, local) — montrée à côté (l'inspiration)
  2) il en extrait un programme de traits (la technique choisie)
  3) la page anime le tracé sur la toile, comme s'il dessinait.

  python3 app.py            # puis ouvre http://127.0.0.1:8765
"""
from __future__ import annotations

import base64
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image

from draw_lab import OUT
from draw_figure import op_to_points

PORT = 8787
WEB_SRC = OUT / "web_src.png"
_PIPE = None

STYLES = {
    "cartoon": "a simple cute cartoon {s}, flat minimalist vector illustration, bold clean outlines, solid flat colors, plain white background, sticker style",
    "realistic": "a photo of a {s}, front view, centered, plain white background, studio photo, soft even light, sharp, highly detailed",
    "minimal": "a minimalist clean line illustration of a {s}, few simple lines, plain white background, centered",
}


def get_pipe():
    global _PIPE
    if _PIPE is None:
        import torch
        from diffusers import AutoPipelineForText2Image
        p = AutoPipelineForText2Image.from_pretrained(
            "stabilityai/sd-turbo", torch_dtype=torch.float32, safety_checker=None)
        _PIPE = p.to("mps"); _PIPE.set_progress_bar_config(disable=True)
    return _PIPE


def generate(prompt, style, seed=7):
    import torch
    full = STYLES.get(style, STYLES["cartoon"]).format(s=prompt.strip() or "cat")
    g = torch.Generator(device="cpu").manual_seed(int(seed))
    return get_pipe()(prompt=full, num_inference_steps=4, guidance_scale=0.0,
                      generator=g, height=512, width=512).images[0]


def compute_strokes(technique, path, simple):
    if technique == "stipple":
        import draw_photo as DP; DP.SRC = str(path)
        ops = DP.stipple_ops(2400)
    elif technique == "portrait":
        import draw_portrait as PR; PR.SRC = str(path)
        ops = PR.portrait_ops(1800)
    else:  # lines
        from draw_lines import cat_lines
        ops, _ = cat_lines(str(path), simple=simple)
    return [[[round(float(x), 1), round(float(y), 1)] for (x, y) in op_to_points(op)] for op in ops]


PAGE = """<!doctype html><html><head><meta charset=utf-8><title>drawer</title>
<style>
 body{margin:0;font:15px -apple-system,Segoe UI,sans-serif;background:#f4f4f6;color:#1a1a1a}
 header{padding:14px 18px;background:#fff;border-bottom:1px solid #e3e3e8;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
 input,select,button{font:inherit;padding:8px 10px;border:1px solid #ccc;border-radius:8px;background:#fff}
 #prompt{flex:1;min-width:240px}
 button{background:#1a1a1a;color:#fff;border:0;cursor:pointer;font-weight:600;padding:9px 18px}
 button:disabled{opacity:.5;cursor:default}
 label{font-size:13px;color:#555;display:flex;flex-direction:column;gap:3px}
 main{display:flex;gap:18px;padding:18px;align-items:flex-start;flex-wrap:wrap}
 .panel{background:#fff;border:1px solid #e3e3e8;border-radius:12px;padding:12px;box-shadow:0 1px 3px rgba(0,0,0,.05)}
 .ttl{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:#888;margin-bottom:8px}
 #canvas{width:680px;height:435px;background:#fff;border:1px solid #eee;border-radius:6px}
 #ref{width:280px;height:280px;object-fit:contain;background:#fafafa;border:1px solid #eee;border-radius:6px}
 #status{font-size:13px;color:#666;margin-left:auto}
</style></head><body>
<header>
 <input id=prompt placeholder="que veux-tu que je dessine ? (ex: un renard, un hibou...)" value="un chat">
 <label>style<select id=style><option value=cartoon>cartoon (simple)</option><option value=realistic>réaliste</option><option value=minimal>minimaliste</option></select></label>
 <label>technique<select id=tech><option value=lines>lignes</option><option value=stipple>pointillisme</option><option value=portrait>portrait (lignes+tons)</option></select></label>
 <label>épuré<select id=simple><option value=0>non</option><option value=1>oui</option></select></label>
 <button id=go>Dessiner</button>
 <span id=status>prêt</span>
</header>
<main>
 <div class=panel><div class=ttl>Dessin</div><canvas id=canvas width=1000 height=640></canvas></div>
 <div class=panel><div class=ttl>Inspiration (image générée)</div><img id=ref alt="(l'image apparaîtra ici)"></div>
</main>
<script>
const C=document.getElementById('canvas'),X=C.getContext('2d');
function clear(){X.fillStyle='#fff';X.fillRect(0,0,C.width,C.height);}
clear();
const st=document.getElementById('status'),go=document.getElementById('go');
let anim=null;
function animate(strokes){
 if(anim)cancelAnimationFrame(anim);
 clear();X.strokeStyle='#111';X.lineWidth=1.6;X.lineJoin='round';X.lineCap='round';
 let i=0;const per=Math.max(4,Math.floor(strokes.length/240));
 function frame(){
  for(let k=0;k<per&&i<strokes.length;k++,i++){
   const s=strokes[i];if(s.length<2)continue;
   X.beginPath();X.moveTo(s[0][0],s[0][1]);
   for(let j=1;j<s.length;j++)X.lineTo(s[j][0],s[j][1]);
   X.stroke();
  }
  st.textContent='dessin… '+i+'/'+strokes.length+' traits';
  if(i<strokes.length){anim=requestAnimationFrame(frame);}else{st.textContent='✓ '+strokes.length+' traits';go.disabled=false;}
 }
 frame();
}
go.onclick=async()=>{
 go.disabled=true;st.textContent='génération de l\\'image…';document.getElementById('ref').removeAttribute('src');
 const body={prompt:prompt.value,style:style.value,technique:tech.value,simple:simple.value==='1'};
 try{
  const r=await fetch('/draw',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await r.json();
  if(d.error){st.textContent='erreur: '+d.error;go.disabled=false;return;}
  document.getElementById('ref').src=d.image;
  st.textContent='tracé…';animate(d.strokes);
 }catch(e){st.textContent='erreur: '+e;go.disabled=false;}
};
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers(); self.wfile.write(PAGE.encode())

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
            img = generate(req.get("prompt", "un chat"), req.get("style", "cartoon"))
            OUT.mkdir(parents=True, exist_ok=True); img.save(WEB_SRC)
            strokes = compute_strokes(req.get("technique", "lines"), WEB_SRC, bool(req.get("simple")))
            buf = io.BytesIO(); img.save(buf, "PNG")
            durl = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
            out = json.dumps({"image": durl, "strokes": strokes}).encode()
        except Exception as e:
            out = json.dumps({"error": str(e)[:200]}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.end_headers(); self.wfile.write(out)


if __name__ == "__main__":
    print(f"· interface : http://127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()

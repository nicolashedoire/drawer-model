#!/usr/bin/env python3
"""app — interface web locale du drawer.

Tu tapes un sujet, tu choisis le style (cartoon / réaliste / minimaliste) et la
technique (lignes / pointillisme / portrait), tu cliques Dessiner :
  1) le système génère une image (SD-Turbo, local) — montrée à côté (l'inspiration)
  2) il en extrait un programme de traits (la technique choisie)
  3) la page anime le tracé sur la toile, comme s'il dessinait.

  python3 app.py            # puis ouvre http://127.0.0.1:8787
"""
from __future__ import annotations

import base64
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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
    full = STYLES.get(style, STYLES["cartoon"]).format(s=(prompt or "").strip() or "cat")
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


PAGE = r"""<!doctype html><html lang=fr><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Drawer</title>
<style>
 *{box-sizing:border-box}
 body{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
   background:radial-gradient(1200px 600px at 70% -10%,#eef1ff,transparent),linear-gradient(180deg,#f7f8fb,#eceef4);
   color:#1b1b22;min-height:100vh}
 .wrap{max-width:1200px;margin:0 auto;padding:34px 24px 48px}
 h1{font-size:24px;margin:0;font-weight:800;letter-spacing:-.02em}
 .sub{color:#7c7c88;font-size:14px;margin:4px 0 22px}
 .bar{display:flex;gap:14px;align-items:flex-end;flex-wrap:wrap;background:rgba(255,255,255,.85);
   backdrop-filter:blur(8px);padding:18px;border-radius:18px;box-shadow:0 8px 30px rgba(30,30,60,.08);
   border:1px solid rgba(255,255,255,.7);margin-bottom:22px}
 .fld{display:flex;flex-direction:column;gap:6px}
 .fld.grow{flex:1;min-width:240px}
 .fld label{font-size:11px;font-weight:700;color:#9a9aa6;text-transform:uppercase;letter-spacing:.06em}
 input,select{font-size:15px;font-family:inherit;padding:12px 13px;border:1.5px solid #e6e6ee;border-radius:12px;
   background:#fbfbfe;transition:border .15s,box-shadow .15s;color:#1b1b22}
 input:focus,select:focus{outline:0;border-color:#6366f1;background:#fff;box-shadow:0 0 0 4px rgba(99,102,241,.12)}
 button{font-size:15px;font-family:inherit;font-weight:700;padding:13px 26px;border:0;border-radius:12px;
   background:linear-gradient(180deg,#7376f6,#5b5ef0);color:#fff;cursor:pointer;box-shadow:0 6px 16px rgba(91,94,240,.35);transition:.15s}
 button:hover{transform:translateY(-1px);box-shadow:0 9px 22px rgba(91,94,240,.45)}
 button:disabled{opacity:.55;cursor:default;transform:none;box-shadow:none}
 button.ghost{background:#fff;color:#5b5ef0;border:1.5px solid #dcdcf3;box-shadow:none}
 button.ghost:hover{background:#f2f2ff;transform:none;box-shadow:none}
 .row{display:flex;gap:22px;align-items:flex-start;flex-wrap:wrap}
 .card{background:#fff;border-radius:18px;padding:18px;box-shadow:0 8px 30px rgba(30,30,60,.07);border:1px solid #f0f0f5}
 .card .h{font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.07em;color:#a6a6b2;margin-bottom:14px}
 #canvas{width:720px;max-width:100%;aspect-ratio:1000/640;background:#fff;border-radius:12px;border:1px solid #eee;display:block}
 .ref-box{width:300px;height:300px;border-radius:12px;border:1px solid #eee;background:#f6f6fa;
   display:flex;align-items:center;justify-content:center;overflow:hidden}
 .ref-box img{width:100%;height:100%;object-fit:contain}
 .ref-box .ph{color:#bcbcc8;font-size:13px;padding:0 20px;text-align:center}
 .status{margin-top:14px;font-size:13px;color:#83838f;min-height:18px}
 .dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#5b5ef0;margin-right:7px;vertical-align:middle;animation:pulse 1s infinite}
 @keyframes pulse{0%,100%{opacity:.3}50%{opacity:1}}
</style></head><body>
<div class=wrap>
 <h1>🎨 Drawer</h1>
 <div class=sub>Tape un sujet, choisis le style et la technique — je l'imagine puis je le dessine, à la main.</div>
 <div class=bar>
  <div class="fld grow"><label>Sujet</label><input id=prompt value="un chat" placeholder="un renard, un hibou, une maison…"></div>
  <div class=fld><label>Style</label><select id=style>
   <option value=cartoon>Cartoon (simple)</option><option value=realistic>Réaliste</option><option value=minimal>Minimaliste</option></select></div>
  <div class=fld><label>Technique</label><select id=tech>
   <option value=lines>Lignes</option><option value=stipple>Pointillisme</option><option value=portrait>Portrait (lignes+tons)</option></select></div>
  <div class=fld><label>Épuré</label><select id=simple><option value=0>Non</option><option value=1>Oui</option></select></div>
  <div class=fld><label>Trait</label><select id=pen><option value=1.2>Fin</option><option value=1.7 selected>Moyen</option><option value=2.6>Épais</option></select></div>
  <div class=fld><label>&nbsp;</label><button id=go>Dessiner</button></div>
  <div class=fld><label>&nbsp;</label><button id=png class=ghost disabled>↓ PNG</button></div>
  <div class=fld><label>&nbsp;</label><button id=svg class=ghost disabled>↓ SVG</button></div>
 </div>
 <div class=row>
  <div class=card><div class=h>Dessin</div><canvas id=canvas width=1000 height=640></canvas><div class=status id=status>Prêt.</div></div>
  <div class=card><div class=h>Inspiration · image générée</div>
   <div class=ref-box id=refbox><div class=ph>L'image générée apparaîtra ici</div></div></div>
 </div>
</div>
<script>
const $=id=>document.getElementById(id);
const C=$('canvas'),X=C.getContext('2d');
let anim=null,lastStrokes=null;
const penW=()=>parseFloat($('pen').value);
function clr(){X.fillStyle='#fff';X.fillRect(0,0,C.width,C.height);}
clr();
function redraw(){
 clr();if(!lastStrokes)return;
 X.strokeStyle='#141414';X.lineWidth=penW();X.lineJoin='round';X.lineCap='round';
 for(const s of lastStrokes){if(!s||s.length<2)continue;
  X.beginPath();X.moveTo(s[0][0],s[0][1]);for(let j=1;j<s.length;j++)X.lineTo(s[j][0],s[j][1]);X.stroke();}
}
function animate(strokes){
 if(anim)cancelAnimationFrame(anim);
 lastStrokes=strokes;clr();
 X.strokeStyle='#141414';X.lineWidth=penW();X.lineJoin='round';X.lineCap='round';
 let i=0;const per=Math.max(3,Math.floor(strokes.length/260));
 (function frame(){
  for(let k=0;k<per&&i<strokes.length;k++,i++){
   const s=strokes[i];if(!s||s.length<2)continue;
   X.beginPath();X.moveTo(s[0][0],s[0][1]);for(let j=1;j<s.length;j++)X.lineTo(s[j][0],s[j][1]);X.stroke();
  }
  $('status').textContent='✎ tracé… '+i+' / '+strokes.length+' traits';
  if(i<strokes.length)anim=requestAnimationFrame(frame);
  else{$('status').textContent='✓ terminé — '+strokes.length+' traits';$('go').disabled=false;$('png').disabled=false;$('svg').disabled=false;}
 })();
}
$('pen').onchange=redraw;
$('go').onclick=async()=>{
 $('go').disabled=true;$('png').disabled=true;$('svg').disabled=true;
 $('status').innerHTML='<span class=dot></span>génération de l\'image…';
 $('refbox').innerHTML='<div class=ph>génération…</div>';
 const body={prompt:$('prompt').value,style:$('style').value,technique:$('tech').value,simple:$('simple').value==='1'};
 try{
  const r=await fetch('/draw',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const d=await r.json();
  if(d.error){$('status').textContent='⚠ '+d.error;$('go').disabled=false;return;}
  $('refbox').innerHTML='<img src="'+d.image+'">';
  $('status').innerHTML='<span class=dot></span>tracé…';animate(d.strokes);
 }catch(e){$('status').textContent='⚠ '+e;$('go').disabled=false;}
};
function dl(href,name){const a=document.createElement('a');a.href=href;a.download=name;a.click();}
$('png').onclick=()=>dl(C.toDataURL('image/png'),'dessin.png');
$('svg').onclick=()=>{
 let p='<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="640" viewBox="0 0 1000 640"><rect width="1000" height="640" fill="#fff"/>';
 for(const s of (lastStrokes||[])){if(!s||s.length<2)continue;
  p+='<polyline fill="none" stroke="#141414" stroke-width="'+penW()+'" stroke-linejoin="round" stroke-linecap="round" points="'+s.map(q=>q[0]+','+q[1]).join(' ')+'"/>';}
 p+='</svg>';dl('data:image/svg+xml;charset=utf-8,'+encodeURIComponent(p),'dessin.svg');
};
$('prompt').addEventListener('keydown',e=>{if(e.key==='Enter')$('go').click();});
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
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

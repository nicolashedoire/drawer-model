#!/usr/bin/env python3
"""draw-critic — l'ŒIL QUI JUGE (critique CLIP local, MPS).

Rend un score « ça ressemble à X ? » : on compare l'image rendue au prompt
« un dessin de X » contre une liste de distracteurs, via CLIP (sur le GPU Apple).
C'est le critique qui ferme la boucle générer → rendre → noter → raffiner.

  python3 draw_critic.py .state/draw/fig_horse.png horse
  python3 draw_critic.py .state/draw/fig_house.png house
"""
from __future__ import annotations

import sys

import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

MODEL = "openai/clip-vit-base-patch32"
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
# pool de distracteurs courants (sujets dessinables)
DISTRACTORS = ["dog", "cow", "cat", "house", "tree", "car", "bicycle", "boat",
               "person", "bird", "fish", "flower", "chair", "sun", "dragon"]
_MODEL = None
_PROC = None


def _load():
    global _MODEL, _PROC
    if _MODEL is None:
        _MODEL = CLIPModel.from_pretrained(MODEL).to(DEVICE).eval()
        _PROC = CLIPProcessor.from_pretrained(MODEL)
    return _MODEL, _PROC


def embed_texts(texts):
    """Embeddings CLIP normalisés pour une liste de textes (pour la récupération)."""
    model, proc = _load()
    inputs = proc(text=list(texts), return_tensors="pt", padding=True, truncation=True).to(DEVICE)
    with torch.no_grad():
        out = model.text_model(input_ids=inputs["input_ids"], attention_mask=inputs.get("attention_mask"))
        emb = model.text_projection(out.pooler_output)
        emb = emb / emb.norm(dim=-1, keepdim=True)
    return emb


def score(image, subject, distractors=None):
    """Retourne (p_subject, classement[(label,prob)], cos_brut_subject)."""
    model, proc = _load()
    img = image if isinstance(image, Image.Image) else Image.open(image).convert("RGB")
    labels = [subject] + [d for d in (distractors or DISTRACTORS) if d != subject]
    prompts = [f"a simple line drawing of a {l}" for l in labels]
    inputs = proc(text=prompts, images=img, return_tensors="pt", padding=True).to(DEVICE)
    with torch.no_grad():
        out = model(**inputs)
        img_emb = out.image_embeds / out.image_embeds.norm(dim=-1, keepdim=True)
        txt_emb = out.text_embeds / out.text_embeds.norm(dim=-1, keepdim=True)
        cos = (img_emb @ txt_emb.T)[0]                # cosinus image vs chaque prompt
        probs = (cos * 100).softmax(dim=-1)           # température CLIP standard
    ranking = sorted(zip(labels, probs.tolist()), key=lambda x: -x[1])
    p_subject = probs[0].item()
    cos_subject = cos[0].item()
    return p_subject, ranking, cos_subject


def main():
    image = sys.argv[1] if len(sys.argv) > 1 else ".state/draw/fig_horse.png"
    subject = sys.argv[2] if len(sys.argv) > 2 else "horse"
    print(f"· critique CLIP ({MODEL}) sur {DEVICE}")
    p, ranking, cos = score(image, subject)
    top = ranking[0][0]
    verdict = "RECONNU ✓" if top == subject and p >= 0.5 else ("proche" if top == subject else f"vu comme « {top} »")
    print(f"\n  image : {image}")
    print(f"  sujet visé : « {subject} »  →  P={p:.2f}  (cosinus brut {cos:.3f})  [{verdict}]")
    print("  classement CLIP :")
    for label, pr in ranking[:6]:
        bar = "█" * int(pr * 30)
        mark = "←" if label == subject else " "
        print(f"    {pr:5.2f} {label:10} {bar} {mark}")


if __name__ == "__main__":
    main()

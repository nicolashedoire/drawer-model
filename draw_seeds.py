#!/usr/bin/env python3
"""draw-seeds — graines de programmes de traits (le cerveau pose l'ébauche).

Chaque graine est une ébauche grossière mais reconnaissable d'un sujet. La
machine d'apprentissage (draw_learn) la raffine ensuite via CLIP. Sujets choisis
pour être simples à tracer et distincts dans l'espace CLIP.
"""
from __future__ import annotations
import math


def _star(cx, cy, ro, ri, n=5):
    pts = []
    for i in range(2 * n + 1):
        r = ro if i % 2 == 0 else ri
        a = -math.pi / 2 + i * math.pi / n
        pts.append([round(cx + r * math.cos(a), 1), round(cy + r * math.sin(a), 1)])
    return {"op": "polyline", "pts": pts, "close": True}


def _sun(cx, cy, r, rays=12):
    ops = [{"op": "circle", "c": [cx, cy], "r": r}]
    for i in range(rays):
        a = 2 * math.pi * i / rays
        ops.append({"op": "line",
                    "a": [round(cx + (r + 16) * math.cos(a), 1), round(cy + (r + 16) * math.sin(a), 1)],
                    "b": [round(cx + (r + 52) * math.cos(a), 1), round(cy + (r + 52) * math.sin(a), 1)]})
    return ops


def _flower(cx, cy):
    ops = [{"op": "line", "a": [cx, cy + 24], "b": [cx, cy + 250]}]                 # tige
    ops.append({"op": "ellipse", "c": [cx - 46, cy + 150], "r": [42, 18], "rot": -28})  # feuille
    ops.append({"op": "ellipse", "c": [cx + 46, cy + 190], "r": [42, 18], "rot": 28})
    for i in range(6):                                                              # pétales
        a = 2 * math.pi * i / 6
        ops.append({"op": "ellipse", "c": [round(cx + 52 * math.cos(a), 1), round(cy + 52 * math.sin(a), 1)],
                    "r": [44, 26], "rot": round(math.degrees(a), 1)})
    ops.append({"op": "circle", "c": [cx, cy], "r": 32})                            # cœur
    return ops


SEEDS = {
    "sun": _sun(500, 300, 86),
    "star": [_star(500, 312, 156, 64)],
    "tree": [  # sapin (triangles empilés) — bien plus « arbre » que des cercles
        {"op": "polyline", "pts": [[480, 548], [480, 470], [520, 470], [520, 548]], "close": False},  # tronc
        {"op": "polyline", "pts": [[404, 472], [500, 300], [596, 472]], "close": True},  # étage bas
        {"op": "polyline", "pts": [[420, 374], [500, 224], [580, 374]], "close": True},  # étage milieu
        {"op": "polyline", "pts": [[434, 286], [500, 160], [566, 286]], "close": True},  # étage haut
    ],
    "flower": _flower(500, 268),
    "fish": [
        {"op": "ellipse", "c": [470, 320], "r": [150, 82]},                          # corps
        {"op": "polyline", "pts": [[615, 320], [710, 262], [710, 378]], "close": True},  # queue
        {"op": "polyline", "pts": [[430, 238], [500, 200], [560, 240]], "close": False},  # nageoire dorsale
        {"op": "circle", "c": [378, 300], "r": 9},                                   # œil
        {"op": "arc", "c": [350, 322], "r": 36, "a": [120, 240]},                    # bouche/branchie
    ],
    "sailboat": [
        {"op": "polyline", "pts": [[360, 430], [640, 430], [590, 492], [410, 492]], "close": True},  # coque
        {"op": "line", "a": [500, 430], "b": [500, 196]},                            # mât
        {"op": "polyline", "pts": [[508, 206], [508, 414], [624, 414]], "close": True},  # grande voile
        {"op": "polyline", "pts": [[492, 240], [492, 414], [392, 414]], "close": True},  # foc
        {"op": "line", "a": [300, 520], "b": [700, 520]},                            # eau
        {"op": "line", "a": [320, 540], "b": [680, 540]},
    ],
    "cat": [
        {"op": "circle", "c": [500, 250], "r": 84},                                  # tête
        {"op": "polyline", "pts": [[446, 196], [428, 126], [492, 200]], "close": True},  # oreille G
        {"op": "polyline", "pts": [[508, 200], [572, 126], [554, 196]], "close": True},  # oreille D
        {"op": "circle", "c": [472, 248], "r": 8}, {"op": "circle", "c": [528, 248], "r": 8},  # yeux
        {"op": "polyline", "pts": [[492, 268], [508, 268], [500, 282]], "close": True},  # nez
        {"op": "line", "a": [500, 282], "b": [500, 300]},
        {"op": "line", "a": [430, 270], "b": [360, 258]}, {"op": "line", "a": [430, 284], "b": [362, 292]},  # moustaches G
        {"op": "line", "a": [570, 270], "b": [640, 258]}, {"op": "line", "a": [570, 284], "b": [638, 292]},  # moustaches D
        {"op": "ellipse", "c": [500, 440], "r": [96, 118]},                          # corps
        {"op": "cubic", "p": [[592, 470], [660, 440], [664, 360], [610, 330]]},      # queue
    ],
    "umbrella": [
        {"op": "arc", "c": [500, 300], "r": 160, "a": [180, 360]},                   # dôme
        {"op": "line", "a": [340, 300], "b": [660, 300]},                            # base du dôme
        {"op": "line", "a": [500, 140], "b": [500, 300]}, {"op": "line", "a": [420, 300], "b": [500, 152]},
        {"op": "line", "a": [580, 300], "b": [500, 152]},                            # baleines
        {"op": "line", "a": [500, 300], "b": [500, 500]},                            # manche
        {"op": "cubic", "p": [[500, 500], [500, 540], [452, 540], [452, 506]]},      # poignée
    ],
    "ladder": [
        {"op": "line", "a": [438, 140], "b": [414, 548]}, {"op": "line", "a": [562, 140], "b": [586, 548]},
        {"op": "line", "a": [432, 208], "b": [568, 208]}, {"op": "line", "a": [424, 288], "b": [576, 288]},
        {"op": "line", "a": [418, 368], "b": [582, 368]}, {"op": "line", "a": [412, 448], "b": [588, 448]},
    ],
    "car": [
        {"op": "polyline", "pts": [[340, 420], [400, 420], [444, 352], [596, 352], [648, 420], [712, 420],
                                   [712, 472], [340, 472]], "close": True},          # carrosserie
        {"op": "polyline", "pts": [[452, 360], [512, 360], [512, 416], [430, 416]], "close": True},  # vitre G
        {"op": "polyline", "pts": [[524, 360], [588, 360], [612, 416], [524, 416]], "close": True},  # vitre D
        {"op": "circle", "c": [438, 478], "r": 42}, {"op": "circle", "c": [620, 478], "r": 42},  # roues
    ],
}

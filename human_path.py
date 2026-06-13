"""Minimal human-like pointer-path planner (interface used by cdp_session).

The drawing executor drives the canvas with direct CDP mouse events, so this is
only an import-time dependency; it returns a smooth ease-in-out path for the
generic human_move/human_click helpers if they are ever used.
"""
from __future__ import annotations

import math


def plan_human_path(x0, y0, x1, y1, target_w=40, target_h=40):
    dist = math.hypot(x1 - x0, y1 - y0)
    n = max(8, int(dist / 12))
    path = []
    for i in range(1, n + 1):
        t = i / n
        e = 3 * t * t - 2 * t * t * t          # ease-in-out
        path.append({"x": x0 + (x1 - x0) * e, "y": y0 + (y1 - y0) * e, "delay_ms": 8})
    return path

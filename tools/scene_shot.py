# -*- coding: utf-8 -*-
"""渲染指定场景的指定时刻(1:1), 用于精调某一格:
  python tools/scene_shot.py ceiling_3am 8.0 14.0
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pygame  # noqa: E402

from nightpix import config as C  # noqa: E402
C.set_canvas(640, 360, 3)

from nightpix import night_ep, render, scenes as S  # noqa: E402


def main():
    scene = sys.argv[1] if len(sys.argv) > 1 else "ceiling_3am"
    lt = float(sys.argv[2]) if len(sys.argv) > 2 else 6.0
    dur = float(sys.argv[3]) if len(sys.argv) > 3 else 14.0
    surf = render.init_pygame()
    ctx = night_ep.Context()
    S.SCENES[scene](surf, ctx, lt, dur)
    big = pygame.transform.scale(surf, (C.VW * C.SCALE, C.VH * C.SCALE))
    os.makedirs(C.OUT, exist_ok=True)
    p = os.path.join(C.OUT, f"_scene_{scene}.png")
    pygame.image.save(big, p)
    print(p)


if __name__ == "__main__":
    main()

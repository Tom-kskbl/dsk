# -*- coding: utf-8 -*-
"""单帧近检: python tools/_closeup.py [A|B|C] [level]"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pygame  # noqa: E402

from nightpix import config as C  # noqa: E402
from nightpix import keeper as K  # noqa: E402
from nightpix import paint as P  # noqa: E402
from nightpix import pixeltext as T  # noqa: E402
from nightpix import render  # noqa: E402

which = sys.argv[1] if len(sys.argv) > 1 else "A"
level = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
name = {"A": "A_背影提灯", "B": "B_远景小人物", "C": "C_正面版"}[which]

surf = render.init_pygame()
surf.blit(P.make_gradient(C.NIGHT1, C.VOID), (0, 0))
P.dither_gradient_rect(surf, (0, 232, C.VW, 128), C.NIGHT1, C.VOID)
# 地面线
pygame.draw.line(surf, (44, 56, 86), (0, 300), (C.VW, 300))
for i in range(1, 4):
    pygame.draw.line(surf, (22, 28, 46), (0, 300 + i * 2), (C.VW, 300 + i * 2))
K.CONCEPTS[name](surf, C.VW // 2, 300, level, 0.0)
T.draw(surf, f"{name}  level={level:.2f}", 12, 12, color=C.BRIGHT,
       size=C.FONT_SIZE_BIG, bold=True)
# 局部放大: 人物区域 (中心 240x260) -> 1:1 贴回右侧, 看清像素
big = pygame.transform.scale(surf, (C.VW * C.SCALE, C.VH * C.SCALE))
crop = big.subsurface(pygame.Rect(C.VW * 3 // 2 - 180, 1080 - 300, 360, 300)).copy()
zoom = pygame.transform.scale(crop, (720, 600))
big.blit(zoom, (1150, 380))
pygame.draw.rect(big, (90, 104, 140), pygame.Rect(1150, 380, 720, 600), 2)
T.draw(big, "局部 2x 放大", 1160, 366, color=C.MUTE, size=13, outline=(0, 0, 0))
os.makedirs(C.OUT, exist_ok=True)
p = os.path.join(C.OUT, f"_closeup_{which}.png")
pygame.image.save(big, p)
print(p)

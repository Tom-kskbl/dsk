# -*- coding: utf-8 -*-
"""角色单独预览: python tools/sprite_preview.py [scale] [level] [pose]"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pygame  # noqa: E402

from nightpix import config as C  # noqa: E402
from nightpix import keeper as K  # noqa: E402
from nightpix import paint as P  # noqa: E402
from nightpix import pixeltext as T  # noqa: E402
from nightpix import render  # noqa: E402

scale = int(sys.argv[1]) if len(sys.argv) > 1 else 6
level = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
pose = sys.argv[3] if len(sys.argv) > 3 else "stand"

surf = render.init_pygame()
surf.fill((26, 30, 44))                      # 中性背景, 便于判断剪影
for x in range(0, C.VW, 20):
    pygame.draw.line(surf, (34, 39, 56), (x, 0), (x, C.VH))
for y in range(0, C.VH, 20):
    pygame.draw.line(surf, (34, 39, 56), (0, y), (C.VW, y))
# 地面
pygame.draw.line(surf, (70, 84, 118), (0, 300), (C.VW, 300))
K.draw_keeper(surf, C.VW // 2, 300, level, 0.0, scale, pose)
T.draw(surf, f"keeper  scale={scale}  level={level:.2f}  pose={pose}", 10, 8,
       color=C.BRIGHT, size=12, bold=True)

# 左侧列: 三档亮度对照(小图)
for i, lv in enumerate((1.0, 0.55, 0.24)):
    K.draw_keeper(surf, 70, 110 + i * 95, lv, 0.0, 3, "stand")
    T.draw(surf, f"level {lv:.2f}", 8, 60 + i * 95, color=C.MUTE, size=11)

big = pygame.transform.scale(surf, (C.VW * 3, C.VH * 3))
os.makedirs(C.OUT, exist_ok=True)
p = os.path.join(C.OUT, f"_sprite_{scale}x_{pose}.png")
pygame.image.save(big, p)
print(p)

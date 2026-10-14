# -*- coding: utf-8 -*-
"""形象定稿工具: 出 3 版候选的对比联络表 + 段过场样片。

  python tools/char_concept.py            # 出 docs/process/design_concepts.png
  python tools/char_concept.py --sample   # 额外出 out/_concept_sample.mp4 (2 秒动画样片)
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from nightpix import config as C  # noqa: E402
from nightpix import keeper as K  # noqa: E402
from nightpix import paint as P  # noqa: E402
from nightpix import pixeltext as T  # noqa: E402
from nightpix import render  # noqa: E402

CELL = (C.VW * C.SCALE // 2, C.VH * C.SCALE // 2)      # 960x540


def _bg(surf, warm=1.0):
    surf.blit(P.make_gradient(C.NIGHT1, C.VOID), (0, 0))
    P.dither_gradient_rect(surf, (0, 232, C.VW, 128), C.NIGHT1, C.VOID)
    P.glow_at(surf, C.VW * 0.72, C.VH * 0.55, 90, C.WARM_DEEP, 0.16 * warm)


def _cell(fn, level, t, label, sub=""):
    """渲染一格: 640x360 画布 -> 2 倍 -> 960x540。"""
    surf = render.init_pygame()
    _bg(surf, level)
    fn(surf, C.VW // 2, 300, level, t)
    T.draw(surf, label, 12, 12, color=C.BRIGHT, size=C.FONT_SIZE_BIG, bold=True,
           outline=(0, 0, 0))
    if sub:
        T.draw(surf, sub, 12, 32, color=C.MUTE, size=C.FONT_SIZE_SMALL, outline=(0, 0, 0))
    return pygame.transform.scale(surf, CELL)


def contact_sheet(out_path: str) -> str:
    render.init_pygame()
    names = list(K.CONCEPTS)
    cols = ["灯 100%", "灯 55%", "灯 22%", "呼吸/明灭"]
    sheet = pygame.Surface((CELL[0] * 3, CELL[1] * 4))
    sheet.fill((6, 8, 14))
    for r, name in enumerate(names):
        fn = K.CONCEPTS[name]
        for c, lab in enumerate(cols):
            if c == 3:
                t = 0.0
                lv = 0.55 + 0.45 * max(0.0, math.sin(t * 6.0))
            else:
                t = 0.0
                lv = (1.0, 0.55, 0.22)[c]
            img = _cell(fn, lv, t, name if c == 0 else "", lab)
            sheet.blit(img, (c * CELL[0], r * CELL[1]))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    pygame.image.save(sheet, out_path)
    print("候选联络表:", out_path, sheet.get_size())
    return out_path


class SampleTimeline:
    """2 秒样片: 呼吸 + 灯明灭 + 灯色转冷, 用来验证"动起来不崩"。"""

    duration = 2.0

    def __init__(self, concept="A_提灯背影"):
        self.fn = K.CONCEPTS[concept]
        self.keep = K.Keeper()
        self.fx = P.NightFX(seed=3, grain=0.35)

    def draw(self, surf, t):
        k = t / self.duration
        level = P.lerp(1.0, 0.30, k)
        surf.blit(P.make_gradient(C.NIGHT1, C.VOID), (0, 0))
        P.dither_gradient_rect(surf, (0, 232, C.VW, 128), C.NIGHT1, C.VOID)
        # 呼吸: 整个场景跟着灯一起明暗
        self.fn(surf, C.VW // 2, 300, level, t)
        T.draw(surf, "呼吸 · 灯明灭 样片", 12, 12, color=C.BRIGHT, size=C.FONT_SIZE_BIG,
               bold=True)
        T.draw(surf, f"灯 {int(level * 100)}%", C.VW - 12, 12, color=C.MUTE,
               size=C.FONT_SIZE_SMALL, anchor="topright")
        self.fx.apply(surf, t, grain=True, scan=True, vignette=True)
        return surf


def sample(out_path: str) -> str:
    tl = SampleTimeline()
    render.init_pygame()
    # 无音频: 生成一个同长的静音 wav
    import numpy as np
    from nightpix import audio as A
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    silent = os.path.join(C.OUT, "_silence.wav")
    A.write_wav(silent, np.zeros((int(A.SR * tl.duration), 2), dtype=np.float32))
    return render.encode(tl, silent, out_path, crf=20, preset="veryfast")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true")
    ap.add_argument("--out", default=os.path.join(C.DOCS, "process", "design_concepts.png"))
    a = ap.parse_args()
    contact_sheet(a.out)
    if a.sample:
        sample(os.path.join(C.OUT, "_concept_sample.mp4"))

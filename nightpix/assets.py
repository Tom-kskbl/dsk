# -*- coding: utf-8 -*-
"""精灵图集读取器: 从 assets/sprites/atlas.png + atlas.json 载入素材。

设计与 keeper.py 的几何版并行存在, 但优先使用图集 —— 这样改素材只要重跑
tools/make_pixel_assets.py, 不必动画面代码。

亮度分档复用几何版的做法: 三档位图交叉混合(避免逐帧改色导致的缩放闪烁)。
"""
import json
import os

import pygame

from . import config as C

_CACHE = {}
_MANIFEST = None


def _manifest():
    global _MANIFEST
    if _MANIFEST is None:
        p = os.path.join(C.ASSETS, "sprites", "atlas.json")
        with open(p, encoding="utf-8") as fh:
            _MANIFEST = json.load(fh)
    return _MANIFEST


def _atlas() -> pygame.Surface:
    key = "__atlas__"
    if key not in _CACHE:
        p = os.path.join(C.ASSETS, "sprites", _manifest()["atlas"])
        _CACHE[key] = pygame.image.load(p).convert_alpha()
    return _CACHE[key]


def get(name: str) -> pygame.Surface:
    """取一个 sprite(1:1 像素, 未缩放)。"""
    info = _manifest()["sprites"][name]
    return _atlas().subsurface(pygame.Rect(info["x"], info["y"], info["w"], info["h"])).copy()


def meta(name: str) -> dict:
    return _manifest()["sprites"][name]


def tinted(name: str, level: float, dim_color=(7, 10, 20)) -> pygame.Surface:
    """按 level(0..1) 压暗 —— 灯越暗, 人物越沉进夜色。

    实现上踩过两次坑, 都记在这里:
      1. 不能盖"半透明黑矩形" —— 会把 sprite 周围的透明区一起涂黑, 每个精灵顶个黑方块
      2. 用 pixels3d 写 RGB 虽然 alpha 测试看着是干净的, 但配合上层的加色光晕仍会显出方块
    最终改成 BLEND_RGB_MULT 通道乘法: 只缩 RGB、完全不动 alpha, 是三者里唯一稳的。
    """
    key = (name, round(level, 2))
    if key in _CACHE:
        return _CACHE[key]
    s = get(name)
    lv = 0.0 if level < 0 else 1.0 if level > 1 else level
    if lv < 0.999:
        s = s.copy()
        # 关键: BLEND_RGB_MULT 只乘 RGB, 但会把目标 alpha 覆盖成源 alpha(即 255),
        # 于是 sprite 周围的透明区被刷成不透明 -> 每个精灵顶着一个黑方块。
        # 先把 alpha 存下来, 乘完再写回去。
        import numpy as np
        keep = pygame.surfarray.pixels_alpha(s).copy()
        f = int(round(255 * (0.18 + 0.82 * lv)))
        mul = pygame.Surface(s.get_size())
        mul.fill((f, f, f))
        s.blit(mul, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        pygame.surfarray.pixels_alpha(s)[:] = keep
    _CACHE[key] = s
    return s


def scaled(name: str, level: float, scale: int) -> pygame.Surface:
    """最近邻放大到世界坐标尺寸。"""
    key = (name, round(level, 2), scale)
    if key in _CACHE:
        return _CACHE[key]
    s = tinted(name, level)
    big = pygame.transform.scale(s, (s.get_width() * scale, s.get_height() * scale))
    _CACHE[key] = big
    return big


def draw(surf, name: str, x: int, y: int, level: float = 1.0, scale: int = 2,
         anchor: str = "bottom", glow: float = 0.0, glow_color=None):
    """把 sprite 画到世界坐标。anchor: bottom / center / topleft。

    注意: pygame 的 get_rect 不认 'bottom' 这种锚点名, 必须用 midbottom 之类的标准名,
    所以这里自己算位置, 不用 **{anchor: ...}。
    """
    big = scaled(name, level, scale)
    w, h = big.get_size()
    if anchor == "bottom":
        pos = (int(x - w / 2), int(y - h))
    elif anchor == "center":
        pos = (int(x - w / 2), int(y - h / 2))
    else:
        pos = (int(x), int(y))
    if glow > 0:
        from . import paint as P
        P.glow_at(surf, pos[0] + w // 2, pos[1] + h // 2, max(w, h),
                  glow_color or C.WARM, glow)
    surf.blit(big, pos)
    return pygame.Rect(pos[0], pos[1], w, h)


def available() -> list[str]:
    return list(_manifest()["sprites"])


# --------------------------------------------------------------------------
# 场景背景板(文生图生成的像素画, 见 tools/gen_backdrops.py)
# --------------------------------------------------------------------------
def backdrop(name: str, tint=None, alpha=255) -> pygame.Surface | None:
    """取一张 640x360 背景板。没有就返回 None, 调用方回退到程序化底。"""
    key = ("bd", name, tint, alpha)
    if key in _CACHE:
        return _CACHE[key]
    p = os.path.join(C.ASSETS, "backdrops", name + ".png")
    if not os.path.exists(p):
        return None
    s = pygame.image.load(p).convert()
    if s.get_size() != (C.VW, C.VH):
        s = pygame.transform.scale(s, (C.VW, C.VH))
    if tint:
        layer = pygame.Surface(s.get_size())
        layer.fill(tint)
        s = s.copy()
        s.blit(layer, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    if alpha < 255:
        s = s.copy()
        s.set_alpha(alpha)
    _CACHE[key] = s
    return s


def has_backdrop(name: str) -> bool:
    return os.path.exists(os.path.join(C.ASSETS, "backdrops", name + ".png"))

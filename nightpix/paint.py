# -*- coding: utf-8 -*-
"""夜间绘画工具箱: 渐变天幕 / 光晕 / 光锥 / 灯芯 / 暗角 / 颗粒 / 雨丝 / 星空 / 转场。

设计原则: 所有"静态叠加层"(渐变底、暗角、颗粒、扫描线)都在初始化时用 numpy 烘一次,
之后逐帧只做一次 blit/set_alpha —— 保证 5400 帧跑得动。
"""
import math
import random

import numpy as np
import pygame

from . import config as C


# --------------------------------------------------------------------------
# 基础
# --------------------------------------------------------------------------
def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(c1, c2, t) -> tuple[int, int, int]:
    t = clamp(t)
    return tuple(int(round(lerp(c1[i], c2[i], t))) for i in range(3))


def scale_color(c, k) -> tuple[int, int, int]:
    return tuple(int(max(0, min(255, c[i] * k))) for i in range(3))


def add_color(c, d) -> tuple[int, int, int]:
    return tuple(int(max(0, min(255, c[i] + d[i]))) for i in range(3))


def surface(w=None, h=None, alpha=False) -> pygame.Surface:
    s = pygame.Surface((w or C.VW, h or C.VH), pygame.SRCALPHA if alpha else 0)
    return s


def blit_np(surf: pygame.Surface, rgb: np.ndarray):
    """把 (H, W, 3) uint8 的 numpy 图贴到 Surface 上(替代已弃用的 surfarray.blit_array)。"""
    arr = np.ascontiguousarray(rgb.transpose(1, 0, 2))      # (W, H, 3)
    pygame.surfarray.pixels3d(surf)[:] = arr


def make_gradient(top, bot, h=None, w=None) -> pygame.Surface:
    """竖直渐变(带 4x4 Bayer 抖动, 避免深色渐变出现色带)。"""
    h, w = h or C.VH, w or C.VW
    t = (np.arange(h, dtype=np.float32)[:, None] / max(1, h - 1)) ** 0.9
    a = np.array(top, dtype=np.float32)[None, None, :]
    b = np.array(bot, dtype=np.float32)[None, None, :]
    img = a * (1 - t[:, :, None]) + b * t[:, :, None]
    bayer = np.array(((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5)),
                     dtype=np.float32) / 16.0
    tile = np.tile(bayer, (h // 4 + 2, w // 4 + 2))[:h, :w][:, :, None]
    levels = ((t * 7) % 1.0)[:, :, None]
    img = np.where(tile < levels * 0.30, img + (b - img) * 0.10, img)
    s = pygame.Surface((w, h))
    blit_np(s, np.clip(img, 0, 255).astype(np.uint8))
    return s


def radial_glow(r: int, color, strength: float = 1.0, steps: int = 22) -> pygame.Surface:
    """中心亮、向外衰减的软光斑(用于灯光/屏幕光)。"""
    d = r * 2
    img = np.zeros((d, d, 3), dtype=np.float32)
    yy, xx = np.mgrid[0:d, 0:d]
    dist = np.sqrt((xx - r) ** 2 + (yy - r) ** 2) / max(1, r)
    k = np.clip(1.0 - dist, 0.0, 1.0) ** 2.1
    col = np.array(color, dtype=np.float32)
    img = col[None, None, :] * k[:, :, None] * strength
    s = pygame.Surface((d, d), pygame.SRCALPHA)
    blit_np(s, np.clip(img, 0, 255).astype(np.uint8))
    a = np.clip(k * 255 * strength, 0, 255).astype(np.uint8)
    pygame.surfarray.pixels_alpha(s)[:] = np.ascontiguousarray(a.transpose(1, 0))
    return s


def glow_at(surf, cx, cy, r, color, strength=1.0, additive=True):
    g = radial_glow(r, color, strength)
    flags = pygame.BLEND_RGB_ADD if additive else 0
    surf.blit(g, (int(cx - r), int(cy - r)), special_flags=flags)


def pool_glow(surf, cx, cy, rx: int, ry: int, color, strength: float = 0.5,
              additive=True):
    """椭圆光池: 比多边形光锥自然得多, 用于屏幕光/灯光落地/光束。

    做法是画一个径向光斑再非等比拉伸 —— 得到柔和、无硬边的椭圆衰减。
    """
    if strength <= 0 or rx <= 0 or ry <= 0:
        return
    r = max(4, min(rx, ry))
    base = radial_glow(r, color, strength)
    w, h = rx * 2, ry * 2
    if (w, h) != base.get_size():
        base = pygame.transform.smoothscale(base, (w, h))
    flags = pygame.BLEND_RGB_ADD if additive else 0
    surf.blit(base, (int(cx - rx), int(cy - ry)), special_flags=flags)


def lamp_core(surf, cx, cy, r: float, color, level: float):
    """灯芯: 中心过曝白点 + 彩色光晕。level 0..1 直接控制亮度。"""
    if level <= 0.02:
        return
    rr = max(2, int(r))
    glow_at(surf, cx, cy, rr * 6, color, 0.09 * level)
    glow_at(surf, cx, cy, rr * 3, color, 0.16 * level)
    glow_at(surf, cx, cy, int(rr * 1.6), lerp_color(color, C.BRIGHT, 0.45), 0.26 * level)
    if level > 0.35:
        pygame.draw.circle(surf, lerp_color(color, C.BRIGHT, 0.75 * level),
                           (int(cx), int(cy)), max(1, int(rr * 0.5)))


def light_cone(surf, apex, angle_deg: float, spread_deg: float, length: float,
               color, strength: float = 0.5, soft: bool = True, additive: bool = True):
    """从 apex 射出的光锥。用 5 层递增长度的薄锥叠加, 得到随距离衰减的软边光束;
    没有退化为硬边多边形 —— 那样在暗场里会像一块贴纸。
    """
    strength = clamp(strength, 0, 1)
    if strength <= 0:
        return
    ax, ay = apex
    layer = pygame.Surface((C.VW, C.VH), pygame.SRCALPHA)
    n = 8
    for step in range(1, 6):
        k = step / 5.0
        ln = length * k
        # 越靠外越淡(模拟衰减), 总能量靠叠加累积
        a = int(11 * strength * (1.0 - 0.55 * (k - 0.2)))
        if a <= 0:
            continue
        pts = [(ax, ay)]
        for i in range(n + 1):
            ang = math.radians(angle_deg - spread_deg / 2 + spread_deg * i / n)
            pts.append((ax + math.cos(ang) * ln, ay + math.sin(ang) * ln))
        pygame.draw.polygon(layer, (*color, a), pts)
    flags = pygame.BLEND_RGBA_ADD if additive else 0
    surf.blit(layer, (0, 0), special_flags=flags)


def dither_gradient_rect(surf, rect, top, bot, t_key=0.5):
    """给一个矩形区域铺抖动渐变(墙面/床面受光用)。"""
    x, y, w, h = rect
    s = make_gradient(top, bot, h=h, w=w)
    surf.blit(s, (x, y))


# --------------------------------------------------------------------------
# 后处理: 暗角 / 颗粒 / 扫描线 / 色阶
# --------------------------------------------------------------------------
class NightFX:
    """一次性烘好暗角 + 扫描线 + 颗粒, 每帧叠一次。"""

    def __init__(self, seed: int = 21, grain: float = 0.55, vignette: float = 1.0):
        self.rnd = random.Random(seed)
        self.grain = grain
        self._grain_frames = []
        for i in range(6):                                  # 6 帧颗粒循环, 足够看不出重复
            g = pygame.Surface((C.VW, C.VH), pygame.SRCALPHA)
            rnd = random.Random(seed + i)
            # 颗粒是 x264 最贵的东西: 密度降到 1.7%, 亮度降到 ±6 以内。
            # 这样保留"老胶片起雾"的质感, 码率却只涨约 15%。
            for _ in range(int(C.VW * C.VH * 0.017 * grain)):
                x, y = rnd.randrange(C.VW), rnd.randrange(C.VH)
                k = rnd.choice((5, 7, 9, 11))
                g.set_at((x, y), (k, k, k, 255))
            self._grain_frames.append(g)
        # 暗角
        yy, xx = np.mgrid[0:C.VH, 0:C.VW]
        d = np.sqrt(((xx - C.VW / 2) / (C.VW / 2)) ** 2 + ((yy - C.VH / 2) / (C.VH / 2)) ** 2)
        k = np.clip(1.0 - np.clip(d - 0.42, 0, None) ** 1.7 * (1.35 * vignette), 0.06, 1.0)
        self.vig = pygame.Surface((C.VW, C.VH))
        rgb = np.repeat((k * 255)[:, :, None], 3, axis=2).astype(np.uint8)
        blit_np(self.vig, rgb)
        self.scan = pygame.Surface((C.VW, C.VH))
        sc = np.ones((C.VH, C.VW, 3), dtype=np.float32) * 255
        sc[2::3, :, :] *= 0.93
        blit_np(self.scan, sc.astype(np.uint8))

    def apply(self, surf: pygame.Surface, t: float = 0.0, grain=True, scan=True,
              vignette=True):
        if scan:
            surf.blit(self.scan, (0, 0), special_flags=pygame.BLEND_MULT)
        if vignette:
            surf.blit(self.vig, (0, 0), special_flags=pygame.BLEND_MULT)
        if grain:
            # 每 5 帧才换一格颗粒: 静态颗粒既能保留胶片感, 又不会把 x264 的码率拉爆
            surf.blit(self._grain_frames[int(t * 6) % len(self._grain_frames)], (0, 0),
                      special_flags=pygame.BLEND_RGB_ADD)


def dim(surf, k: float, color=None):
    """整体压暗/染色(k<1 压暗)。"""
    if k >= 0.999:
        return
    layer = pygame.Surface((C.VW, C.VH))
    layer.fill(color or C.VOID)
    layer.set_alpha(int(clamp(1 - k) * 255))
    surf.blit(layer, (0, 0))


def tint(surf, color, alpha: int):
    layer = pygame.Surface((C.VW, C.VH))
    layer.fill(color)
    layer.set_alpha(int(alpha))
    surf.blit(layer, (0, 0))


def flash(surf, color=C.BRIGHT, alpha=90):
    if alpha > 0:
        tint(surf, color, alpha)


# --------------------------------------------------------------------------
# 气候: 雨 / 星 / 尘埃
# --------------------------------------------------------------------------
class Rain:
    """斜雨(窗口外的夜雨 / 房间里的氛围雨声可视化)。"""

    def __init__(self, rnd, n=70, area=None, speed=(190, 300), slant=-0.28, length=(6, 16)):
        self.a = area or (0, 0, C.VW, C.VH)
        self.slant = slant
        self.p = []
        for _ in range(n):
            self.p.append([rnd.uniform(self.a[0], self.a[0] + self.a[2]),
                           rnd.uniform(self.a[1], self.a[1] + self.a[3]),
                           rnd.uniform(*speed), rnd.uniform(*length)])

    def update(self, dt):
        for q in self.p:
            q[0] += self.slant * q[2] * dt
            q[1] += q[2] * dt
            if q[1] > self.a[1] + self.a[3]:
                q[1] = self.a[1] - 8
                q[0] = random.uniform(self.a[0], self.a[0] + self.a[2])
            if q[0] < self.a[0]:
                q[0] = self.a[0] + self.a[2]

    def draw(self, surf, color=(96, 122, 168)):
        for x, y, _, ln in self.p:
            pygame.draw.line(surf, color, (int(x), int(y)),
                             (int(x + self.slant * ln), int(y + ln)))


class Dust:
    """浮尘 / 光里的微尘: 只在灯光附近可见。"""

    def __init__(self, rnd, n=40, area=None):
        self.a = area or (0, 0, C.VW, C.VH)
        self.p = [[rnd.uniform(self.a[0], self.a[0] + self.a[2]),
                   rnd.uniform(self.a[1], self.a[1] + self.a[3]),
                   rnd.uniform(2.5, 7.0), rnd.uniform(0, math.tau),
                   rnd.uniform(0.4, 1.0)] for _ in range(n)]

    def update(self, dt):
        for q in self.p:
            q[1] -= q[2] * dt
            q[3] += dt * 1.6
            if q[1] < self.a[1] - 6:
                q[1] = self.a[1] + self.a[3]

    def draw(self, surf, color=C.WARM, level=1.0):
        for x, y, _, ph, s in self.p:
            k = (0.5 + 0.5 * math.sin(ph)) * s * level
            if k < 0.25:
                continue
            c = lerp_color(C.NIGHT1, color, clamp(k, 0, 1))
            surf.set_at((int(x) % C.VW, int(y) % C.VH), c)


class Stars:
    def __init__(self, rnd, n=90, ymax=200):
        self.p = [[rnd.randrange(C.VW), rnd.randrange(ymax),
                   rnd.uniform(0, math.tau), rnd.uniform(0.6, 1.0)] for _ in range(n)]

    def draw(self, surf, t: float, level=1.0):
        for x, y, ph, s in self.p:
            k = (0.55 + 0.45 * math.sin(ph + t * 1.2)) * s * level
            if k < 0.35:
                continue
            c = lerp_color(C.NIGHT1, C.BRIGHT, clamp(k, 0, 1))
            surf.set_at((x, y), c)
            if k > 0.92:
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    px, py = x + dx, y + dy
                    if 0 <= px < C.VW and 0 <= py < C.VH:
                        surf.set_at((px, py), lerp_color(C.NIGHT1, C.BRIGHT, 0.45))


# --------------------------------------------------------------------------
# 转场
# --------------------------------------------------------------------------
_BAYER4 = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))


def dither_wipe(surf, progress: float, color=C.VOID, cell: int = 4):
    p = clamp(progress)
    if p <= 0:
        return
    for by in range(0, C.VH, cell):
        for bx in range(0, C.VW, cell):
            th = (_BAYER4[(by // cell) & 3][(bx // cell) & 3] + 0.5) / 16.0
            if p > th:
                surf.fill(color, (bx, by, cell, cell))


def bars_wipe(surf, progress: float, color=C.VOID, bars: int = 14):
    p = clamp(progress)
    h = C.VH / bars
    for i in range(bars):
        surf.fill(color, (0, int(i * h), int(C.VW * p), int(h) + 1))


def fade_through(surf, k: float, color=C.VOID):
    """k: 0=不遮, 1=全遮。"""
    tint(surf, color, int(clamp(k) * 255))


# --------------------------------------------------------------------------
# 版式
# --------------------------------------------------------------------------
CAP_RECT = pygame.Rect(120, 252, 400, 78)       # 字幕安全区(1600 帧里最脏的地方)
TITLE_SAFE = pygame.Rect(0, 48, 640, 300)      # 顶部 48px 留给抖音状态栏/进度


def caption_band(surf, k: float = 1.0):
    """字幕底衬: 一条自下而上淡出的暗带(最下方最实), 保证白字在任何画面上都读得清。"""
    if k <= 0:
        return
    h = 130
    s = pygame.Surface((C.VW, h), pygame.SRCALPHA)
    for i in range(h):
        a = int(118 * k * (1.0 - (i / (h - 1.0)) ** 1.6))
        pygame.draw.line(s, (4, 6, 12, a), (0, i), (C.VW, i))
    surf.blit(s, (0, C.VH - h))


def progress_line(surf, ratio: float, color=None, y: int = 22):
    pygame.draw.line(surf, (36, 45, 68), (0, y), (C.VW, y))
    x = int(C.VW * clamp(ratio))
    if x > 0:
        pygame.draw.line(surf, color or C.WARM, (0, y), (x, y))
        surf.set_at((x, y), lerp_color(color or C.WARM, C.BRIGHT, 0.6))


def watermark(surf, text="@提灯的人 · 深夜研究", color=None):
    from . import pixeltext as T
    T.draw(surf, text, 12, C.VH - 16, color=color or (108, 120, 148),
           size=C.FONT_SIZE_SMALL, outline=(0, 0, 0), anchor="bottomleft")


def act_tag(surf, text, color=None):
    from . import pixeltext as T
    T.draw(surf, text, C.VW - 12, C.VH - 16, color=color or (108, 120, 148),
           size=C.FONT_SIZE_SMALL, outline=(0, 0, 0), anchor="bottomright")


def source_tag(surf, text):
    """出处角标(实证引用)。"""
    from . import pixeltext as T
    T.draw(surf, text, C.VW - 12, 34, color=(96, 108, 136), size=C.FONT_SIZE_SMALL,
           outline=(0, 0, 0), anchor="topright")


def title_card(surf, main: str, sub: str = "", k: float = 1.0, color=None):
    """片名卡: 主标题 + 副标题, 带下划线光条。"""
    from . import pixeltext as T
    cx = C.VW // 2
    T.draw(surf, main, cx, 138, color=color or C.BRIGHT, size=C.FONT_SIZE_TITLE,
           bold=True, outline=(0, 0, 0), anchor="center")
    w = T.measure(main, C.FONT_SIZE_TITLE, True)[0]
    pygame.draw.line(surf, lerp_color(C.NIGHT2, C.WARM, 0.7),
                     (cx - w // 2, 154), (cx + w // 2, 154))
    if sub:
        T.draw(surf, sub, cx, 172, color=C.MUTE, size=C.FONT_SIZE,
               outline=(0, 0, 0), anchor="center")

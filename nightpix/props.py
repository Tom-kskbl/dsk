# -*- coding: utf-8 -*-
"""夜间道具库: 床 / 手机 / 时钟 / 脑剖面 / 折线图 / 信息卡 / 灯 / 家具。

全部用 pygame.draw 在同一条像素网格上画, 颜色只取 config 里的夜间调色板 +
两个光源色, 保证整片视觉统一。每个道具函数都接受 (surf, rect/pos, ...) 与
一个 0..1 的进度量, 便于逐帧做动画。
"""
import math

import pygame

from . import config as C
from . import paint as P
from . import pixeltext as T


# --------------------------------------------------------------------------
# 时间 / 刻度
# --------------------------------------------------------------------------
def clock(surf, cx, cy, r: int, hh: int, mm: int, glow=True, digit=True):
    """像素挂钟。hh/mm 是现实时间, 指针按它画。"""
    if glow:
        P.glow_at(surf, cx, cy, int(r * 2.4), C.WARM_DEEP, 0.16)
    pygame.draw.circle(surf, (18, 23, 40), (cx, cy), r)
    pygame.draw.circle(surf, (52, 64, 96), (cx, cy), r, 1)
    for i in range(12):
        a = math.radians(i * 30 - 90)
        r0, r1 = (r - 3, r - 1) if i % 3 == 0 else (r - 2, r - 1)
        pygame.draw.line(surf, (86, 100, 140),
                         (cx + math.cos(a) * r0, cy + math.sin(a) * r0),
                         (cx + math.cos(a) * r1, cy + math.sin(a) * r1))
    a_h = math.radians((hh % 12) * 30 + mm * 0.5 - 90)
    a_m = math.radians(mm * 6 - 90)
    pygame.draw.line(surf, P.lerp_color(C.TEXT, C.BRIGHT, 0.4), (cx, cy),
                     (cx + math.cos(a_h) * r * 0.45, cy + math.sin(a_h) * r * 0.45), 2)
    pygame.draw.line(surf, C.BRIGHT, (cx, cy),
                     (cx + math.cos(a_m) * r * 0.72, cy + math.sin(a_m) * r * 0.72), 1)
    pygame.draw.circle(surf, C.WARM, (cx, cy), 1)
    if digit:
        T.draw(surf, f"{hh:02d}:{mm:02d}", cx, cy + r + 4, color=C.MUTE,
               size=C.FONT_SIZE_SMALL, anchor="midtop")


def time_bar(surf, rect, labels, t: float, color=C.COOL):
    """横轴时间条: 刻度 + 当前时间游标(t=0..1)。"""
    x, y, w, h = rect
    pygame.draw.line(surf, (46, 56, 84), (x, y), (x + w, y), 1)
    n = len(labels)
    for i, lab in enumerate(labels):
        px = x + int(w * i / max(1, n - 1))
        pygame.draw.line(surf, (72, 86, 120), (px, y - 2), (px, y + 2), 1)
        T.draw(surf, lab, px, y + 4, color=C.DIM, size=C.FONT_SIZE_SMALL, anchor="midtop")
    cur = x + int(w * P.clamp(t))
    pygame.draw.line(surf, P.lerp_color(color, C.BRIGHT, 0.5), (cur, y - 5), (cur, y - 1), 2)
    return cur


# --------------------------------------------------------------------------
# 家具 / 房间
# --------------------------------------------------------------------------
def bed(surf, x, y, w=190, h=64, lit=0.3):
    """侧视的床: 床架 + 被褥 + 枕头。"""
    P.dither_gradient_rect(surf, (x, y, w, h), (26, 33, 54), (16, 21, 36))
    pygame.draw.rect(surf, (22, 28, 46), (x, y, w, h))
    pygame.draw.rect(surf, (52, 63, 92), (x, y, w, h), 1)
    pygame.draw.rect(surf, (34, 43, 68), (x + 6, y + 6, w - 12, h - 18))     # 被子
    pygame.draw.rect(surf, (46, 57, 88), (x + 6, y + 6, w - 12, 8))
    pygame.draw.rect(surf, (40, 49, 76), (x + 10, y + 10, 46, 20))          # 枕头
    pygame.draw.rect(surf, (56, 68, 100), (x + 10, y + 10, 46, 2))
    pygame.draw.rect(surf, (30, 38, 58), (x - 3, y + h - 8, w + 6, 8))       # 床腿横梁
    if lit > 0:
        P.glow_at(surf, x + w * 0.5, y, 40, C.COOL, 0.10 * lit)


def window_night(surf, rect, t: float, rain=True, moon=True, stars=70):
    """雨夜窗: 窗外有月光/星星/雨, 窗框是暗色。"""
    x, y, w, h = rect
    pygame.draw.rect(surf, (30, 40, 66), (x - 3, y - 3, w + 6, h + 6))
    sky = P.make_gradient((16, 24, 46), (28, 36, 58), h=h, w=w)
    surf.blit(sky, (x, y))
    if stars:
        rnd = __import__("random").Random(9)
        for _ in range(stars):
            sx, sy = rnd.randrange(w), rnd.randrange(int(h * 0.7))
            surf.set_at((x + sx, y + sy), P.lerp_color((20, 28, 50), C.BRIGHT, rnd.random()))
    if moon:
        P.glow_at(surf, x + w * 0.72, y + h * 0.28, 30, C.COOL, 0.22)
        pygame.draw.circle(surf, (222, 230, 246), (int(x + w * 0.72), int(y + h * 0.28)), 9)
        pygame.draw.circle(surf, (196, 208, 232), (int(x + w * 0.72 + 3), int(y + h * 0.28 - 2)), 3)
    if rain:
        r = P.Rain(__import__("random").Random(4), n=46,
                   area=(x, y, w, h), speed=(150, 240), slant=-0.3, length=(5, 12))
        r.update(t * 0.4)
        r.draw(surf, (108, 134, 182))
    pygame.draw.line(surf, (44, 55, 82), (x + w // 2, y), (x + w // 2, y + h), 1)
    pygame.draw.line(surf, (44, 55, 82), (x, y + h // 2), (x + w, y + h // 2), 1)
    pygame.draw.rect(surf, (34, 44, 68), (x, y, w, h), 1)


def phone(surf, rect, t: float, screen_glow=1.0, content="feed", progress=0.0):
    """手机: 冷光屏 + 内容滚动。content: feed(信息流) / chat(聊天) / clock(时间)。

    屏幕本身是画面里最亮的冷光源 —— 加色光池 + 亮屏底色 + 内容, 三层一起做。
    """
    x, y, w, h = rect
    g = P.clamp(screen_glow)
    P.glow_at(surf, x + w / 2, y + h / 2, int(max(w, h) * 1.35), C.COOL, 0.30 * g)
    P.pool_glow(surf, x + w / 2, y + h / 2, int(w * 2.6), int(h * 1.2), C.COOL, 0.20 * g)
    pygame.draw.rect(surf, (28, 34, 52), (x - 3, y - 3, w + 6, h + 6), border_radius=5)
    pygame.draw.rect(surf, (12, 17, 32), (x, y, w, h))
    inner = pygame.Rect(x + 3, y + 6, w - 6, h - 12)
    # 亮屏底: 冷白
    pygame.draw.rect(surf, P.lerp_color((150, 178, 216), (238, 246, 255), 0.55 * g), inner)
    if content == "feed":
        off = (t * 26.0) % 30.0
        for i in range(9):
            cy = int(inner.y + i * 30 - off)
            if cy < inner.y - 26 or cy > inner.bottom:
                continue
            card = pygame.Rect(inner.x + 3, cy, inner.w - 6, 26)
            shade = 0.35 + 0.45 * ((i * 37) % 7) / 7.0
            pygame.draw.rect(surf, P.lerp_color((70, 92, 128), (188, 212, 244), shade), card)
            pygame.draw.rect(surf, (222, 236, 255), card, 1)
            for k in range(2):
                lw = int(card.w * (0.75 - 0.25 * k))
                pygame.draw.line(surf, (245, 250, 255), (card.x + 4, card.y + 8 + k * 8),
                                 (card.x + 4 + lw, card.y + 8 + k * 8), 1)
    elif content == "chat":
        for i in range(5):
            cy = inner.y + 8 + i * 26
            mine = i % 2 == 0
            bw = int(inner.w * (0.45 + 0.1 * ((i * 13) % 3)))
            bx = inner.x + (inner.w - bw - 6 if mine else 6)
            pygame.draw.rect(surf, (86, 122, 176) if mine else (196, 214, 240),
                             (bx, cy, bw, 18), border_radius=4)
            pygame.draw.line(surf, (250, 253, 255), (bx + 5, cy + 9),
                             (bx + bw - 6, cy + 9), 1)
    pygame.draw.rect(surf, (86, 104, 144), (x, y, w, h), 1, border_radius=2)


# --------------------------------------------------------------------------
# 示意图: 大脑 / 曲线 / 环 / 拔河
# --------------------------------------------------------------------------
def brain(surf, rect, t: float, pfc: float = 1.0, amygdala: float = 0.2):
    """大脑侧面剖面: 前额叶电量(pfc) + 杏仁核警报(amygdala)。"""
    x, y, w, h = rect
    cx, cy = x + w // 2, y + h // 2
    # 轮廓: 用圆/椭圆拼出大脑侧影
    base = (54, 66, 100)
    pygame.draw.ellipse(surf, base, (x, y + 6, w, h - 12))
    pygame.draw.ellipse(surf, base, (x + int(w * 0.05), y - 2, int(w * 0.62), int(h * 0.7)))
    pygame.draw.ellipse(surf, (66, 80, 118), (x + int(w * 0.30), y + 2, int(w * 0.55),
                                             int(h * 0.62)))
    # 沟回
    for i in range(1, 6):
        px = x + int(w * i / 6)
        pygame.draw.arc(surf, (40, 50, 80), (px - 14, y + 10, 28, h - 26), 0.6, 2.4, 1)
    # 前额叶(左侧)电量
    lit = int(255 * P.clamp(pfc))
    col = P.lerp_color(C.ALERT, C.WARM, pfc) if pfc < 0.6 else P.lerp_color(C.WARM, C.GOOD, (pfc - 0.6) / 0.4)
    layer = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(layer, (*col, int(70 + 110 * pfc)), (x + 2, y + 12, int(w * 0.34), h - 24))
    surf.blit(layer, (0, 0))
    P.glow_at(surf, x + w * 0.18, cy, int(w * 0.22), col, 0.35 * max(0.25, pfc))
    # 杏仁核(中下) 警报
    ax, ay = x + int(w * 0.46), y + int(h * 0.66)
    pulse = 0.6 + 0.4 * abs(math.sin(t * 5.0))
    if amygdala > 0.05:
        P.glow_at(surf, ax, ay, int(14 * (0.7 + amygdala)), C.ALERT, 0.5 * amygdala * pulse)
        pygame.draw.circle(surf, P.lerp_color(C.ALERT, C.WARM_HOT, 0.35 * pulse), (ax, ay),
                           max(3, int(4 + 2 * amygdala)))
    return pygame.Rect(x, y, w, h)


def battery(surf, rect, level: float, label="前额叶·自控资源", alert_below=0.35):
    """电量条: 讲"刹车没了"时它从 100% 掉到 35%。"""
    x, y, w, h = rect
    level = P.clamp(level)
    T.draw(surf, label, x, y - 14, color=C.MUTE, size=C.FONT_SIZE_SMALL)
    pygame.draw.rect(surf, (16, 21, 36), (x, y, w, h))
    col = C.GOOD if level > 0.6 else (C.WARM if level > alert_below else C.ALERT)
    fill = max(1, int((w - 4) * level))
    for i in range(fill):                       # 分段电池格
        if i % 6 < 5:
            pygame.draw.line(surf, col, (x + 2 + i, y + 2), (x + 2 + i, y + h - 3))
    pygame.draw.rect(surf, (86, 100, 140), (x, y, w, h), 1)
    pygame.draw.rect(surf, (86, 100, 140), (x + w, y + h // 4, 3, h // 2))
    T.draw(surf, f"{int(level * 100)}%", x + w + 10, y + h // 2, color=col,
           size=C.FONT_SIZE_SMALL, anchor="midleft")
    if level <= alert_below:
        T.draw(surf, "！告急", x, y + h + 3, color=C.ALERT, size=C.FONT_SIZE_SMALL)


def line_chart(surf, rect, series, t: float, x_labels=None, y_max=1.0, draw_cursor=True):
    """折线图(情绪夜曲线)。series: [(label, color, [v0..vn])]。t=0..1 走针进度。"""
    x, y, w, h = rect
    pygame.draw.rect(surf, (12, 17, 32), (x, y, w, h))
    for i in range(1, 4):
        yy = y + int(h * i / 4)
        pygame.draw.line(surf, (28, 35, 56), (x, yy), (x + w, yy), 1)
    pygame.draw.line(surf, (48, 58, 88), (x, y + h), (x + w, y + h), 1)
    pygame.draw.line(surf, (48, 58, 88), (x, y), (x, y + h), 1)
    if x_labels:
        for i, lab in enumerate(x_labels):
            px = x + int(w * i / max(1, len(x_labels) - 1))
            T.draw(surf, lab, px, y + h + 3, color=C.DIM, size=C.FONT_SIZE_SMALL,
                   anchor="midtop")
    n = max(len(s[2]) for s in series)
    cut = int(n * P.clamp(t))
    for label, color, vals in series:
        pts = []
        for i, v in enumerate(vals):
            if i > cut:
                break
            pts.append((x + int(w * i / max(1, n - 1)),
                        y + h - int(h * P.clamp(v / y_max, 0, 1))))
        if len(pts) > 1:
            pygame.draw.lines(surf, color, False, pts, 2)
        if pts:
            px, py = pts[-1]
            P.glow_at(surf, px, py, 7, color, 0.4)
            pygame.draw.circle(surf, color, (px, py), 2)
    # 图例
    lx, ly = x + w + 8, y + 6
    for label, color, _ in series:
        pygame.draw.line(surf, color, (lx, ly + 3), (lx + 10, ly + 3), 2)
        T.draw(surf, label, lx + 13, ly - 2, color=C.MUTE, size=C.FONT_SIZE_SMALL)
        ly += 15
    return cut / max(1, n)


def rumination_ring(surf, cx, cy, r: float, cards, t: float, n_visible=None):
    """反刍环: 台词卡沿首尾相接的圆环排布, 缓慢旋转, 逐条点亮。"""
    n = len(cards)
    n_visible = n if n_visible is None else n_visible
    for i, text in enumerate(cards):
        a = t * 0.45 + i * math.tau / n
        px = cx + math.cos(a) * r
        py = cy + math.sin(a) * r * 0.52
        w = T.measure(text, C.FONT_SIZE_SMALL)[0] + 10
        box = pygame.Rect(int(px - w / 2), int(py - 8), w, 16)
        lit = i < n_visible
        col = P.lerp_color((26, 33, 54), C.COOL, 0.25 if lit else 0.06)
        pygame.draw.rect(surf, col, box, border_radius=3)
        pygame.draw.rect(surf, P.lerp_color((40, 50, 78), C.COOL, 0.5 if lit else 0.1),
                         box, 1, border_radius=3)
        T.draw(surf, text, box.centerx, box.centery - 5, color=C.TEXT if lit else C.DIM,
               size=C.FONT_SIZE_SMALL, anchor="midtop")
    # 环本身
    for i in range(0, n):
        a0 = t * 0.45 + i * math.tau / n
        a1 = t * 0.45 + (i + 1) * math.tau / n
        steps = 8
        for k in range(steps):
            aa = a0 + (a1 - a0) * k / steps
            px = cx + math.cos(aa) * r
            py = cy + math.sin(aa) * r * 0.52
            surf.set_at((int(px) % C.VW, int(py) % C.VH), (44, 56, 86))


def tug_of_war(surf, cx, cy, rope_w: int, pull: float, t: float, labels=("睡眠", "睡眠努力")):
    """拔河: 中间的红布按 pull (0..1) 偏移; 两侧小人用力。"""
    pull = P.clamp(pull)
    y = cy
    x0, x1 = cx - rope_w // 2, cx + rope_w // 2
    pygame.draw.line(surf, (96, 108, 140), (x0, y), (x1, y), 2)
    mx = int(P.lerp(x0 + 14, x1 - 14, pull))
    pygame.draw.line(surf, (200, 92, 84), (mx, y - 7), (mx, y + 7), 3)
    # 两侧的"力量"箭头
    for side, lab in ((-1, labels[0]), (1, labels[1])):
        ax = cx + side * (rope_w // 2 - 20)
        strength = (1 - pull) if side < 0 else pull
        for k in range(3):
            ln = int(8 + 12 * strength) + k * 3
            pygame.draw.line(surf, P.lerp_color((70, 84, 120), C.WARM,
                                                 0.55 * strength + 0.1 * k),
                             (ax, y + 14 + k * 4), (ax + side * ln, y + 14 + k * 4), 1)
        T.draw(surf, lab, ax, y + 32, color=C.MUTE, size=C.FONT_SIZE_SMALL, anchor="midtop")
        # 小人: 一个方块身体 + 用力的倾斜
        bx = ax + side * 4
        pygame.draw.rect(surf, (58, 72, 108), (bx - 5, y - 26, 10, 20))
        pygame.draw.circle(surf, (70, 86, 126), (bx, y - 30), 5)
        pygame.draw.line(surf, (58, 72, 108), (bx, y - 20),
                         (bx + side * 10, y - 10), 3)


# --------------------------------------------------------------------------
# 卡片
# --------------------------------------------------------------------------
def action_card(surf, rect, idx, title, desc, done: bool, t: float, color=C.WARM):
    """行动卡(三招): done 时打勾 + 高亮。"""
    x, y, w, h = rect
    k = 1.0 if done else 0.45
    pygame.draw.rect(surf, P.lerp_color((14, 19, 34), (26, 36, 60), k), (x, y, w, h),
                     border_radius=4)
    pygame.draw.rect(surf, P.lerp_color((40, 50, 76), color, 0.7 if done else 0.15),
                     (x, y, w, h), 1, border_radius=4)
    box = pygame.Rect(x + 8, y + h // 2 - 7, 14, 14)
    pygame.draw.rect(surf, (18, 24, 40), box)
    pygame.draw.rect(surf, P.lerp_color((60, 72, 104), color, 0.6 if done else 0.2), box, 1)
    if done:
        pygame.draw.lines(surf, C.GOOD, False,
                          [(box.x + 3, box.y + 7), (box.x + 6, box.y + 10),
                           (box.x + 11, box.y + 4)], 2)
    T.draw(surf, title, x + 30, y + 9, color=C.TEXT if done else C.MUTE,
           size=C.FONT_SIZE, bold=True)
    T.draw(surf, desc, x + 30, y + 26, color=C.MUTE if done else C.DIM,
           size=C.FONT_SIZE_SMALL)
    T.draw(surf, f"0{idx}", x + w - 8, y + 8, color=P.lerp_color(C.DIM, color, 0.8 if done else 0.3),
           size=C.FONT_SIZE_SMALL, anchor="topright")


def info_card(surf, rect, text, idx, t: float, color=C.COOL, tilt=0.0):
    """信息流里的一张卡(第 6 场"手机在喂它")。"""
    x, y, w, h = rect
    pygame.draw.rect(surf, P.lerp_color((20, 28, 48), (34, 48, 78), 0.4),
                     (x, y, w, h), border_radius=3)
    pygame.draw.rect(surf, P.lerp_color((40, 52, 82), color, 0.45), (x, y, w, h), 1,
                     border_radius=3)
    T.draw(surf, text, x + 6, y + 5, color=C.TEXT, size=C.FONT_SIZE_SMALL)
    T.draw(surf, f"{idx}", x + w - 6, y + 5, color=C.DIM, size=C.FONT_SIZE_SMALL,
           anchor="topright")


def concept_card(surf, rect, tag, title, lines, t: float, accent=C.WARM):
    """概念命名卡(记忆锚点)。"""
    x, y, w, h = rect
    pygame.draw.rect(surf, (12, 17, 32), (x, y, w, h), border_radius=4)
    pygame.draw.rect(surf, P.lerp_color((44, 56, 86), accent, 0.65), (x, y, w, h), 1,
                     border_radius=4)
    tw = T.measure(tag, C.FONT_SIZE_SMALL)[0] + 12
    pygame.draw.rect(surf, P.lerp_color((30, 40, 66), accent, 0.35), (x + 8, y + 8, tw, 15),
                     border_radius=2)
    T.draw(surf, tag, x + 14, y + 11, color=accent, size=C.FONT_SIZE_SMALL)
    T.draw(surf, title, x + 8, y + 30, color=C.BRIGHT, size=C.FONT_SIZE_BIG, bold=True)
    for i, ln in enumerate(lines):
        T.draw(surf, ln, x + 8, y + 54 + i * 15, color=C.MUTE, size=C.FONT_SIZE_SMALL)

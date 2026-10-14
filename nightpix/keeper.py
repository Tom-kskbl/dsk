# -*- coding: utf-8 -*-
"""新形象: 提灯的人(Lantern Keeper)。

设计要点 —— 灯就是她的情绪:
  * 灯的亮度 = 心理能量(开场暖金 -> 深夜被压到最低 -> 日出回暖)
  * 灯的色温 = 情绪色彩(暖黄 -> 冷青 -> 回暖)
  * 灯是画面里唯一光源, 所以她的世界随灯一起明暗 —— 观众不用听懂解释就能"看见"状态
  * 纯剪影不画脸: 回避像素人脸崩坏风险, 情绪带宽反而更大

实现: 角色画在 4-5 色的小 Surface(24x38 像素)上, 直接写像素保证像素级对齐;
      三种亮度档位各烘一张, 播放时按 level 两张之间交叉混合 —— 避免缩放闪烁。
"""
import math

import pygame

from . import config as C

W, H = 26, 40                      # 角色画布(像素)
SCALE_TO_WORLD = 4                 # 世界里的显示倍率 -> 104x160 像素(1080p 里约 480px 高)

# 剪影配色: 必须比夜色(NIGHT1=12,17,32)明显亮, 否则人物会被背景吃掉
K_DARK = (26, 33, 56)
K_BASE = (52, 66, 102)
K_LIT = (92, 116, 164)
K_RIM = (168, 196, 236)


def _runs(rows):
    """rows: {(y): [(x0,x1,color), ...]} -> 直接写像素。"""
    s = pygame.Surface((W, H), pygame.SRCALPHA)
    for y, arms in rows.items():
        if not (0 <= y < H):
            continue
        for x0, x1, col in arms:
            x0 = max(0, int(x0))
            x1 = min(W - 1, int(x1))
            for x in range(x0, x1 + 1):
                s.set_at((x, y), col)
    return s


def _pose(pose: str, hair: int = 0, bob: int = 0, arm: int = 0):
    """返回 (上下身像素行)。pose: back / sit / lie / walk。"""
    rows = {}
    if pose == "lie":
        # 侧躺: 横向一条 + 头在前端, 灯在她手上(由调用方另画)
        for y in range(20, 26):
            rows[y] = [(4, 21, K_BASE if y < 23 else K_DARK)]
        rows[19] = [(4, 8, K_BASE)]                      # 头
        rows[18] = [(5, 7, K_BASE)]
        rows[24] = [(14, 20, K_LIT)]                     # 裙摆受光
        return _runs(rows)

    # 站立/坐姿的公共骨架。y 越小越靠上。
    if pose == "sit":
        hip, knee, foot = 30, 34, 35
    else:
        hip, knee, foot = 26, 32, 37

    bob = int(bob)
    head_top = (6 if pose != "sit" else 9) + bob
    # 头
    for y in range(head_top, head_top + 7):
        rows[y] = [(10, 15, K_BASE)]
    rows[head_top + 7] = [(11, 14, K_BASE)]              # 收下颌
    # 长发(垂到腰, 带轻微摆动)
    hx0 = 9 + hair
    hx1 = 16 + hair
    for i, y in enumerate(range(head_top + 2, head_top + 17)):
        off = int(round(hair * (i / 16.0)))
        rows.setdefault(y, [])
        rows[y] = [(hx0 + off, hx0 + off + 1, K_DARK)] + rows[y] + \
                  [(hx1 + off - 1, hx1 + off, K_DARK)]
    # 躯干(肩略宽, 腰收)
    for y in range(head_top + 8, hip):
        t = (y - (head_top + 8)) / max(1, hip - (head_top + 8))
        wdt = 4 if t < 0.55 else 3
        rows.setdefault(y, [])
        rows[y].append((13 - wdt, 13 + wdt, K_BASE))
    # 裙摆: 从胯部展开到膝
    for y in range(hip, knee + 1):
        t = (y - hip) / max(1, knee - hip)
        half = int(round(4 + t * 5))
        rows.setdefault(y, [])
        rows[y].append((13 - half, 13 + half, K_BASE if t < 0.7 else K_LIT))
    # 腿/脚
    for y in range(knee + 1, foot + 1):
        rows.setdefault(y, [])
        if pose == "sit":
            rows[y].append((11, 15, K_DARK))
        else:
            rows[y].append((11, 12, K_DARK))
            rows[y].append((14, 15, K_DARK))
    # 右侧边缘光(背后有光)
    for y in sorted(rows):
        arms = rows[y]
        if not arms:
            continue
        rx = max(a[1] for a in arms)
        if rx + 1 < W:
            rows[y].append((rx + 1, rx + 1, K_RIM))
    return _runs(rows)


def _levels(pose: str):
    """同一姿势的三种亮度档位(灯芯由调用方叠加, 这里只管剪影边缘)。"""
    out = {}
    for name, k in (("bright", 1.0), ("mid", 0.55), ("dark", 0.22)):
        base = _pose(pose)
        s = base.copy()
        if k < 0.999:
            layer = pygame.Surface((W, H))
            layer.fill(C.NIGHT0)
            layer.set_alpha(int((1 - k) * 190))
            s.blit(layer, (0, 0))
        out[name] = s
    return out


class Keeper:
    """一次烘好三档亮度 x 若干姿势, 播放时只做 blit。"""

    POSES = ("back", "sit", "lie", "walk")

    def __init__(self):
        self._cache: dict[str, dict] = {}

    def sprite(self, pose: str, level: float, t: float = 0.0) -> pygame.Surface:
        """level 0..1: 0 最暗(冷), 1 最亮(暖)。"""
        if pose not in self._cache:
            self._cache[pose] = _levels(pose)
        lv = self._cache[pose]
        if level >= 0.78:
            return lv["bright"]
        if level >= 0.42:
            k = (level - 0.42) / 0.36
            a, b = lv["mid"], lv["bright"]
        else:
            k = max(0.0, level / 0.42)
            a, b = lv["dark"], lv["mid"]
        s = a.copy()
        blend = b.copy()
        blend.set_alpha(int(k * 255))
        s.blit(blend, (0, 0))
        return s

    def anchor_pt(self, pose: str) -> tuple[float, float]:
        """像素坐标: 提灯的手的位置(绳子上端)。"""
        if pose == "lie":
            return 21.0, 22.0
        head_top = 9 if pose == "sit" else 6
        return 16.5, float(head_top + 20)          # 肩下, 手的位置

    def lantern_pos(self, x: int, y: int, scale: int, side: int, pose: str):
        """灯体中心的屏幕坐标。"""
        if pose == "lie":
            return x + side * 16 * scale, y - 2 * scale
        hx, hy = self.anchor_pt(pose)
        return (x + side * (hx - W / 2 + 4.5) * scale,
                y - (H - hy) * scale + 7 * scale)

    def draw(self, surf, x: int, y: int, level: float = 1.0, pose: str = "back",
             t: float = 0.0, scale: int = SCALE_TO_WORLD, lantern: bool = True,
             lantern_side: int = 1, anchor: str = "bottom", shadow=True):
        """x, y: 世界坐标; anchor=bottom 时 y 是脚底。"""
        img = self.sprite(pose, level)
        w, h = W * scale, H * scale
        if anchor == "bottom":
            pos = (int(x - w / 2), int(y - h))
        else:
            pos = (int(x - w / 2), int(y - h / 2))
        if shadow:
            self.ground_shadow(surf, x, y, scale, level)
        big = pygame.transform.scale(img, (w, h))
        # 提灯的手臂: 从像素骨架的肩部连到灯绳, 用世界坐标画线保证接得上
        if lantern:
            lx, ly = self.lantern_pos(x, y, scale, lantern_side, pose)
            hx, hy = self.anchor_pt(pose)
            ax = pos[0] + hx * scale
            ay = pos[1] + hy * scale
            arm_col = big.get_at((int(hx), int(hy)))[:3]
            for i in range(int(max(1, scale * 0.6))):
                pygame.draw.line(surf, arm_col, (int(ax), int(ay) + i),
                                 (int(lx), int(ly - 4 * scale) + i), 1)
        surf.blit(big, pos)
        if lantern:
            self.draw_lantern(surf, lx, ly, level, t, scale, lantern_side)
        return pygame.Rect(pos[0], pos[1], w, h)

    def ground_shadow(self, surf, x, y, scale, level=1.0):
        """脚下的接地阴影 + 灯光在地面的一摊亮。"""
        from . import paint as P
        w = int(14 * scale)
        h = max(2, int(2.6 * scale))
        for i in range(h):
            t = i / max(1, h - 1)
            ww = int(w * (0.55 + 0.45 * t))
            pygame.draw.line(surf, P.lerp_color(C.VOID, C.NIGHT2, 0.35 * (1 - t)),
                             (int(x - ww), int(y - h + i)), (int(x + ww), int(y - h + i)))
        if level > 0.15:
            P.glow_at(surf, x + 12 * scale, y - 1 * scale, int(11 * scale),
                      P.lerp_color(C.WARM_DEEP, C.WARM, 0.4), 0.20 * level)

    # ---- 灯 -------------------------------------------------------------
    def draw_lantern(self, surf, lx, ly, level, t, scale, side=1, cone=True):
        """lx, ly: 灯体中心的屏幕坐标。"""
        from . import paint as P
        level = clamp01(level)
        body = max(3, int(3.4 * scale))
        lx = lx + math.sin(t * 1.6) * 1.4 * scale * (1.0 - 0.45 * level)   # 提灯轻摆
        top = ly - body * 2.6
        pygame.draw.line(surf, (26, 32, 54), (int(lx), int(top)), (int(lx), int(ly - body)), 1)
        shell = P.lerp_color((26, 30, 46),
                             P.lerp_color(C.WARM_DEEP, C.WARM, level), 0.30 + 0.55 * level)
        rect = pygame.Rect(int(lx - body), int(ly - body), body * 2, int(body * 1.9))
        pygame.draw.rect(surf, shell, rect)
        pygame.draw.rect(surf, P.scale_color(shell, 0.55), rect, 1)
        core = P.lerp_color(C.COOL_DEEP, C.WARM_HOT, level)
        P.lamp_core(surf, lx, ly - body * 0.1, max(1.2, 1.15 * scale), core, level)
        if cone and level > 0.30:
            P.light_cone(surf, (lx, ly + body * 0.6), 90.0, 62.0, 22.0 * scale,
                         P.lerp_color(C.WARM_DEEP, C.WARM, level), 0.85 * level)
        return lx, ly

    # ---- 组合动作 --------------------------------------------------------
    def idle(self, surf, x, y, level=1.0, t=0.0, scale=SCALE_TO_WORLD):
        bob = math.sin(t * 1.5) * 1.1
        return self.draw(surf, x, y + bob, level, "back", t, scale)

    def walk(self, surf, x, y, level=1.0, t=0.0, scale=SCALE_TO_WORLD):
        bob = abs(math.sin(t * 2.6)) * 1.8
        return self.draw(surf, x, y - bob, level, "walk", t, scale)

    def sit(self, surf, x, y, level=1.0, t=0.0, scale=SCALE_TO_WORLD):
        return self.draw(surf, x, y, level, "sit", t, scale)

    def lie(self, surf, x, y, level=1.0, t=0.0, scale=SCALE_TO_WORLD):
        return self.draw(surf, x, y, level, "lie", t, scale)

    def shiver(self, surf, x, y, level=1.0, t=0.0, scale=SCALE_TO_WORLD, amp=0.9):
        """发抖: 灯忽明忽灭 + 剪影轻微抖动(第 7 场"越想睡越睡不着")。"""
        jx = math.sin(t * 23.0) * amp
        jy = math.cos(t * 31.0) * amp * 0.6
        flick = 0.55 + 0.45 * max(0.0, math.sin(t * 9.0)) * (0.5 + 0.5 * math.sin(t * 1.3))
        lv = clamp01(level * (0.55 + 0.45 * flick))
        return self.draw(surf, x + jx, y + jy, lv, "back", t, scale)


def clamp01(v):
    return 0.0 if v < 0 else 1.0 if v > 1 else v


# ==========================================================================
# 正面形象: 提灯的姑娘(定稿路线)
#   用"灯照亮裙摆的光斑 + 发丝上的边缘光"当视觉焦点 —— 不画脸也不空
# ==========================================================================
FW, FH = 26, 52


def _fill(rows):
    s = pygame.Surface((FW, FH), pygame.SRCALPHA)
    for y, arms in rows.items():
        if not (0 <= y < FH):
            continue
        for x0, x1, col in arms:
            for x in range(max(0, int(x0)), min(FW - 1, int(x1)) + 1):
                s.set_at((x, y), col)
    return s


def _front_pose(pose="stand", hair=0, bob=0):
    """正面站姿。hair: 发丝摆动像素; bob: 呼吸起伏。

    骨架(FW=26, 中心 x=13, 脚底 y=51):
      0-8 头发/脸   9-11 脖子   12-16 肩  17-30 上衣/腰
      31-43 裙摆(展开到脚踝)  44-49 小腿/袜  50-51 鞋
    """
    rows = {}
    y0 = int(bob)
    if pose == "sit":
        y0 += 3

    def R(y, x0, x1, col=K_BASE):
        rows.setdefault(y + y0, []).append((x0, x1, col))

    # --- 头发(内层深色, 提供外轮廓) ---
    R(0, 8, 17, K_DARK)
    R(1, 7, 18, K_DARK)
    for y in range(2, 5):
        R(y, 6, 19, K_DARK)
    # 垂发两绺(越往下越窄)
    for y in range(5, 15):
        t = (y - 5) / 9.0
        ins = int(t * 1.6) + int(round(hair))
        R(y, 6 + ins, 7 + ins, K_DARK)
        R(y, 18 - ins, 19 - ins, K_DARK)
    # --- 脸 ---
    for y in range(4, 10):
        R(y, 9, 16, K_BASE)
    R(10, 10, 15, K_BASE)
    # 刘海压额
    R(3, 10, 15, K_DARK)
    R(4, 10, 11, K_DARK)
    R(4, 15, 16, K_DARK)
    # 发丝高光(灯在她右手边 -> 右上受光)
    R(1, 15, 17, K_RIM)
    R(2, 17, 18, K_RIM)
    R(3, 18, 19, K_LIT)
    # --- 脖子 ---
    R(10, 11, 14, K_DARK)
    R(11, 11, 14, K_DARK)
    # --- 肩 / 躯干(上衣) ---
    R(12, 9, 16, K_BASE)
    for y in range(13, 16):
        R(y, 8, 17, K_BASE)
    for y in range(16, 24):
        R(y, 9, 16, K_BASE)
    for y in range(24, 31):
        R(y, 10, 15, K_BASE)
    # 背后受光: 右侧边缘一道亮
    for y in range(12, 31):
        R(y, 16, 16, K_LIT)
    # --- 手臂(两侧下垂; 右手提灯) ---
    for y in range(13, 27):
        R(y, 6, 7, K_BASE)
    for y in range(13, 31):
        R(y, 18, 19, K_BASE)
    R(30, 18, 20, K_LIT)                          # 提灯的手掌
    # --- 裙摆(阶梯式展开, 下缘受灯) ---
    for y in range(31, 44):
        t = (y - 31) / 12.0
        half = int(round(3 + t * 6))
        R(y, 13 - half, 13 + half, K_BASE)
    for y in range(40, 44):
        R(y, 15, 13 + int(round(3 + (y - 31) / 12.0 * 6)), K_LIT)
    # --- 小腿 / 鞋 ---
    for y in range(44, 50):
        R(y, 9, 10, K_DARK)
        R(y, 16, 17, K_DARK)
    R(50, 8, 11, K_DARK)
    R(50, 15, 18, K_DARK)
    R(51, 8, 11, K_DARK)
    R(51, 15, 18, K_DARK)
    if pose == "sit":
        for y in range(42, 49):
            R(y, 7, 19, K_DARK)
        R(49, 6, 20, K_DARK)
        R(50, 6, 20, K_DARK)
    return rows


def _add_rim(rows, side=1, lifts=2):
    """在朝灯那一侧加边缘光(浅色), 让剪影不是死黑一块。"""
    for y, arms in rows.items():
        if not arms:
            continue
        if side > 0:
            x = max(a[1] for a in arms)
        else:
            x = min(a[0] for a in arms)
        for k in range(lifts):
            xx = x - k * side
            if 0 <= xx < FW:
                rows[y].append((xx, xx, K_LIT if k == 0 else K_BASE))
    return rows


def _front_levels(pose="stand"):
    out = {}
    for name, k in (("bright", 1.0), ("mid", 0.55), ("dark", 0.24)):
        rows = _add_rim(_front_pose(pose), side=1, lifts=2)
        s = _fill(rows)
        if k < 0.999:
            layer = pygame.Surface((FW, FH))
            layer.fill(C.NIGHT0)
            layer.set_alpha(int((1 - k) * 190))
            s.blit(layer, (0, 0))
        out[name] = s
    return out


# --------------------------------------------------------------------------
# 形象候选(第 2 步定稿用: tools/char_concept.py)
# --------------------------------------------------------------------------
_FRONT: dict[str, dict] = {p: _front_levels(p) for p in ("stand", "sit")}


# ==========================================================================
# 背影形象(定稿路线): 背对观众的提灯姑娘
#   马尾 + 过膝长裙 + 一只手垂在身侧提灯; 不画脸 —— 剪影审美, 零恐怖谷风险
#   光从她的灯照到裙摆下缘与发丝边缘, 形成焦点
# ==========================================================================
def _back_pose(pose="stand", hair=0, bob=0):
    """背影骨架(同 FW/FH)。hair: 马尾摆动像素。"""
    rows = {}
    y0 = int(bob)
    if pose == "sit":
        y0 += 4

    def R(y, x0, x1, col=K_BASE):
        rows.setdefault(y + y0, []).append((x0, x1, col))

    sw = int(round(hair))
    # --- 头顶 + 圆弧轮廓 ---
    R(0, 10, 19, K_DARK)
    R(1, 9, 20, K_DARK)
    for y in range(2, 6):
        R(y, 8, 21, K_DARK)
    for y in range(6, 12):
        R(y, 8, 21, K_DARK)                     # 后脑
    # --- 马尾: 从头顶后方垂下, 随 hair 摆动 ---
    for i, y in enumerate(range(3, 30)):
        t = i / 26.0
        cx = 15 - 3 - int(round(t * 4)) + int(round(math.sin(i / 5.0) * 1.2)) - sw
        half = 2 if y < 20 else 2
        R(y, cx - half, cx + half, K_DARK)
    # --- 肩 / 背 ---
    for y in range(12, 16):
        R(y, 9, 20, K_BASE)
    for y in range(16, 22):
        R(y, 10, 19, K_BASE)
    for y in range(22, 28):
        R(y, 11, 18, K_BASE)
    # 背脊高光(灯在她右侧 -> 右侧边缘亮)
    for y in range(13, 28):
        R(y, 19, 19, K_LIT)
    # --- 手臂: 左手垂在身侧(提灯) + 右手 ---
    for y in range(13, 29):
        R(y, 7, 8, K_BASE)
    for y in range(13, 29):
        R(y, 21, 22, K_BASE)
    R(29, 21, 23, K_LIT)                        # 提灯那只手
    # --- 长裙(过膝, 阶梯下摆) ---
    for y in range(28, 42):
        t = (y - 28) / 13.0
        half = int(round(4 + t * 6))
        R(y, 15 - half, 15 + half, K_BASE)
    # 下摆: 灯照到的右半边更亮
    for y in range(38, 42):
        R(y, 16, 15 + (2 if y < 41 else 0) + 7, K_LIT)
    R(41, 10, 24, K_LIT)
    # --- 脚 ---
    for y in range(42, 46):
        R(y, 11, 13, K_DARK)
        R(y, 17, 19, K_DARK)
    R(46, 10, 13, K_DARK)
    R(46, 17, 20, K_DARK)
    if pose == "sit":
        for y in range(40, 46):
            R(y, 9, 21, K_DARK)
        for y in range(46, 48):
            R(y, 8, 22, K_DARK)
    return rows


def _back_levels(pose="stand"):
    out = {}
    for name, k in (("bright", 1.0), ("mid", 0.55), ("dark", 0.24)):
        s = _fill(_back_pose(pose))
        if k < 0.999:
            layer = pygame.Surface((FW, FH))
            layer.fill(C.NIGHT0)
            layer.set_alpha(int((1 - k) * 190))
            s.blit(layer, (0, 0))
        out[name] = s
    return out


_BACK: dict[str, dict] = {p: _back_levels(p) for p in ("stand", "sit")}


def _back_sprite(level: float, pose="stand") -> pygame.Surface:
    lv = _BACK.get(pose) or _BACK["stand"]
    if level >= 0.78:
        return lv["bright"]
    if level >= 0.42:
        k = (level - 0.42) / 0.36
        a, b = lv["mid"], lv["bright"]
    else:
        k = max(0.0, level / 0.42)
        a, b = lv["dark"], lv["mid"]
    s = a.copy()
    bl = b.copy()
    bl.set_alpha(int(k * 255))
    s.blit(bl, (0, 0))
    return s


def draw_keeper(surf, x, y, level=1.0, t=0.0, scale=SCALE_TO_WORLD, pose="stand",
                lantern=True, shadow=True):
    """世界坐标绘制背影提灯姑娘。x=中心, y=脚底。返回灯体中心 (lx, ly)。"""
    from . import paint as P
    lv = clamp01(level)
    b = int(round(math.sin(t * 1.5) * 1.1))
    img = _back_sprite(lv, pose)
    w, h = FW * scale, FH * scale
    rect = img.get_rect(midbottom=(int(x), int(y) - b * scale))
    if shadow:
        sw = int(9 * scale)
        for i in range(max(2, int(2.4 * scale))):
            k = i / max(1, int(2.4 * scale) - 1)
            ww = int(sw * (0.6 + 0.4 * k))
            pygame.draw.line(surf, P.lerp_color(C.VOID, C.NIGHT2, 0.42 * (1 - k)),
                             (int(x - ww), y - int(2.4 * scale) + i),
                             (int(x + ww), y - int(2.4 * scale) + i))
        if lv > 0.10:
            P.glow_at(surf, x + 7 * scale, y - 1 * scale, int(9 * scale),
                      P.lerp_color(C.WARM_DEEP, C.WARM, 0.5), 0.34 * lv)
    big = pygame.transform.scale(img, (w, h))
    surf.blit(big, rect)
    if not lantern:
        return None
    lx = x + (20 - FW / 2 + 2.2) * scale
    ly = y - (FH - 28) * scale + 2.0 * scale
    return draw_lantern_front(surf, lx, ly, lv, t, scale)


def _front_sprite(level: float, pose="stand") -> pygame.Surface:
    lv = _FRONT.get(pose) or _FRONT["stand"]
    if level >= 0.78:
        return lv["bright"]
    if level >= 0.42:
        k = (level - 0.42) / 0.36
        a, b = lv["mid"], lv["bright"]
    else:
        k = max(0.0, level / 0.42)
        a, b = lv["dark"], lv["mid"]
    s = a.copy()
    bl = b.copy()
    bl.set_alpha(int(k * 255))
    s.blit(bl, (0, 0))
    return s


def draw_front(surf, x, y, level=1.0, t=0.0, scale=SCALE_TO_WORLD, pose="stand",
               lantern=True, bob=True, shadow=True):
    """世界坐标绘制正面提灯形象。x=中心, y=脚底。"""
    from . import paint as P
    lv = clamp01(level)
    b = int(round(math.sin(t * 1.5) * 1.2)) if bob else 0
    img = _front_sprite(lv, pose)
    w, h = FW * scale, FH * scale
    rect = img.get_rect(midbottom=(int(x), int(y) - b * scale))
    if shadow:
        # 接地阴影 + 灯在地面的光池
        sw = int(9 * scale)
        for i in range(max(2, int(2.2 * scale))):
            k = i / max(1, int(2.2 * scale) - 1)
            ww = int(sw * (0.6 + 0.4 * k))
            pygame.draw.line(surf, P.lerp_color(C.VOID, C.NIGHT2, 0.4 * (1 - k)),
                             (int(x - ww), int(y - int(2.2 * scale) + i)),
                             (int(x + ww), int(y - int(2.2 * scale) + i)))
        if lv > 0.12:
            P.glow_at(surf, x + 4 * scale, y - 1 * scale, int(7 * scale),
                      P.lerp_color(C.WARM_DEEP, C.WARM, 0.5), 0.30 * lv)
    big = pygame.transform.scale(img, (w, h))
    surf.blit(big, rect)
    if lantern:
        # 手在像素 (19, 30); 灯挂在手外侧偏下
        lx = x + (19 - FW / 2 + 2.6) * scale
        ly = y - (FH - 30) * scale + 2.2 * scale
        return draw_lantern_front(surf, lx, ly, lv, t, scale)
    return rect


def draw_lantern_front(surf, lx, ly, level, t, scale):
    """正面灯: 竹骨小灯, 提在身侧。lx=中心, ly=灯体中心。"""
    from . import paint as P
    level = clamp01(level)
    body = max(3, int(2.6 * scale))
    lx += math.sin(t * 1.7) * 1.1 * scale * (1.0 - 0.4 * level)
    # 提梁 + 绳
    pygame.draw.line(surf, (30, 36, 58), (int(lx), int(ly - body * 2.4)),
                     (int(lx), int(ly - body)), 1)
    pygame.draw.arc(surf, (36, 44, 70),
                    pygame.Rect(int(lx - body), int(ly - body * 2.6), body * 2, body * 1.4),
                    0, math.pi, 1)
    shell = P.lerp_color((30, 34, 52),
                         P.lerp_color(C.WARM_DEEP, C.WARM, level), 0.35 + 0.5 * level)
    rect = pygame.Rect(int(lx - body), int(ly - body), body * 2, int(body * 1.9))
    pygame.draw.rect(surf, shell, rect)
    pygame.draw.rect(surf, P.scale_color(shell, 0.55), rect, 1)
    for gy in (rect.top + rect.h // 3, rect.top + 2 * rect.h // 3):
        pygame.draw.line(surf, P.scale_color(shell, 0.7), (rect.left + 1, gy),
                         (rect.right - 2, gy))
    core = P.lerp_color(C.COOL_DEEP, C.WARM_HOT, level)
    P.lamp_core(surf, lx, ly - body * 0.1, max(1.2, 1.0 * scale), core, level)
    return lx, ly


def _concept_a(surf, x, y, level=1.0, t=0.0, scale=SCALE_TO_WORLD):
    """A 正面提灯姑娘(4x): 主推方案。"""
    draw_front(surf, x, y, level, t, scale, "stand")


def _concept_b(surf, x, y, level=1.0, t=0.0, scale=SCALE_TO_WORLD):
    """B 远景版(3x): 人物更小, 强调环境的空。"""
    draw_front(surf, x, y, level, t, max(2, scale - 1), "stand")


def _concept_c(surf, x, y, level=1.0, t=0.0, scale=SCALE_TO_WORLD):
    """C 背面剪影(4x): 靠轮廓光, 完全不给脸。"""
    Keeper().draw(surf, x, y, level, "back", t, scale, lantern_side=1)


def _concept_a(surf, x, y, level=1.0, t=0.0, scale=SCALE_TO_WORLD):
    """A 背影提灯(4x): 定稿路线。"""
    draw_keeper(surf, x, y, level, t, scale, "stand")


def _concept_b(surf, x, y, level=1.0, t=0.0, scale=SCALE_TO_WORLD):
    """B 远景小人物(3x): 人物更小, 强调环境的空。"""
    draw_keeper(surf, x, y, level, t, max(2, scale - 1), "stand")


def _concept_c(surf, x, y, level=1.0, t=0.0, scale=SCALE_TO_WORLD):
    """C 正面版(4x): 备选, 用于对比。"""
    draw_front(surf, x, y, level, t, scale, "stand")


CONCEPTS = {"A_背影提灯": _concept_a, "B_远景小人物": _concept_b, "C_正面版": _concept_c}

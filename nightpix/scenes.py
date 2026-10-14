# -*- coding: utf-8 -*-
"""8 场分镜(640x360, 16:9)。每一场都吃 (surf, ctx, lt, dur)。

构图统一约定:
  * 地平线/地面线在 y=300
  * 字幕安全区 y∈[252, 330] 由 timeline 统一叠加, 场景主体尽量留在 y<250
  * 右侧 x>560 留白, 给抖音互动按钮
  * 全片只有两种光源: 冷(屏幕/月光) 与 暖(灯/日出)
"""
import math
import random

import pygame

from . import assets as A
from . import config as C
from . import keeper as K
from . import paint as P
from . import pixeltext as T
from . import props as R

GROUND = 300
CX = 320


def backdrop(surf, name, fallback=None, darken=0.0, tint=None):
    """铺一张背景板; 没有就回退。返回是否用了背景板。

    背景板是文生图生成的完整像素画房间, 比程序化的纯色渐变有信息量得多;
    但它不受本片调色板控制, 所以统一再压一道暗 + 可选偏色, 保持色调一致。
    """
    bd = A.backdrop(name, tint=tint)
    if bd is None:
        if fallback:
            fallback()
        return False
    surf.blit(bd, (0, 0))
    if darken > 0:
        P.dim(surf, 1.0 - darken)
    return True


# --------------------------------------------------------------------------
# 公共背景
# --------------------------------------------------------------------------
def room_base(surf, ctx, level=0.0, floor_top=None):
    """房间: 上方夜色墙, 下方地板, 中间一道极弱的地面反光。"""
    surf.blit(ctx.bg_room, (0, 0))
    if level > 0:
        P.glow_at(surf, CX, GROUND, 220, P.lerp_color(C.WARM_DEEP, C.WARM, 0.5),
                  0.06 * level)
    ft = floor_top or GROUND
    pygame.draw.line(surf, (44, 55, 84), (0, ft), (C.VW, ft))
    for i in range(1, 4):
        pygame.draw.line(surf, (20, 26, 42), (0, ft + i * 2), (C.VW, ft + i * 2))


def limbo(surf, ctx, level=0.6, t=0.0, floor=True):
    """大留白: 空房间 + 一点地面反光, 人物很小。"""
    surf.fill(C.VOID)
    surf.blit(ctx.bg_room, (0, 0))
    if floor:
        P.dither_gradient_rect(surf, (0, GROUND - 34, C.VW, 94), (16, 21, 36), (9, 12, 22))
        pygame.draw.line(surf, (34, 43, 68), (0, GROUND), (C.VW, GROUND))
    P.glow_at(surf, CX, GROUND, 260, C.WARM_DEEP, 0.05 * level)


# --------------------------------------------------------------------------
# 1. 凌晨三点的天花板
# --------------------------------------------------------------------------
def ceiling_3am(surf, ctx, lt, dur):
    """仰视: 天花板 + 房梁 + 吊灯 + 窗帘透进来的街灯 + 发光的手机 + 躺床侧影。"""
    k = P.clamp(lt / dur)
    surf.blit(ctx.bg_ceil, (0, 0))
    # 天花的斜向透视: 从画面中心向四角发散的四道房梁
    for i, (x0, y0) in enumerate(((0, 60), (C.VW, 60), (60, 0), (C.VW - 60, 0))):
        for j in range(3):
            pygame.draw.line(surf, (15, 19, 34), (CX, 150),
                             (x0 + (j - 1) * 26 * (1 if x0 else -1), y0), 1)
    pygame.draw.line(surf, (20, 26, 42), (0, 96), (C.VW, 96), 1)
    pygame.draw.line(surf, (14, 18, 32), (0, 98), (C.VW, 98), 1)
    # 吊灯(暖, 但很弱)
    lx, ly = CX + 96, 22
    pygame.draw.line(surf, (30, 37, 58), (lx, 0), (lx, ly), 1)
    pygame.draw.polygon(surf, (36, 44, 68), [(lx - 22, ly + 10), (lx + 22, ly + 10),
                                             (lx + 12, ly), (lx - 12, ly)])
    P.lamp_core(surf, lx, ly + 16, 2.4, C.WARM, 0.20)
    # 右侧窗帘: 街灯从缝里透进来
    pygame.draw.rect(surf, (14, 19, 33), (C.VW - 46, 0, 46, C.VH))
    for i in range(5):
        pygame.draw.line(surf, (20, 26, 44), (C.VW - 44 + i * 9, 0),
                         (C.VW - 44 + i * 9, C.VH), 2)
    P.pool_glow(surf, C.VW - 30, 128, 62, 190, (196, 172, 132), 0.13)
    pygame.draw.line(surf, (34, 38, 48), (C.VW - 47, 0), (C.VW - 47, C.VH), 1)
    # 手机冷光: 从右下角打上来
    ph = pygame.Rect(CX + 60, 210, 44, 74)
    R.phone(surf, ph, lt, screen_glow=0.9, content="feed")
    P.glow_at(surf, ph.centerx, ph.centery, 120, C.COOL, 0.16)
    P.pool_glow(surf, ph.centerx - 90, ph.top - 60, 180, 90, C.COOL, 0.16)
    # 床沿: 一条横向亮边把画面下方"压住", 也是仰视的参照
    bed_y = GROUND + 6
    pygame.draw.rect(surf, (30, 38, 60), (0, bed_y, C.VW, C.VH - bed_y))
    P.dither_gradient_rect(surf, (0, bed_y, C.VW, C.VH - bed_y), (30, 38, 60), (16, 21, 36))
    pygame.draw.line(surf, (62, 78, 114), (0, bed_y), (C.VW, bed_y))
    # 躺着的人: 床上侧影, 头在左(仰视: 只看见被子和一个轮廓)
    hx, hy = CX - 100, GROUND + 26
    pygame.draw.ellipse(surf, (58, 74, 110), (hx - 6, hy - 40, 152, 58))       # 被子
    pygame.draw.ellipse(surf, (74, 94, 138), (hx + 6, hy - 36, 130, 50))
    pygame.draw.circle(surf, (66, 84, 124), (hx + 4, hy - 22), 13)             # 头
    for k in range(4):                                                          # 头发
        pygame.draw.arc(surf, (44, 56, 88), (hx - 10 + k * 3, hy - 38 + k * 2, 40, 30),
                        0.4, 2.6, 1)
    # 挂钟 23:47 -> 03:12
    mins = int(P.lerp(23 * 60 + 47, 27 * 60 + 12, k)) % (24 * 60)
    R.clock(surf, 96, 96, 34, mins // 60, mins % 60, glow=True)
    T.draw(surf, "凌晨", 96, 150, color=C.MUTE, size=C.FONT_SIZE_BIG, anchor="midtop")
    if k > 0.55:
        a = int(160 * (k - 0.55) / 0.45)
        T.draw(surf, "谁又没睡", CX + 150, 40, color=P.lerp_color(C.NIGHT2, C.TEXT, 0.8),
               size=C.FONT_SIZE_BIG, anchor="midtop")


# --------------------------------------------------------------------------
# 2. 白天同一个你
# --------------------------------------------------------------------------
def two_yous(surf, ctx, lt, dur):
    """左右分屏: 15:00 的她 vs 02:30 的她, 同一件小事。"""
    k = P.clamp(lt / dur)
    half = C.VW // 2
    # 左: 白天(暖灰)
    left = pygame.Rect(0, 0, half, C.VH)
    pygame.draw.rect(surf, (58, 62, 74), left)
    P.dither_gradient_rect(surf, (0, 0, half, C.VH), (74, 78, 92), (40, 44, 56))
    P.glow_at(surf, 120, 120, 130, (255, 226, 178), 0.16)
    # 右: 深夜(冷蓝)
    right = pygame.Rect(half, 0, half, C.VH)
    surf.fill(C.NIGHT1, right)
    P.dither_gradient_rect(surf, (half, 0, half, C.VH), (14, 20, 38), (8, 11, 22))
    P.glow_at(surf, half + 200, 230, 120, C.COOL, 0.16)
    pygame.draw.line(surf, (70, 80, 108), (half, 0), (half, C.VH), 1)
    # 同一个她
    K.draw_keeper(surf, 150, GROUND, 0.85, lt, 3, "stand")
    K.draw_keeper(surf, half + 150, GROUND, 0.32, lt, 3, "stand")
    # 同一件小事: 手机上的同一行字
    T.draw(surf, "「已读不回」", 150, 96, color=(246, 232, 206), size=C.FONT_SIZE_BIG,
           bold=True, anchor="midtop")
    T.draw(surf, "「已读不回」", half + 150, 96, color=P.lerp_color(C.COOL, C.BRIGHT, 0.4),
           size=C.FONT_SIZE_BIG, bold=True, anchor="midtop")
    T.draw(surf, "15:00", 16, 14, color=(250, 236, 210), size=C.FONT_SIZE_BIG, bold=True)
    T.draw(surf, "02:30", half + 16, 14, color=C.COOL, size=C.FONT_SIZE_BIG, bold=True)
    # 情绪条: 白天不动, 深夜下行
    R.battery(surf, pygame.Rect(20, 220, 110, 10), 0.92, "情绪调节余量")
    R.battery(surf, pygame.Rect(half + 20, 220, 110, 10), 0.28, "情绪调节余量")
    if k > 0.5:
        T.draw(surf, "同一件事", CX, 268, color=C.MUTE, size=C.FONT_SIZE_SMALL,
               anchor="midtop")
        T.draw(surf, "两个完全不同的感受", CX, 282, color=C.BRIGHT, size=C.FONT_SIZE,
               anchor="midtop")


# --------------------------------------------------------------------------
# 3. 刹车没了
# --------------------------------------------------------------------------
def brake_gauge(surf, ctx, lt, dur):
    """大脑剖面 + 前额叶电量下降 + 杏仁核警报。"""
    k = P.clamp(lt / dur)
    room_base(surf, ctx, level=0.3)
    limbic = P.clamp(1.0 - k * 0.95)
    R.brain(surf, pygame.Rect(70, 60, 210, 130), lt, pfc=limbic,
            amygdala=P.clamp(0.15 + k * 0.85))
    R.battery(surf, pygame.Rect(70, 232, 190, 12), limbic,
              "前额叶 · 自控资源", alert_below=0.4)
    # 右侧: 刹车/油门 的比喻
    bx, by = 356, 96
    pygame.draw.rect(surf, (20, 26, 44), (bx, by, 236, 132), border_radius=6)
    pygame.draw.rect(surf, (44, 55, 84), (bx, by, 236, 132), 1, border_radius=6)
    T.draw(surf, "深夜的大脑", bx + 12, by + 10, color=C.MUTE, size=C.FONT_SIZE_SMALL)
    # 刹车片: 随进度磨薄
    brake_w = int(84 * limbic) + 6
    pygame.draw.rect(surf, P.lerp_color((70, 84, 120), C.ALERT, 1 - limbic),
                     (bx + 16, by + 40, brake_w, 16), border_radius=3)
    T.draw(surf, "刹车（抑制冲动）", bx + 16, by + 62, color=C.TEXT if limbic > 0.4 else C.ALERT,
           size=C.FONT_SIZE_SMALL)
    # 油门: 一直满
    pygame.draw.rect(surf, C.WARM, (bx + 16, by + 92, 96, 16), border_radius=3)
    T.draw(surf, "油门（情绪反应）", bx + 16, by + 112, color=C.WARM, size=C.FONT_SIZE_SMALL)
    P.source_tag(surf, "睡眠剥夺 → 前额叶—杏仁核耦合减弱")
    K.draw_keeper(surf, 596, GROUND + 10, limbic, lt, 3, "stand", shadow=False)


# --------------------------------------------------------------------------
# 4. 情绪夜曲线
# --------------------------------------------------------------------------
def emotion_curve(surf, ctx, lt, dur):
    """22:00 -> 04:00 双折线, 负面上升 / 正面下降, 在第 2 小时交叉。"""
    k = P.clamp(lt / dur)
    room_base(surf, ctx, level=0.2)
    labels = ["22:00", "23:00", "00:00", "01:00", "02:00", "03:00", "04:00"]
    neg = [0.22, 0.30, 0.40, 0.52, 0.68, 0.84, 0.96, 1.0, 0.98]
    pos = [0.80, 0.74, 0.66, 0.54, 0.42, 0.30, 0.20, 0.14, 0.16]
    R.line_chart(surf, pygame.Rect(56, 66, 380, 148),
                 [("负面情绪", C.ALERT, neg), ("正面感受", C.COOL, pos)],
                 k, labels)
    # 交叉点 + 凌晨两点标注
    x0, y0, w0, h0 = 56, 66, 380, 148
    if k > 0.5:
        cx = x0 + int(w0 * 0.44)
        cy = y0 + h0 - int(h0 * 0.52)
        pygame.draw.circle(surf, C.WARM, (cx, cy), 4, 1)
        pygame.draw.line(surf, P.lerp_color(C.WARM, C.VOID, 0.4), (cx, cy), (cx, cy + 26), 1)
        T.draw(surf, "交叉点 ≈ 凌晨 2 点", cx + 8, cy - 18, color=C.WARM, size=C.FONT_SIZE_SMALL)
    # 右侧: 同一件事的两种读法
    bx = 470
    T.draw(surf, "同一件事", bx, 74, color=C.MUTE, size=C.FONT_SIZE_SMALL)
    for i, (tag, txt, col) in enumerate((("15:00", "「他可能只是忙」", C.GOOD),
                                         ("02:30", "「他是不是烦我了」", C.ALERT))):
        yy = 92 + i * 52
        pygame.draw.rect(surf, (18, 24, 40), (bx, yy, 152, 40), border_radius=3)
        pygame.draw.rect(surf, P.lerp_color((40, 50, 76), col, 0.5), (bx, yy, 152, 40), 1,
                         border_radius=3)
        T.draw(surf, tag, bx + 8, yy + 7, color=col, size=C.FONT_SIZE_SMALL, bold=True)
        T.draw(surf, txt, bx + 8, yy + 22, color=C.TEXT, size=C.FONT_SIZE_SMALL)
    R.clock(surf, 596, 96, 30, (22 + int(k * 6)) % 24, int((k * 60) % 60), glow=False)
    R.time_bar(surf, pygame.Rect(56, 240, 400, 6), ["22:00", "00:00", "02:00", "04:00"], k)
    P.source_tag(surf, "Murray et al. 2009 · 情绪唤醒度夜间升高")


# --------------------------------------------------------------------------
# 5. 反刍回环
# --------------------------------------------------------------------------
def rumination_loop(surf, ctx, lt, dur):
    """台词卡被吸进首尾相接的环, 越想越紧, 环越转越快。"""
    k = P.clamp(lt / dur)
    room_base(surf, ctx, level=0.25)
    cards = ["我是不是说错话了", "他为什么不回我", "我明天怎么办",
             "是不是我又不够好", "算了，我就是这样"]
    K.draw_keeper(surf, CX, GROUND, 0.5, lt, 3, "stand")
    r = P.lerp(168, 120, k)
    R.rumination_ring(surf, CX, 138, r, cards, lt * (1.0 + k * 0.8), n_visible=int(1 + k * 4))
    T.draw(surf, "反刍：把同一件事，翻来覆去想", CX, 268, color=C.MUTE,
           size=C.FONT_SIZE_SMALL, anchor="midtop")
    if k > 0.6:
        T.draw(surf, "越想 → 越难受 → 越想", CX, 284,
               color=P.lerp_color(C.COOL, C.ALERT, (k - 0.6) / 0.4),
               size=C.FONT_SIZE, anchor="midtop")


# --------------------------------------------------------------------------
# 6. 手机在喂它
# --------------------------------------------------------------------------
def feed_glow(surf, ctx, lt, dur):
    """手机亮着 → 蓝光 → 人越暗; 「下一条」永远还有一张卡。"""
    k = P.clamp(lt / dur)
    surf.fill(C.VOID)
    surf.blit(ctx.bg_room, (0, 0))
    # 手机在左, 人站在右, 中间是流出来的信息卡
    ph = pygame.Rect(44, 168, 62, 108)
    R.phone(surf, ph, lt, screen_glow=1.0, content="feed")
    P.glow_at(surf, ph.centerx, ph.centery, 130, C.COOL, 0.20)
    P.pool_glow(surf, ph.centerx + 130, ph.centery + 10, 230, 78, C.COOL, 0.15)
    rnd = random.Random(5)
    for i in range(9):
        p = (lt * 0.30 + i * 0.11) % 1.0
        x = ph.right + 10 + p * 380
        y = 118 + math.sin(p * 5.5 + i * 1.7) * 26 + i * 4
        w = 92 + rnd.randrange(56)
        alpha = P.clamp(1.0 - abs(p - 0.5) * 1.5)
        if alpha <= 0.05:
            continue
        R.info_card(surf, pygame.Rect(int(x), int(y), w, 20), "下一条", i + 1, lt, C.COOL)
    # 蓝光把她的灯压到最暗
    K.draw_keeper(surf, 522, GROUND, P.clamp(0.30 - 0.18 * k), lt, 3, "stand")
    T.draw(surf, "屏幕越亮，你越暗", 320, 246, color=C.COOL, size=C.FONT_SIZE,
           anchor="midtop")


# --------------------------------------------------------------------------
# 7. 越想睡越睡不着
# --------------------------------------------------------------------------
def sleep_tug(surf, ctx, lt, dur):
    """床两边的拔河: 睡眠 vs 睡眠努力; 越用力越输, 灯忽明忽灭。"""
    k = P.clamp(lt / dur)
    # 背景板里已经有一张床和窗, 比程序化的色块床有说服力得多
    used = backdrop(surf, "sleep_tug")
    if not used:
        surf.blit(ctx.bg_room, (0, 0))
    else:
        P.dim(surf, 0.78)
    pull = P.clamp(0.5 + math.sin(lt * 1.1) * 0.34 + k * 0.12)
    R.tug_of_war(surf, CX, 132, 300, pull, lt)
    # 她坐在床上(背景板里的床在画面中下), 灯随"越用力越输"忽明忽灭
    K.draw_keeper(surf, CX - 40, 268, P.clamp(0.5 - 0.25 * k), lt, 3, "sit", shadow=False)
    # 时钟: 03:00 -> 04:00 一直没睡
    mins = int(P.lerp(3 * 60, 4 * 60, k))
    R.clock(surf, CX + 196, 76, 30, mins // 60, mins % 60, glow=False)
    if k > 0.45:
        a = (k - 0.45) / 0.55
        T.draw(surf, "20 分钟还没睡着？", CX - 190, 52,
               color=P.lerp_color(C.MUTE, C.TEXT, P.clamp(a * 2)), size=C.FONT_SIZE_SMALL)
        T.draw(surf, "就起来，别在床上硬躺", CX + 20, 52,
               color=P.lerp_color(C.MUTE, C.WARM, P.clamp(a * 2)), size=C.FONT_SIZE_SMALL)
    P.source_tag(surf, "刺激控制法 · 睡眠努力悖论")


# --------------------------------------------------------------------------
# 8. 天亮了 + 三招
# --------------------------------------------------------------------------
def dawn_three_moves(surf, ctx, lt, dur):
    """日出 + 三张行动卡逐条打勾。用文生图的天亮背景板打底。"""
    k = P.clamp(lt / dur)
    # 天光: 夜色 -> 日出梯度(没有背景板时的回退)
    top = P.lerp_color(C.NIGHT1, (72, 92, 138), k)
    bot = P.lerp_color(C.NIGHT0, (216, 168, 118), k)

    def _fallback():
        surf.blit(P.make_gradient(top, bot), (0, 0))

    used = backdrop(surf, "dawn", fallback=_fallback)
    if used:
        # 背景板是固定饱满的天光, 用夜色盖一下再随 k 揭开, 做出"天亮起来"的过程
        P.dim(surf, P.lerp(0.30, 1.0, k))
    # 太阳压到左下(避开右侧三张行动卡), 也不和人物重叠
    sun_x, sun_y = 108, P.lerp(352, 262, k)
    P.glow_at(surf, sun_x, sun_y, int(P.lerp(90, 190, k)), (255, 206, 140), 0.22 + 0.2 * k)
    pygame.draw.circle(surf, (255, 226, 172), (sun_x, int(sun_y)), int(P.lerp(11, 20, k)))
    for i in range(1, 5):
        yy = int(sun_y + i * 14)
        if yy < C.VH:
            pygame.draw.line(surf, P.lerp_color(bot, (250, 210, 160), 0.5 / i),
                             (0, yy), (C.VW, yy), 1)
    pygame.draw.line(surf, (34, 43, 68), (0, 268), (C.VW, 268))
    # 人物站在左侧偏中, 避开左边缘的字幕角标
    K.draw_keeper(surf, 150, 268, P.clamp(0.55 + 0.45 * k), lt, 3, "stand")
    cards = [("写下来", "把担心写成具体的句子，标上概率"),
             ("别硬躺", "20 分钟睡不着就离开床"),
             ("别在深夜决定", "凌晨的判断等于疲劳驾驶")]
    n_done = int(k * 3.4)
    for i, (title, desc) in enumerate(cards):
        done = i < n_done
        R.action_card(surf, pygame.Rect(268, 74 + i * 62, 330, 52), i + 1, title, desc,
                      done, lt, C.WARM)
    if k > 0.85:
        T.draw(surf, "天亮了，你会觉得" + "还好", CX, 258, color=(70, 60, 50),
               size=C.FONT_SIZE_SMALL, anchor="midtop")


SCENES = {
    "ceiling_3am": ceiling_3am,
    "two_yous": two_yous,
    "brake_gauge": brake_gauge,
    "emotion_curve": emotion_curve,
    "rumination_loop": rumination_loop,
    "feed_glow": feed_glow,
    "sleep_tug": sleep_tug,
    "dawn_three_moves": dawn_three_moves,
}

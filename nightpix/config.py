# -*- coding: utf-8 -*-
"""全局配置: 画布 / 帧率 / 夜间调色板 / 字体 / 路径。

画面在 640x360 的"虚拟像素画布"上以 1:1 像素绘制, 最后由 ffmpeg 用最近邻
放大 3 倍输出 1920x1080 —— 所有元素共享同一条像素网格。
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASSETS = os.path.join(ROOT, "assets")
OUT = os.path.join(ROOT, "out")
CACHE = os.path.join(ROOT, ".cache")
DOCS = os.path.join(ROOT, "docs")

VW, VH = 640, 360
SCALE = 3
FPS = 30


def set_canvas(w: int, h: int, scale: int = 3):
    """切换虚拟画布。16:9 -> (640, 360, 3) = 1920x1080。"""
    global VW, VH, SCALE
    VW, VH, SCALE = w, h, scale
    return VW, VH, SCALE


# --- 夜间调色板 -----------------------------------------------------------
# 全片只有两种光: 冷(夜色/屏幕) 与 暖(灯/日出)。其余都是它们的衰减。
VOID = (4, 6, 12)             # 比夜色更黑的底
NIGHT0 = (7, 10, 20)          # 夜色最深处
NIGHT1 = (12, 17, 32)         # 夜色
NIGHT2 = (19, 26, 46)         # 夜色偏亮(墙面)
NIGHT3 = (30, 40, 66)         # 受光面

DIM = (78, 90, 118)           # 暗部细节
MUTE = (116, 130, 160)        # 次要文字
TEXT = (206, 214, 230)        # 正文
BRIGHT = (244, 247, 252)      # 高光

COOL = (127, 168, 216)        # 冷青(月光/屏幕)
COOL_DEEP = (58, 88, 132)
WARM = (240, 201, 122)        # 暖金(灯)
WARM_DEEP = (168, 122, 62)
WARM_HOT = (255, 231, 176)    # 灯芯过曝

ALERT = (226, 112, 94)        # 警示(电量低/警报)
GOOD = (140, 214, 168)        # 行动卡打勾
SHADOW = (0, 0, 0)

# 灯的亮度档位 -> 光色。剧本里用 "灯 = 情绪" 时直接取这里的值。
LAMP_LEVELS = {
    1.00: WARM_HOT,
    0.75: WARM,
    0.45: WARM_DEEP,
    0.20: COOL_DEEP,
    0.12: (40, 58, 92),
}

FONT_MAIN = r"C:\Windows\Fonts\simhei.ttf"
FONT_BODY = r"C:\Windows\Fonts\simsun.ttc"
FONT_SIZE_SMALL = 11
FONT_SIZE = 12
FONT_SIZE_BIG = 16
FONT_SIZE_TITLE = 22

TITLE = "深夜效应 · 一到凌晨你就想哭，不是矫情，是刹车没了"
FILENAME = "night01_late_night_emo"

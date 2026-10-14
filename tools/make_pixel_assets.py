# -*- coding: utf-8 -*-
"""程序化像素美术生成器 —— 手绘密度版(不是几何拼块)。

设计原则(借用 AI 出图工具的像素画规范, 再用代码精确执行):
  1. **1px 深色描边**包住整个剪影 —— 这是像素画能"立住"的第一要素
  2. **按光源分区投影**: 每个色块给 base / 亮 / 暗 三阶, 亮面朝灯, 暗面背灯
  3. **单点高光**: 头发与灯罩各一个亮点, 负责把视线钉在焦点上
  4. **轮廓留负空间**: 发梢与肩之间留 1px 空隙, 剪影才不糊成一块

产物:
  assets/sprites/atlas.png   图集(1:1 像素, 无缩放)
  assets/sprites/atlas.json  每个 sprite 的矩形与锚点
  docs/process/sprite_sheet.png  放大预览(自检用)

  python tools/make_pixel_assets.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pygame  # noqa: E402

from nightpix import config as C  # noqa: E402

# --------------------------------------------------------------------------
# 调色板: 每个色只有 3 阶(描边 / 暗 / 基 / 亮), 保证像素画色调统一
# --------------------------------------------------------------------------
PAL = {
    ".": None,                          # 透明
    "K": (13, 16, 28),                  # 轮廓深色
    # 头发刻意压暗压冷 —— 与裙子的蓝拉开明度差, 否则剪影糊成一块
    "H": (38, 48, 80),                  # 头发 基
    "h": (66, 84, 128),                 # 头发 亮(受灯)
    "h2": (140, 170, 220),              # 头发 高光点
    "S": (176, 152, 136),               # 皮肤 基
    "s": (208, 186, 168),               # 皮肤 亮
    "C": (96, 118, 168),                # 上衣 基
    "c": (140, 168, 216),               # 上衣 亮
    "D": (118, 146, 202),               # 裙子 基(比头发亮一档)
    "d": (166, 194, 238),               # 裙子 亮
    "d2": (78, 100, 150),               # 裙子 暗
    "L": (240, 201, 122),               # 灯 暖金
    "l": (255, 231, 176),               # 灯 过曝
    "l2": (168, 122, 62),               # 灯 暗
    "M": (58, 74, 112),                 # 手机 机身
    "m": (196, 222, 250),               # 手机 屏幕亮
    "B": (46, 58, 92),                  # 家具 暗
    "b": (72, 90, 136),                 # 家具 亮
    "W": (222, 232, 246),               # 白(表盘)
    "R": (226, 112, 94),                # 警示红
    "G": (140, 214, 168),               # 通过绿
    "Y": (240, 208, 150),               # 暖黄(月光/街灯)
}


def surface_from_rows(rows, scale=1):
    """rows: 字符串列表, 每行等长。返回裁剪到实际内容边界的 Surface。"""
    w = max(len(r) for r in rows)
    h = len(rows)
    s = pygame.Surface((w * scale, h * scale), pygame.SRCALPHA)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            col = PAL.get(ch, None)
            if col is None:
                continue
            if scale == 1:
                s.set_at((x, y), col)
            else:
                pygame.draw.rect(s, col, (x * scale, y * scale, scale, scale))
    return s


# ==========================================================================
# 人物: 提灯的人(背影) —— 16x30
#   读法: 顶部发髻/头 -> 肩 -> 腰 -> 阶梯裙摆 -> 小腿
# ==========================================================================
CHAR = [
    "................",
    "......KKKK......",
    ".....KHHHHK.....",
    "....KHHhhHHK....",
    "....KHh2hHHK....",
    "....KHHHHHHK....",
    "....KHHHHHHK....",
    "....KKHHHHKK....",
    ".....KHHHHK.....",
    ".....KHHHHK.....",
    "......KCCK......",
    "....KKCCCCKK....",
    "...KCCCCCCCCK...",
    "...KCcCCCCcCK...",
    "...KCCCCCCCCK...",
    "...KCCCCCCCCK...",
    "...KCCCCCCCCK...",
    "...KCDDDDDDCK...",
    "..KDDDddddDDDK..",
    "..KDDDddddDDDK..",
    "..KDDDddddDDDK..",
    "..KDDDddddDDDKK.",
    ".KDDDDddddDDDKCK",
    ".KDDDDddddDDDKCK",
    "KDDDDDddddDDDDKC",
    "KDDDDDddddDDDDKK",
    "KDDDDDddddDDDDDK",
    "KDDDDDDddDDDDDDK",
    "KKKKKKKKKKKKKKKK",
    "................",
]

# Q 版路线(头大身短), 用于对比取型
CHAR_CHIBI = [
    "................",
    ".....KKKKKK.....",
    "....KHHHHHHK....",
    "...KHHhhhhHHK...",
    "...KHh2hhHHHK...",
    "...KHHHHHHHHK...",
    "...KHHHHHHHHK...",
    "...KHHHHHHHHK...",
    "...KKHHHHHHKK...",
    "....KHHHHHHK....",
    "....KKCCCCKK....",
    "...KCCcCCcCCK...",
    "...KCCCCCCCCK...",
    "...KCCCCCCCCK...",
    "...KCDDDDDDCK...",
    "..KDDDddddDDDKK.",
    "..KDDDddddDDDKCK",
    ".KDDDDddddDDDDKC",
    ".KDDDDddddDDDDKC",
    "KDDDDDddddDDDDKC",
    "KDDDDDddddDDDDKK",
    "KDDDDDddddDDDDDK",
    "KKKKKKKKKKKKKKKK",
    "................",
]

# 提灯(独立 sprite, 便于按情绪改亮度/位置)
LANTERN = [
    "..KKKK..",
    ".KlllLK.",
    "KlllllLK",
    "KlLLLlLK",
    "KlLLLlLK",
    "KlllllLK",
    ".KlllLK.",
    "..KKKK..",
]

# ==========================================================================
# 道具
# ==========================================================================
PHONE = [
    "KKKKKKKK",
    "KMMMMMMK",
    "KMmmmmMK",
    "KMmKKmMK",
    "KMmmmmMK",
    "KMmKKmMK",
    "KMmmmmMK",
    "KMmmmmMK",
    "KMmKKmMK",
    "KMmmmmMK",
    "KMMMMMMK",
    "KKKKKKKK",
]

CLOCK = [
    "...KKKK...",
    "..KWWWWK..",
    ".KWKWWKWK.",
    ".KWWKWKWK.",
    "KWKWKWWWWK",
    "KWKKKWKWWK",
    "KWWWWWWWWK",
    "KWKWWWWKWK",
    ".KWWWWWWK.",
    "..KWWWWK..",
    "...KKKK...",
]

BED = [
    "KKKKKKKKKKKKKKKKKKKKKK",
    "KBBBBBBBBBBBBBBBBBBBBK",
    "KbbbbbbbbbbbbbbbbbbbbK",
    "KBBBBBBBBBBBBBBBBBBBBK",
    "KwWWWWwwBBBBBBBBBBBBBK",
    "KWWWWWWwBBBBBBBBBBBBBK",
    "KBBBBBBBBBBBBBBBBBBBBK",
    "KKKKKKKKKKKKKKKKKKKKKK",
]

LAMP = [
    "..KKKK..",
    ".KbbbbK.",
    "KbLLLLbK",
    "KbLllLbK",
    "KbLLLLbK",
    ".KbbbbK.",
    "..KKKK..",
    "...bb...",
]

BRAIN = [
    "....KKKKKK....",
    "..KKbbbbbbKK..",
    ".KbbbbbbbbbbK.",
    "KbbbbbbbbbbbbK",
    "KbbbRRRbbbbbbK",
    "KbbRRRRRbbbbbK",
    "KbbbRRRbbbbbbK",
    "KbbbbbbbbbbbbK",
    ".KbbbbbbbbbbK.",
    "..KKbbbbbbKK..",
    "....KKKKKK....",
]


def build():
    out_dir = os.path.join(C.ASSETS, "sprites")
    os.makedirs(out_dir, exist_ok=True)
    atlas_path = os.path.join(out_dir, "atlas.png")
    json_path = os.path.join(out_dir, "atlas.json")

    items = [
        ("keeper", CHAR, "bottom"),
        ("keeper_chibi", CHAR_CHIBI, "bottom"),
        ("lantern", LANTERN, "center"),
        ("phone", PHONE, "center"),
        ("clock", CLOCK, "center"),
        ("bed", BED, "bottom"),
        ("lamp", LAMP, "bottom"),
        ("brain", BRAIN, "center"),
    ]
    surfaces = [(name, surface_from_rows(rows), anchor) for name, rows, anchor in items]

    # 图集: 横排, 留 2px 间隔
    pad = 2
    W = sum(s.get_width() for _, s, _ in surfaces) + pad * (len(surfaces) + 1)
    H = max(s.get_height() for _, s, _ in surfaces) + pad * 2
    atlas = pygame.Surface((W, H), pygame.SRCALPHA)
    manifest = {"atlas": "atlas.png", "sprites": {}}
    x = pad
    for name, s, anchor in surfaces:
        atlas.blit(s, (x, pad))
        manifest["sprites"][name] = {
            "x": x, "y": pad, "w": s.get_width(), "h": s.get_height(), "anchor": anchor,
        }
        x += s.get_width() + pad

    pygame.image.save(atlas, atlas_path)
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    print("图集:", atlas_path, atlas.get_size())
    print("清单:", json_path, "->", list(manifest["sprites"]))

    # 放大预览(自检): 图集横排 + 右侧"实际用法"合成图(人物+灯)
    k = 8
    sheet_w = W * k
    comp_w = 34 * k
    big = pygame.Surface((sheet_w + comp_w, H * k))
    big.fill((18, 22, 34))
    for yy in range(0, H, 4):                       # 4px 网格, 便于数格子
        pygame.draw.line(big, (28, 33, 48), (0, yy * k), (sheet_w, yy * k))
    for xx in range(0, W, 4):
        pygame.draw.line(big, (28, 33, 48), (xx * k, 0), (xx * k, H * k))
    big.blit(pygame.transform.scale(atlas, (sheet_w, H * k)), (0, 0))

    # 合成预览: 人物 + 身侧提灯(这是成片里的真实用法, 单看 sprite 会低估效果)
    comp = pygame.Surface((34, 34), pygame.SRCALPHA)
    keep = surface_from_rows(CHAR)
    lant = surface_from_rows(LANTERN)
    comp.blit(keep, (6, 4))
    comp.blit(lant, (20, 16))
    # 灯旁边的暖光(用同心圆近似)
    for i in range(9, 0, -1):
        a = int(26 * (1 - i / 9.0) + 6)
        s = pygame.Surface((i * 2, i * 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (240, 201, 122, a), (i, i), i)
        comp.blit(s, (24 - i, 20 - i), special_flags=pygame.BLEND_RGBA_ADD)
    comp_big = pygame.transform.scale(comp, (comp_w, comp_w))
    big.blit(comp_big, (sheet_w, (H * k - comp_w) // 2))

    prev = os.path.join(C.DOCS, "process", "sprite_sheet.png")
    os.makedirs(os.path.dirname(prev), exist_ok=True)
    pygame.image.save(big, prev)
    print("放大预览:", prev, big.get_size())
    return 0


if __name__ == "__main__":
    pygame.init()
    pygame.display.set_mode((1, 1))
    sys.exit(build())

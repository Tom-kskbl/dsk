# -*- coding: utf-8 -*-
"""把文生图结果转成工程可用的像素精灵。

文生图有三个工程上过不去的坎: 背景不透明、尺寸太大、帧间不一致。
但前两个可以在代码里解决:
  1. 从四角泛洪抠掉背景 -> alpha
  2. 高质量重采样到像素尺寸(如高 26px) -> 回到像素网格
  3. 量化到工程调色板 -> 色调统一, 且能复用现有的压暗/光晕链路

产物: assets/sprites/down_<name>.png, 并在预览图里和手绘版并排对比。

  python tools/image_to_sprite.py --src assets/reference/keeper.png --box 0,0,0.5,1 --name keeper_ai
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

PALETTE = [
    (13, 16, 28), (38, 48, 80), (66, 84, 128), (140, 170, 220),
    (176, 152, 136), (208, 186, 168),
    (96, 118, 168), (140, 168, 216),
    (118, 146, 202), (166, 194, 238), (78, 100, 150),
    (240, 201, 122), (255, 231, 176), (168, 122, 62),
    (58, 74, 112), (196, 222, 250),
    (46, 58, 92), (72, 90, 136),
    (222, 232, 246), (226, 112, 94), (140, 214, 168), (240, 208, 150),
]


def key_out(img: Image.Image, tol: int = 42) -> Image.Image:
    """从四角泛洪抠背景 -> 带 alpha 的图。"""
    img = img.convert("RGBA")
    a = np.array(img)
    h, w = a.shape[:2]
    # 背景色取四角中位数
    corners = np.array([a[0, 0, :3], a[0, w - 1, :3], a[h - 1, 0, :3], a[h - 1, w - 1, :3]],
                       dtype=np.float32)
    bg = np.median(corners, axis=0)
    dist = np.sqrt(((a[:, :, :3].astype(np.float32) - bg[None, None, :]) ** 2).sum(axis=2))
    mask = dist > tol
    # 只保留最大的连通块(去掉零散噪点)
    mask = _largest_blob(mask)
    out = a.copy()
    out[:, :, 3] = np.where(mask, 255, 0).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def _largest_blob(mask: np.ndarray) -> np.ndarray:
    """不引入 scipy 的连通块: 用迭代膨胀近似, 保留与主体相连的部分。"""
    from scipy import ndimage  # scipy 已在依赖里
    lab, n = ndimage.label(mask)
    if n <= 1:
        return mask
    sizes = ndimage.sum(mask, lab, range(1, n + 1))
    keep = int(np.argmax(sizes)) + 1
    # 主体 + 任何面积超过主体 8% 的块(人物可能被灯绳断开)
    out = np.zeros_like(mask)
    for i, s in enumerate(sizes, start=1):
        if s >= max(sizes) * 0.08:
            out |= (lab == i)
    return out


def quantize(img: Image.Image, denoise: bool = True) -> Image.Image:
    """量化到工程调色板, 保留 alpha。

    denoise: 先做一次 3x3 中值滤波。下采样后常出现孤立杂点(颜色跳变),
    中值能去掉它们而不糊掉边缘 —— 这是"像像素画"和"像马赛克"的分界线。
    """
    if denoise:
        img = img.filter(ImageFilter.MedianFilter(3))
    arr = np.array(img).astype(np.float32)
    rgb, alpha = arr[:, :, :3], arr[:, :, 3]
    pal = np.array(PALETTE, dtype=np.float32)
    d = ((rgb[:, :, None, :] - pal[None, None, :, :]) ** 2).sum(axis=3)
    idx = d.argmin(axis=2)
    out = np.zeros_like(arr)
    out[:, :, :3] = pal[idx]
    out[:, :, 3] = alpha
    return Image.fromarray(out.astype(np.uint8), "RGBA")


def upscale(name: str, k: int = 5) -> str:
    """把像素精灵按整数倍最近邻放大 —— 成片在 640x360 画布上要用大尺寸。"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(root, "assets", "sprites", f"down_{name}.png")
    im = Image.open(src).convert("RGBA")
    big = im.resize((im.width * k, im.height * k), Image.NEAREST)
    dst = os.path.join(root, "assets", "sprites", f"big_{name}.png")
    big.save(dst)
    print(f"  {name}: {im.size} -> {big.size}  {dst}")
    return dst


def to_sprite(src: str, box, height: int, name: str, tol: int = 42,
              sharpen: bool = True) -> str:
    im = Image.open(src).convert("RGBA")
    w, h = im.size
    x0, y0, x1, y1 = box
    crop = im.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))
    keyed = key_out(crop, tol)
    bb = keyed.getbbox()
    if bb:
        keyed = keyed.crop(bb)
    # 重采样到像素高度
    k = height / keyed.height
    small = keyed.resize((max(1, int(round(keyed.width * k))), height), Image.LANCZOS)
    # 阈值化 alpha, 避免半透明毛边(像素画必须硬边)
    a = np.array(small)
    a[:, :, 3] = np.where(a[:, :, 3] > 110, 255, 0).astype(np.uint8)
    small = Image.fromarray(a, "RGBA")
    if sharpen:
        small = quantize(small)
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "assets", "sprites")
    os.makedirs(out_dir, exist_ok=True)
    dst = os.path.join(out_dir, f"down_{name}.png")
    small.save(dst)
    print(f"  {name}: {crop.size} -> 抠背景 -> {small.size}  -> {dst}")
    return dst


def preview(pairs, out_path, k=8):
    """并排对比: (标签, 图路径) 列表。"""
    imgs = [(lab, Image.open(p).convert("RGBA")) for lab, p in pairs]
    cw = max(im.width for _, im in imgs) * k + 16
    ch = max(im.height for _, im in imgs) * k + 24
    sheet = Image.new("RGB", (cw * len(imgs), ch), (18, 22, 34))
    d = ImageDraw.Draw(sheet)
    for i, (lab, im) in enumerate(imgs):
        big = im.resize((im.width * k, im.height * k), Image.NEAREST)
        ox = i * cw + (cw - big.width) // 2
        oy = 20
        sheet.paste(big, (ox, oy), big)
        d.text((i * cw + 8, 6), lab, fill=(200, 210, 230))
    sheet.save(out_path)
    print("对比图:", out_path, sheet.size)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join("assets", "reference", "keeper.png"))
    ap.add_argument("--box", default="0.06,0.03,0.45,0.50", help="归一化裁剪框 x0,y0,x1,y1")
    ap.add_argument("--name", default="keeper_ai")
    ap.add_argument("--height", type=int, default=26)
    ap.add_argument("--tol", type=int, default=42)
    a = ap.parse_args()
    box = tuple(float(v) for v in a.box.split(","))
    to_sprite(a.src, box, a.height, a.name, a.tol)

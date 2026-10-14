# -*- coding: utf-8 -*-
"""用文生图模型生成**场景背景**(不是精灵), 再转成工程可用的 640x360 背景板。

为什么走背景而不是精灵:
  * 精灵必须像素级精确 + alpha + 帧间一致, 文生图三条都做不到, 强行转出来会丢关键信息
  * 背景只要"氛围对"就够, 而且文生图在构图/配色上远强于几何绘制
  * 背景压暗后当底, 字幕与光效叠在上面 —— 正好补上"画面太暗太空"的问题

  python tools/gen_backdrops.py            # 生成全部
  python tools/gen_backdrops.py --only bed
"""
import argparse
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np  # noqa: E402
from PIL import Image, ImageEnhance, ImageFilter  # noqa: E402

from nightpix import config as C  # noqa: E402

MODEL = "wan2.2-t2i-flash"
PATH_SUBMIT = "/services/aigc/text2image/image-synthesis"
PATH_QUERY = "/tasks/"

STYLE = ("pixel art, 16-bit retro game background, limited dark palette, "
         "dithering, crisp pixels, pixel art scene, no characters, no text, ")
NEG = ("photo, 3d render, blurry, smooth gradient, text, watermark, characters, "
       "people, faces, UI, logo")

BACKDROPS = {
    # 场景键 -> 提示词
    "ceiling_3am": (
        "view from a bed looking up at a dark bedroom ceiling at 3am, "
        "faint moonlight through a curtain on the right, a dim ceiling lamp, "
        "deep indigo and charcoal blue, very low light, empty and quiet, " + STYLE),
    "two_yous": (
        "a dark bedroom room interior at night, one window with rain, "
        "a desk and a bed, cold blue moonlight, empty room, "
        "deep indigo and charcoal blue, very low light, " + STYLE),
    "brake_gauge": (
        "an abstract dark blue room with a subtle glowing horizontal grid floor, "
        "empty, cinematic depth, cold cyan glow from below, " + STYLE),
    "emotion_curve": (
        "an empty dark blue room corner with a large window, night city glow, "
        "abstract, minimal, cold blue with faint warm accents, " + STYLE),
    "rumination_loop": (
        "an empty dark blue void room with a faint circular ring of light "
        "floating in the middle, abstract, minimal, lonely, " + STYLE),
    "feed_glow": (
        "a dark bedroom at night, a glowing phone screen off to the left casting "
        "cold blue light across an empty room, deep shadows, no people, " + STYLE),
    "sleep_tug": (
        "a dark bedroom at night with a bed with white pillow, cold blue moonlight "
        "from a window, empty bed, very low light, no people, " + STYLE),
    "dawn": (
        "a room at dawn seen through a window, warm orange sunrise light, "
        "dark blue interior turning warm, empty, hopeful mood, " + STYLE),
}


def _submit(prompt, key, base, size):
    body = {"model": MODEL, "input": {"prompt": prompt, "negative_prompt": NEG},
            "parameters": {"size": size, "n": 1, "prompt_extend": False}}
    req = urllib.request.Request(base + PATH_SUBMIT, data=json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + key,
                                          "Content-Type": "application/json",
                                          "X-DashScope-Async": "enable"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def _wait(task, key, base, timeout_s=300):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        time.sleep(5)
        req = urllib.request.Request(base + PATH_QUERY + task,
                                     headers={"Authorization": "Bearer " + key})
        with urllib.request.urlopen(req, timeout=40) as resp:
            q = json.loads(resp.read().decode())
        st = (q.get("output") or {}).get("task_status")
        if st == "SUCCEEDED":
            return ((q["output"].get("results") or [{}])[0].get("url"))
        if st in ("FAILED", "CANCELED"):
            raise RuntimeError(f"{st}: {json.dumps(q, ensure_ascii=False)[:200]}")
    raise RuntimeError("超时")


def to_backdrop(src_png: str, name: str, darken=0.42, desat=0.55, blur=0.6):
    """1024x1024 -> 640x360 背景板: 压暗 + 降饱和 + 微模糊, 给字幕让出对比度。"""
    im = Image.open(src_png).convert("RGB")
    w, h = im.size
    # 居中裁成 16:9
    th = int(w * 9 / 16)
    if th <= h:
        top = (h - th) // 2
        im = im.crop((0, top, w, top + th))
    else:
        tw = int(h * 16 / 9)
        left = (w - tw) // 2
        im = im.crop((left, 0, left + tw, h))
    im = im.resize((C.VW, C.VH), Image.LANCZOS)
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur))
    im = ImageEnhance.Color(im).enhance(desat)
    im = ImageEnhance.Brightness(im).enhance(darken)
    # 顶部再压一道暗, 避免和 HUD/进度线打架
    a = np.array(im).astype(np.float32)
    ramp = np.linspace(0.72, 1.0, C.VH)[:, None, None]
    a *= ramp
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    out_dir = os.path.join(C.ASSETS, "backdrops")
    os.makedirs(out_dir, exist_ok=True)
    dst = os.path.join(out_dir, name + ".png")
    im.save(dst)
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    ap.add_argument("--size", default="1024*1024")
    ap.add_argument("--darken", type=float, default=0.42)
    ap.add_argument("--import-local", nargs=2, action="append", metavar=("SRC", "NAME"),
                    help="把本地图片(如 Canva 导出的)按同一套参数转成背景板, 可重复")
    a = ap.parse_args()

    # 先把本地图转成背景板(不需要联网, 也不需要 key)
    if a.import_local:
        for src, name in a.import_local:
            dst = to_backdrop(src, name, darken=a.darken)
            print(f"  [本地 {name}] -> {dst}")
        if not a.only:
            return 0

    cfg = json.load(open(os.path.join(C.CACHE, "aliyun.json"), encoding="utf-8"))
    key, base = cfg["api_key"], cfg["base_url"].rstrip("/")

    raw_dir = os.path.join(C.ASSETS, "reference", "backdrops_raw")
    os.makedirs(raw_dir, exist_ok=True)
    names = [a.only] if a.only else list(BACKDROPS)
    for n in names:
        try:
            raw = os.path.join(raw_dir, n + ".png")
            if not os.path.exists(raw):
                r = _submit(BACKDROPS[n], key, base, a.size)
                task = (r.get("output") or {}).get("task_id")
                if not task:
                    raise RuntimeError(json.dumps(r, ensure_ascii=False)[:200])
                print(f"  [{n}] task {task} 提交", flush=True)
                url = _wait(task, key, base)
                with urllib.request.urlopen(url, timeout=120) as img:
                    open(raw, "wb").write(img.read())
                print(f"  [{n}] 原图 {os.path.getsize(raw)//1024} KB")
            dst = to_backdrop(raw, n, darken=a.darken)
            print(f"  [{n}] 背景板 -> {dst}")
        except Exception as e:
            print(f"  [{n}] 失败 {type(e).__name__}: {str(e)[:180]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

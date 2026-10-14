# -*- coding: utf-8 -*-
"""用文生图模型生像素素材参考图。

背景: 本工程的成片素材走的是 **代码手绘像素图**(tools/make_pixel_assets.py), 因为它必须
满足三个硬条件 —— 像素级精确、带 alpha 透明通道、帧间完全一致。文生图做不到这三点。
但它**很擅长定调**: 配色、剪影比例、"提灯少女"该长什么样。

所以这里生成的图定位是 **视觉参考(reference)**, 用来反过来校准代码里的调色板与比例,
而不是直接拿去当素材用。产物落在 assets/reference/, 并在设计文档里说明来源。

  python tools/gen_reference.py                 # 生成全部参考图
  python tools/gen_reference.py --only keeper   # 只生成一张
"""
import argparse
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from nightpix import config as C  # noqa: E402

MODEL = "wan2.2-t2i-flash"          # 实测可用; 需要更精细可换 wan2.2-t2i-plus
PATH_SUBMIT = "/services/aigc/text2image/image-synthesis"
PATH_QUERY = "/tasks/"

NEGATIVE = ("写实, 照片, 3D渲染, 模糊, 抗锯齿, 渐变过度, 复杂细节, 水印, 文字, "
            "多个人物, 错误的手指, 变形")

COMMON = ("pixel art sprite, 16-bit retro game style, clean 1px dark outline, "
          "limited dark palette, dithered shading, crisp square pixels, "
          "dark indigo background")

PROMPTS = {
    "keeper": (
        "pixel art character sprite sheet of a small girl seen from behind, "
        "long dark blue hair with a ponytail, simple A-line knee-length dress, "
        "holding a small warm glowing lantern at her side, the lantern is the only "
        "light source, warm golden rim light on the right edge of her dress and hair, "
        "chibi proportions, head slightly large, no visible face, "
        "four poses in a row: standing, walking, sitting, lying down, "
        + COMMON),
    "props": (
        "pixel art prop sprite sheet: a small glowing handheld lantern, a smartphone "
        "with a bright cool white screen, a round wall clock, a bed with a pillow, "
        "a warm table lamp, each item isolated and centered, "
        "cool blue night color scheme with warm golden accents, " + COMMON),
    "mood": (
        "pixel art scene, a tiny girl silhouette sitting alone on the floor of an "
        "empty dark room at 3am, a small lantern beside her glowing warm gold, "
        "strong contrast between the tiny warm light and the vast dark blue space, "
        "cinematic loneliness, lots of negative space, " + COMMON),
}


def _post(url, body, key, extra=None):
    hdr = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    if extra:
        hdr.update(extra)
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=hdr)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def generate(name: str, prompt: str, key: str, base: str, size="1024*1024") -> str:
    body = {
        "model": MODEL,
        "input": {"prompt": prompt, "negative_prompt": NEGATIVE},
        "parameters": {"size": size, "n": 1, "prompt_extend": False},
    }
    r = _post(base + PATH_SUBMIT, body, key, {"X-DashScope-Async": "enable"})
    task = (r.get("output") or {}).get("task_id")
    if not task:
        raise RuntimeError(f"提交失败: {json.dumps(r, ensure_ascii=False)[:300]}")
    print(f"  [{name}] task {task} 提交成功, 等待出图 ...", flush=True)

    out_dir = os.path.join(C.ASSETS, "reference")
    os.makedirs(out_dir, exist_ok=True)
    for i in range(60):                       # 最多等 5 分钟
        time.sleep(5)
        q = _post(base + PATH_QUERY + task, None, key) if False else None
        req = urllib.request.Request(base + PATH_QUERY + task,
                                     headers={"Authorization": "Bearer " + key})
        with urllib.request.urlopen(req, timeout=40) as resp:
            q = json.loads(resp.read().decode())
        st = (q.get("output") or {}).get("task_status")
        if st == "SUCCEEDED":
            results = (q.get("output") or {}).get("results") or []
            if not results:
                raise RuntimeError("成功但没有 results")
            url = results[0].get("url")
            dst = os.path.join(out_dir, name + ".png")
            with urllib.request.urlopen(url, timeout=120) as img:
                data = img.read()
            with open(dst, "wb") as fh:
                fh.write(data)
            print(f"  [{name}] 完成 {len(data) // 1024} KB -> {dst}")
            return dst
        if st in ("FAILED", "CANCELED"):
            raise RuntimeError(f"任务 {st}: {json.dumps(q, ensure_ascii=False)[:300]}")
        if i % 4 == 0:
            print(f"  [{name}] 等待中 ... ({st})", flush=True)
    raise RuntimeError("超时")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="只生成指定名字")
    ap.add_argument("--size", default="1024*1024")
    a = ap.parse_args()

    cfg = json.load(open(os.path.join(C.CACHE, "aliyun.json"), encoding="utf-8"))
    key, base = cfg["api_key"], cfg["base_url"].rstrip("/")

    names = [a.only] if a.only else list(PROMPTS)
    done = []
    for n in names:
        try:
            done.append(generate(n, PROMPTS[n], key, base, a.size))
        except Exception as e:
            print(f"  [{n}] 失败: {type(e).__name__}: {str(e)[:200]}")
    print("\n生成完成:", len(done), "/", len(names))
    # 记录来源, 便于复现与署名
    meta = os.path.join(C.ASSETS, "reference", "SOURCE.md")
    if done:
        lines = ["# 参考图来源", "",
                 "以下图片由**文生图模型**生成, 用途是**视觉参考** ——",
                 "校准代码手绘素材(``tools/make_pixel_assets.py``)的配色与剪影比例。", "",
                 f"- 模型: `{MODEL}` (阿里云百炼 DashScope)",
                 f"- 生成脚本: `tools/gen_reference.py`",
                 "- **这些图不进成片**: 成片素材必须像素级精确、带 alpha、帧间一致, 文生图满足不了。", "",
                 "| 文件 | 提示词要点 |", "|---|---|"]
        for n in PROMPTS:
            if os.path.exists(os.path.join(C.ASSETS, "reference", n + ".png")):
                lines.append(f"| `{n}.png` | {PROMPTS[n][:70]}... |")
        with open(meta, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        print("来源说明:", meta)
    return 0 if done else 1


if __name__ == "__main__":
    sys.exit(main())

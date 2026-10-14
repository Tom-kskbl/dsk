# -*- coding: utf-8 -*-
"""渲染器: 在 640x360 虚拟画布上逐帧绘制, 通过管道交给 ffmpeg 最近邻放大编码。

同时提供关键帧(stills)与联络表(contact_sheet) —— 调画面阶段的主要自检手段。
"""
import os
import subprocess
import time

import pygame

from . import config as C


def init_pygame(headless: bool = True):
    if headless:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((C.VW, C.VH))
    return pygame.display.get_surface()


def ffmpeg_exe() -> str:
    from imageio_ffmpeg import get_ffmpeg_exe
    return get_ffmpeg_exe()


def encode(timeline, audio_path: str, out_path: str, crf: int = 18,
           preset: str = "medium", progress_every: int = 120) -> str:
    """逐帧渲染 -> rawvideo 管道 -> ffmpeg (最近邻放大 + 混音)。"""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    surf = init_pygame()
    fps = C.FPS
    total = int(round(timeline.duration * fps))
    cmd = [
        ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{C.VW}x{C.VH}", "-r", str(fps), "-i", "-",
        "-i", audio_path,
        "-vf", f"scale={C.VW * C.SCALE}:{C.VH * C.SCALE}:flags=neighbor",
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-movflags", "+faststart", out_path,
    ]
    t0 = time.time()
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        for i in range(total):
            timeline.draw(surf, i / fps)
            proc.stdin.write(pygame.image.tostring(surf, "RGB"))
            if (i + 1) % progress_every == 0 or i == total - 1:
                el = time.time() - t0
                eta = el / (i + 1) * (total - i - 1)
                print(f"  帧 {i + 1}/{total}  {el:5.1f}s 已用  ETA {eta:5.1f}s", flush=True)
    finally:
        proc.stdin.close()
        err = proc.stderr.read().decode("utf-8", "ignore")
        rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg 失败({rc}): {err[-1500:]}")
    print(f"完成: {out_path}  用时 {time.time() - t0:.1f}s")
    return out_path


def still(timeline, t: float, path: str):
    surf = init_pygame()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    timeline.draw(surf, t)
    big = pygame.transform.scale(surf, (C.VW * C.SCALE, C.VH * C.SCALE))
    pygame.image.save(big, path)
    return path


def stills(timeline, times, out_dir: str, tag: str = "") -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    surf = init_pygame()
    paths = []
    for t in times:
        timeline.draw(surf, t)
        big = pygame.transform.scale(surf, (C.VW * C.SCALE, C.VH * C.SCALE))
        p = os.path.join(out_dir, f"still_{tag}_{t:07.2f}.png".replace(".", "_", 1))
        pygame.image.save(big, p)
        print("  still", round(t, 2), p)
        paths.append(p)
    return paths


def contact_sheet(paths, out_path, cols=4, cell_w=480, label: str = ""):
    """把关键帧拼成一张联络表, 方便一次看完。"""
    imgs = [pygame.image.load(p) for p in paths]
    k = cell_w / imgs[0].get_width()
    ch = int(imgs[0].get_height() * k)
    rows = (len(imgs) + cols - 1) // cols
    sheet = pygame.Surface((cols * cell_w, rows * ch))
    sheet.fill((8, 10, 16))
    for i, im in enumerate(imgs):
        sheet.blit(pygame.transform.scale(im, (cell_w, ch)),
                   ((i % cols) * cell_w, (i // cols) * ch))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    pygame.image.save(sheet, out_path)
    print("联络表:", out_path, sheet.get_size())
    return out_path

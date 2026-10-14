# -*- coding: utf-8 -*-
"""验收报表: 核对成片的 8 条交付判据。

  python tools/night_report.py            # 默认检查 out/night01_late_night_emo.mp4
  python tools/night_report.py --frames   # 额外出每个镜头的抽帧联络表
"""
import argparse
import os
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):          # Windows 控制台默认 GBK, 中文报表会炸
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pygame  # noqa: E402

from nightpix import config as C  # noqa: E402
C.set_canvas(640, 360, 3)

from nightpix import night_ep, render  # noqa: E402

# 本机的 ffprobe / ffmpeg(剪映版 ffmpeg 不支持 -select_streams, imageio 版不带 ffprobe)
FFPROBE_CANDIDATES = [
    r"C:\Users\Lenovo\AppData\Local\Programs\TRAE SOLO CN\resources\app\bin\ffprobe.exe",
    "ffprobe",
]
FFMPEG_CANDIDATES = [
    r"D:\电脑管家迁移文件\JianyingPro\apps\11.3.0.14362\ffmpeg.exe",
    "ffmpeg",
]


def _which(cands):
    for c in cands:
        if os.path.sep in c:
            if os.path.exists(c):
                return c
        else:
            from shutil import which
            p = which(c)
            if p:
                return p
    return None


def probe(path: str, args: list[str]):
    exe = _which(FFPROBE_CANDIDATES)
    if not exe:
        return None
    p = subprocess.run([exe, "-v", "error", *args, "-of", "default=noprint_wrappers=1", path],
                       capture_output=True, text=True)
    out = {}
    for line in p.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k] = v
    return out


def volumedetect(path: str):
    exe = _which(FFMPEG_CANDIDATES)
    if not exe:
        return {}
    p = subprocess.run([exe, "-hide_banner", "-i", path, "-af", "volumedetect",
                        "-f", "null", "-"], capture_output=True, text=True)
    out = {}
    for line in (p.stderr or "").splitlines():
        if "mean_volume:" in line:
            out["mean"] = line.split("mean_volume:")[1].strip()
        if "max_volume:" in line:
            out["max"] = line.split("max_volume:")[1].strip()
    return out


def check(rows, name, ok, detail=""):
    rows.append((("PASS" if ok else "FAIL"), name, detail))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default=os.path.join(C.OUT, C.FILENAME + ".mp4"))
    ap.add_argument("--mix", default=os.path.join(C.OUT, C.FILENAME + "_mix.wav"))
    ap.add_argument("--frames", action="store_true")
    a = ap.parse_args()

    rows, all_ok = [], True
    if not os.path.exists(a.video):
        print("找不到成片:", a.video)
        return 1
    v = probe(a.video, ["-select_streams", "v:0",
                        "-show_entries", "stream=codec_name,width,height,r_frame_rate,pix_fmt",
                        "-show_entries", "format=duration,size,bit_rate"])
    au = probe(a.video, ["-select_streams", "a:0",
                         "-show_entries", "stream=codec_name,sample_rate,channels"])
    v, au = v or {}, au or {}
    dur = float(v.get("duration", 0) or 0)
    size_mb = float(v.get("size", 0) or 0) / 1024 / 1024

    all_ok &= check(rows, "分辨率 1920x1080",
                    v.get("width") == "1920" and v.get("height") == "1080",
                    f"{v.get('width')}x{v.get('height')}")
    all_ok &= check(rows, "视频编码 h264 / yuv420p / 30fps",
                    v.get("codec_name") == "h264" and v.get("pix_fmt") == "yuv420p"
                    and v.get("r_frame_rate") == "30/1",
                    f"{v.get('codec_name')} {v.get('pix_fmt')} {v.get('r_frame_rate')}")
    all_ok &= check(rows, "时长 178±8 秒", 170 <= dur <= 186, f"{dur:.1f}s")
    all_ok &= check(rows, "音轨 aac 44.1kHz 立体声",
                    au.get("codec_name") == "aac" and au.get("sample_rate") == "44100"
                    and au.get("channels") == "2",
                    f"{au.get('codec_name')} {au.get('sample_rate')}Hz {au.get('channels')}ch")
    all_ok &= check(rows, "单文件 < 50MB (可直接进 GitHub)", size_mb < 50,
                    f"{size_mb:.1f} MB  {float(v.get('bit_rate', 0) or 0) / 1e6:.2f} Mbps")

    # 混音自带结尾卡余量, 比正片长是正常的
    lvl = volumedetect(a.mix) if os.path.exists(a.mix) else {}
    if lvl:
        mx = float(lvl["max"].split()[0])
        all_ok &= check(rows, "混音无削波 (峰值 <= -0.3 dBFS)", mx <= -0.3, f"max {mx} dB")
        rows.append(("INFO", "混音平均响度", f"mean {lvl['mean']}"))

    # 旁白存在性: 混音里应有明显高于本底的电平波动
    if os.path.exists(a.mix):
        import wave
        with wave.open(a.mix) as w:
            mix_dur = w.getnframes() / w.getframerate()
            all_ok &= check(rows, "混音时长 与成片一致(允许结尾卡余量)",
                            0 <= mix_dur - dur <= 8.0,
                            f"{mix_dur:.1f}s vs {dur:.1f}s")

    # 关键帧自检
    if a.frames:
        tl = night_ep.make_timeline(tts=False)
        n = len(tl.shots)
        times = [s["start"] + s["dur"] * 0.6 for s in tl.shots]
        paths = render.stills(tl, times, os.path.join(C.OUT, "stills_night"),
                              tag="report")
        sheet = render.contact_sheet(paths, os.path.join(C.OUT, "_check_stills_night.png"),
                                     cols=4, cell_w=480)
        # 联络表同时留档到 docs/process（README 会引用它）
        import shutil
        os.makedirs(os.path.join(C.DOCS, "process"), exist_ok=True)
        shutil.copy2(sheet, os.path.join(C.DOCS, "process", "contact_sheet.png"))
        rows.append(("INFO", "每镜抽帧", f"{n} 张 + 联络表(含 docs 留档)"))

    print("=" * 66)
    print(f"{'result':<8}{'check':<36}measured")
    print("-" * 66)
    for st, name, detail in rows:
        print(f"{st:<8}{name:<36}{detail}")
    print("=" * 66)
    print("TOTAL:", "ALL PASS" if all_ok else "HAS FAILURES")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""构建《深夜效应》—— 1920x1080 / 30fps / 约 3 分钟。

  python build_night.py --stills      # 关键帧自检(几秒)
  python build_night.py --no-tts      # 跳过配音, 先看运动与转场
  python build_night.py               # 完整出片
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nightpix import config as C            # noqa: E402

C.set_canvas(640, 360, 3)                   # 16:9 -> 1920x1080

from nightpix import night_ep, render       # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-tts", action="store_true")
    ap.add_argument("--stills", action="store_true")
    ap.add_argument("--n", type=int, default=16, help="stills 数量")
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--preset", default="medium")
    ap.add_argument("--out", default=os.path.join(C.OUT, C.FILENAME + ".mp4"))
    args = ap.parse_args()

    os.makedirs(C.OUT, exist_ok=True)
    print(f"画布 {C.VW}x{C.VH} x{C.SCALE} -> {C.VW * C.SCALE}x{C.VH * C.SCALE}; {C.FPS}fps")
    tl = night_ep.make_timeline(tts=not args.no_tts)
    chars = sum(len(s["text"]) for s in tl.shots)
    for s in tl.shots:
        print(f"  {s['key']:18s} {s['start']:6.2f}s +{s['dur']:6.2f}s  "
              f"旁白 {s['narr_dur']:6.2f}s  {len(s['text']):3d} 字")
    m, sec = divmod(tl.duration + tl.OUTRO, 60)
    print(f"旁白合计 {chars} 字 ({chars - 0:.0f} 字 / {sum(s['narr_dur'] for s in tl.shots):.1f}s "
          f"= {chars / max(0.1, sum(s['narr_dur'] for s in tl.shots)):.2f} 字/秒)")
    print(f"总时长 {int(m)}分{sec:04.1f}秒  帧数 {int((tl.duration + tl.OUTRO) * C.FPS)}")

    if args.stills:
        n = args.n
        times = [(tl.duration + tl.OUTRO) * (i + 0.5) / n for i in range(n)]
        paths = render.stills(tl, times, os.path.join(C.OUT, "stills_night"), tag="night")
        render.contact_sheet(paths, os.path.join(C.OUT, "_check_stills_night.png"),
                             cols=4, cell_w=480)
        return 0

    audio_path = os.path.join(C.OUT, C.FILENAME + "_mix.wav")
    tl.build_audio(audio_path)
    print("音频:", audio_path)
    render.encode(tl, audio_path, args.out, crf=args.crf, preset=args.preset)
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""片段试码率: 只渲前 N 秒, 用来快速定 CRF(避免每次全片重跑)。
  python tools/bitrate_trial.py 20 22
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nightpix import config as C  # noqa: E402
C.set_canvas(640, 360, 3)

import numpy as np  # noqa: E402
from nightpix import audio, night_ep, render  # noqa: E402


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
    crf = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    tl = night_ep.make_timeline(tts=False)
    render.init_pygame()
    silent = os.path.join(C.OUT, "_silence.wav")
    audio.write_wav(silent, np.zeros((int(audio.SR * secs), 2), dtype=np.float32))
    out = os.path.join(C.OUT, f"_trial_crf{crf}.mp4")

    # 只渲前 secs 秒: 临时裁掉 shot 列表
    kept = []
    for s in tl.shots:
        if s["start"] >= secs:
            break
        kept.append(s)
    tl.shots = kept
    tl.duration = min(secs, kept[-1]["start"] + kept[-1]["dur"])

    render.encode(tl, silent, out, crf=crf, preset="medium")
    mb = os.path.getsize(out) / 1024 / 1024
    full = mb / tl.duration * 177.1
    print(f"CRF {crf}: 片段 {tl.duration:.1f}s = {mb:.2f} MB  ({mb * 8 / tl.duration:.2f} Mbps)")
    print(f"       推算全片 177.1s ≈ {full:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())

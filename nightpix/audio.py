# -*- coding: utf-8 -*-
"""程序化音频: 芯片音乐 BGM + 像素音效 + 中文旁白(SAPI) + 混音。

不依赖任何素材文件, 全部用 numpy 合成, 保证每次渲染结果一致。
"""
import math
import os
import subprocess
import wave

import numpy as np
from scipy.signal import lfilter

from . import config as C

SR = 44100


# --------------------------------------------------------------------------
# 基础波形
# --------------------------------------------------------------------------
def _t(dur):
    return np.arange(int(SR * dur), dtype=np.float32) / SR


def square(freq, dur, duty=0.5):
    ph = (_t(dur) * freq) % 1.0
    return np.where(ph < duty, 1.0, -1.0).astype(np.float32)


def triangle(freq, dur):
    ph = (_t(dur) * freq) % 1.0
    return (4 * np.abs(ph - 0.5) - 1).astype(np.float32)


def noise(dur, rnd):
    return (rnd.random(int(SR * dur)).astype(np.float32) * 2 - 1)


def env(n, a=0.005, d=0.06, s=0.6, r=0.08, sus=None):
    """ADSR 包络(采样数自适应)。"""
    ln = n
    e = np.ones(ln, dtype=np.float32)
    ai, di, ri = int(SR * a), int(SR * d), int(SR * r)
    ai, di, ri = min(ai, ln), min(di, ln), min(ri, ln)
    if ai:
        e[:ai] = np.linspace(0, 1, ai)
    if di:
        e[ai:ai + di] = np.linspace(1, s, di)
    e[ai + di:ln - ri] = s
    if ri:
        e[ln - ri:] = np.linspace(s, 0, ri)
    return e


def note(name):
    """音名 -> 频率, 例如 A4 / C#5。"""
    names = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6,
             "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
    i = 1 if name[1] != "#" else 2
    return 440.0 * 2 ** ((names[name[:i]] + (int(name[i:]) - 4) * 12 - 9) / 12)


# --------------------------------------------------------------------------
# BGM
# --------------------------------------------------------------------------
def chiptune_bgm(dur: float, bpm: float = 104, seed: int = 3) -> np.ndarray:
    """8-bit 循环: 主旋律(方波) + 琶音 + 三角贝斯 + 噪声鼓。"""
    rnd = np.random.default_rng(seed)
    beat = 60.0 / bpm
    step = beat / 2                                   # 八分音符
    total = int(dur / step) + 8
    out = np.zeros(int(SR * (total * step + 1)), dtype=np.float32)

    # Am - F - C - G 进行, 每个和弦 2 小节
    prog = [("A3", ["A3", "C4", "E4"]), ("F3", ["F3", "A3", "C4"]),
            ("C3", ["C4", "E4", "G4"]), ("G3", ["G3", "B3", "D4"])]
    scale = ["A4", "C5", "D5", "E5", "G5", "E5", "D5", "C5"]
    chord_len = 16                                    # 八分音符数
    for s in range(total):
        bar_i = (s // chord_len) % len(prog)
        root, chord = prog[bar_i]
        t0 = s * step
        # 主旋律
        if s % 2 == 0:
            n = scale[(s // 2) % len(scale)] if (s // 4) % 4 != 3 else scale[(s // 2 + 2) % len(scale)]
            f = note(n)
            v = square(f, step * 1.35, duty=0.25 if s % 4 == 0 else 0.5)
            v *= env(len(v), a=0.004, d=0.05, s=0.45, r=0.10) * 0.22
            i0 = int(t0 * SR)
            out[i0:i0 + len(v)] += v[:len(out) - i0]
        # 琶音
        f = note(chord[s % 3]) * 2
        v = square(f, step * 0.9, duty=0.125)
        v *= env(len(v), a=0.002, d=0.03, s=0.2, r=0.05) * 0.075
        i0 = int(t0 * SR)
        out[i0:i0 + len(v)] += v[:len(out) - i0]
        # 贝斯
        if s % 2 == 0:
            f = note(root) / 2
            v = triangle(f, step * 1.8)
            v *= env(len(v), a=0.004, d=0.08, s=0.55, r=0.12) * 0.30
            i0 = int(t0 * SR)
            out[i0:i0 + len(v)] += v[:len(out) - i0]
        # 鼓
        if s % 8 == 0:                                # 底鼓
            v = np.sin(2 * np.pi * np.linspace(120, 45, int(SR * 0.12))) * \
                env(int(SR * 0.12), a=0.001, d=0.04, s=0.3, r=0.06) * 0.42
            i0 = int(t0 * SR)
            out[i0:i0 + len(v)] += v[:len(out) - i0]
        if s % 8 == 4:                                # 军鼓
            v = noise(0.10, rnd) * env(int(SR * 0.10), a=0.001, d=0.03, s=0.15, r=0.05) * 0.20
            i0 = int(t0 * SR)
            out[i0:i0 + len(v)] += v[:len(out) - i0]
        if s % 2 == 1:                                # 踩镲
            v = noise(0.035, rnd) * env(int(SR * 0.035), a=0.001, d=0.008, s=0.05, r=0.02) * 0.09
            i0 = int(t0 * SR)
            out[i0:i0 + len(v)] += v[:len(out) - i0]

    out = out[:int(SR * dur)]
    # 轻微低通, 去掉方波的刺耳高频
    k = np.hanning(5)
    k /= k.sum()
    out = np.convolve(out, k.astype(np.float32), mode="same")
    # 首尾淡入淡出
    f = int(SR * 0.6)
    out[:f] *= np.linspace(0, 1, f)
    out[-f:] *= np.linspace(1, 0, f)
    return np.clip(out, -1, 1) * 0.9


# --------------------------------------------------------------------------
# 音效
# --------------------------------------------------------------------------
def sfx(kind: str, seed: int = 11) -> np.ndarray:
    rnd = np.random.default_rng(seed)
    if kind == "blip":                                # 打字机
        v = square(880 + rnd.integers(0, 160), 0.022, duty=0.25)
        v *= env(len(v), a=0.001, d=0.006, s=0.25, r=0.01) * 0.5
    elif kind == "select":
        v = square(660, 0.05, duty=0.5) * env(int(SR * 0.05), a=0.002, d=0.02, s=0.3, r=0.02) * 0.5
    elif kind == "confirm":
        a = square(note("C5"), 0.06, 0.5) * env(int(SR * .06), a=.002, d=.02, s=.4, r=.02) * .45
        b = square(note("G5"), 0.09, 0.5) * env(int(SR * .09), a=.002, d=.03, s=.4, r=.03) * .45
        v = np.concatenate([a, b])
    elif kind == "error":
        a = square(180, 0.12, 0.5) * env(int(SR * .12), a=.002, d=.04, s=.5, r=.04) * .5
        b = square(120, 0.18, 0.5) * env(int(SR * .18), a=.002, d=.05, s=.5, r=.06) * .5
        v = np.concatenate([a, b])
    elif kind == "levelup":
        seq = ["C5", "E5", "G5", "C6"]
        parts = []
        for i, n in enumerate(seq):
            d = 0.09 + i * 0.02
            p = square(note(n), d, 0.5) * env(int(SR * d), a=.002, d=.03, s=.5, r=.04) * .4
            parts.append(p)
        v = np.concatenate(parts)
    elif kind == "whoosh":
        v = noise(0.35, rnd) * env(int(SR * 0.35), a=0.05, d=0.15, s=0.3, r=0.15) * 0.28
        v = np.convolve(v, np.ones(24, dtype=np.float32) / 24, mode="same")
    elif kind == "pop":
        ph = np.linspace(300, 900, int(SR * 0.07))
        v = np.sin(2 * np.pi * ph * np.arange(len(ph)) / SR) * \
            env(len(ph), a=0.002, d=0.03, s=0.2, r=0.02) * 0.35
    elif kind == "coin":                                  # 马里奥式吃金币: B5 -> E6
        a = square(note("B5"), 0.055, 0.25) * env(int(SR * 0.055), a=.001, d=.01, s=.5, r=.01)
        b = square(note("E6"), 0.17, 0.25) * env(int(SR * 0.17), a=.001, d=.02, s=.45, r=.10)
        v = np.concatenate([a, b]) * 0.5
    elif kind == "jump":                                  # 起跳: 上滑音
        n = int(SR * 0.13)
        f = np.linspace(380, 900, n)
        v = np.sin(2 * np.pi * np.cumsum(f) / SR) * \
            env(n, a=0.002, d=0.04, s=0.5, r=0.05) * 0.5
    elif kind == "stomp":                                 # 踩敌人
        n = int(SR * 0.11)
        f = np.linspace(420, 90, n)
        v = np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, a=.001, d=.03, s=.4, r=.05) * 0.45
        v += noise(0.11, rnd) * env(n, a=.001, d=.02, s=.2, r=.04) * 0.25
    elif kind == "powerup":                               # 顶到问号块/吃到强化
        seq = ["E5", "G5", "C6", "E6"]
        parts = []
        for i, nm in enumerate(seq):
            d = 0.055
            parts.append(square(note(nm), d, 0.25) *
                         env(int(SR * d), a=.001, d=.01, s=.5, r=.015) * 0.42)
        v = np.concatenate(parts)
    elif kind == "page":                                  # 翻书页: 轻噪音
        n = int(SR * 0.22)
        x = np.random.default_rng(5).standard_normal(n).astype(np.float32)
        x = lfilter([1.0, -0.7], [1.0], x)
        v = x * env(n, a=0.004, d=0.05, s=0.25, r=0.14) * 0.22
    elif kind == "chime":                                 # 安静的铃(字幕浮出)
        n = int(SR * 1.4)
        t = np.arange(n, dtype=np.float32) / SR
        f = note("C6")
        v = (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * f * 2 * t) * np.exp(-t * 3)) \
            * np.exp(-t * 2.2).astype(np.float32) * 0.22
    else:
        v = np.zeros(int(SR * 0.05), dtype=np.float32)
    return np.clip(v, -1, 1)


# --------------------------------------------------------------------------
# 中文旁白: 实现搬到 studio/tts.py, 这里转发以保持 audio.tts(...) 的旧调用方式
# --------------------------------------------------------------------------
from .tts import (  # noqa: E402,F401
    VOICE_EDGE, VOICE_ONECORE, VOICE_SAPI, humanize, prosody_ssml, tts,
)


# --------------------------------------------------------------------------
# 混音 / 落盘
# --------------------------------------------------------------------------
class Mixer:
    def __init__(self, dur: float):
        self.dur = dur
        self.buf = np.zeros(int(SR * dur) + SR, dtype=np.float32)

    def add(self, wave_: np.ndarray, at: float, gain: float = 1.0):
        i0 = max(0, int(at * SR))
        seg = wave_[:max(0, len(self.buf) - i0)] * gain
        if len(seg):
            self.buf[i0:i0 + len(seg)] += seg

    def render(self, master_gain=0.9):
        b = self.buf[:int(SR * self.dur)]
        peak = float(np.max(np.abs(b))) or 1.0
        if peak > 1.0:
            b = b / peak
        return np.clip(b * master_gain, -1, 1)


def ambience(kind: str, dur: float, seed: int = 17) -> np.ndarray:
    """环境声床: waves(海浪) / rain(雨)。读书号那种氛围底的必需品。"""
    if dur <= 0.2:
        return np.zeros(1, dtype=np.float32)
    rnd = np.random.default_rng(seed)
    n = int(SR * dur)
    x = rnd.standard_normal(n).astype(np.float32)
    if kind == "waves":
        x = lfilter([0.03], [1.0, -0.97], x)                    # 重低通 -> 低频涌动
        swell = 0.45 + 0.55 * np.sin(2 * np.pi * np.arange(n) / (SR * 6.5))
        x = x * swell.astype(np.float32)
        x = x / (np.abs(x).max() or 1.0) * 0.55
    else:                                                       # rain
        x = lfilter([1.0, -0.55], [1.0, -0.9], x)
        x = lfilter([0.5], [1.0, -0.5], x)
        x = x / (np.abs(x).max() or 1.0) * 0.34
    f = min(int(SR * 1.8), n // 2)
    if f > 0:
        x[:f] *= np.linspace(0, 1, f)
        x[-f:] *= np.linspace(1, 0, f)
    return np.clip(x, -1, 1).astype(np.float32)


def compress(x, thresh_db=-16.0, ratio=2.6, attack=0.006, release=0.20,
             makeup_db=3.5):
    """轻量总线压缩: 把平均响度提上来, 同时让"说话/留白"的电平差更平顺。

    x 可以是 (N,) 或 (N,2); 用快启动 + 慢释放两条包络取较大者(向量化, 不做逐样本循环)。
    """
    y = np.asarray(x, dtype=np.float32)
    mono = np.abs(y).max(axis=1) if y.ndim == 2 else np.abs(y)
    fast = lfilter([1 - math.exp(-1 / (attack * SR))], [1.0, -math.exp(-1 / (attack * SR))], mono)
    slow = lfilter([1 - math.exp(-1 / (release * SR))], [1.0, -math.exp(-1 / (release * SR))], mono)
    env = np.maximum(np.abs(fast), np.abs(slow)).astype(np.float32)
    thr = 10 ** (thresh_db / 20.0)
    gain = np.ones_like(env)
    over = env > thr
    gain[over] = ((thr + (env[over] - thr) / ratio) / env[over]).astype(np.float32)
    gain *= 10 ** (makeup_db / 20.0)
    g = gain[:, None] if y.ndim == 2 else gain
    out = y * g
    peak = float(np.abs(out).max()) or 1.0
    if peak > 0.95:
        out = out * (0.95 / peak)
    return out.astype(np.float32)


def write_wav(path: str, data: np.ndarray):
    """写 16-bit PCM WAV; data 可以是 (N,) 单声道或 (N,2) 立体声。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    x = np.clip(np.asarray(data, dtype=np.float32), -1, 1)
    stereo = x.ndim == 2 and x.shape[1] == 2
    pcm = (x * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2 if stereo else 1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return path

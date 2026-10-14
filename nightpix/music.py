# -*- coding: utf-8 -*-
"""程序化配乐引擎: 按镜头分段编排的 16-bit 芯片音乐(立体声)。

设计目标 —— "适合视频氛围":
  * 不是一段 8 小节循环, 而是跟着叙事走: 每个镜头有自己的和弦、配器、密度;
  * 段落之间用 riser / downlifter / 定音鼓式 sting 过渡, 让情绪有起承转合;
  * 输出立体声(琶音/铃铛轻微左右铺开), 给竖屏手机也有空间感;
  * 全部离线合成, 结果可复现。

用法:
    song = build(duration, sections, bpm=96, seed=7)   # -> (N,2) float32
"""
import math

import numpy as np
from scipy.signal import lfilter

from . import config as C

SR = 44100
PITCH = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5,
         "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}
MINOR = (0, 2, 3, 5, 7, 8, 10)
MAJOR = (0, 2, 4, 5, 7, 9, 11)


def nf(name: str) -> float:
    """音名 -> 频率 (A4 = 440)。"""
    i = 2 if len(name) > 1 and name[1] in "#b" else 1
    return 440.0 * 2 ** ((PITCH[name[:i]] + (int(name[i:]) - 4) * 12 - 9) / 12)


def _n(dur):
    return np.arange(int(SR * dur), dtype=np.float32) / SR


def _env(n, a=0.005, d=0.08, s=0.6, r=0.10, curve=1.0):
    e = np.full(n, s, dtype=np.float32)
    ai, di, ri = min(int(SR * a), n), min(int(SR * d), n), min(int(SR * r), n)
    if ai:
        e[:ai] = np.linspace(0, 1, ai)
    if di:
        end = min(n, ai + di)
        e[ai:end] = np.linspace(1, s, end - ai) ** curve
    if ri and n - ri > 0:
        e[n - ri:] = np.linspace(e[max(0, n - ri - 1)], 0, ri)
    return e


# --------------------------------------------------------------------------
# 音色
# --------------------------------------------------------------------------
def pulse(f, dur, duty=0.5):
    ph = (_n(dur) * f) % 1.0
    return np.where(ph < duty, 1.0, -1.0).astype(np.float32)


def tri(f, dur):
    ph = (_n(dur) * f) % 1.0
    return (4 * np.abs(ph - 0.5) - 1).astype(np.float32)


def _onepole(x, cutoff):
    a = math.exp(-2 * math.pi * cutoff / SR)
    return lfilter([1 - a], [1.0, -a], x).astype(np.float32)


def saw(f, dur, cutoff=2600.0):
    ph = (_n(dur) * f) % 1.0
    return _onepole((2 * ph - 1).astype(np.float32), cutoff)


def bell(f, dur):
    t = _n(dur)
    return (np.sin(2 * math.pi * f * t) * 0.7 +
            np.sin(2 * math.pi * f * 2.01 * t) * 0.2 +
            np.sin(2 * math.pi * f * 3.02 * t) * 0.1).astype(np.float32) * \
        np.exp(-t * 4.5).astype(np.float32)


def sub(f, dur):
    return np.sin(2 * math.pi * f * _n(dur)).astype(np.float32)


def pad(f, dur, detune=0.008):
    x = (saw(f * (1 - detune), dur, 1800) + saw(f, dur, 1800) * 0.9 +
         saw(f * (1 + detune), dur, 1800)) / 2.9
    return x * _env(len(x), a=0.25, d=0.4, s=0.75, r=0.6)


def kick(dur=0.16):
    t = _n(dur)
    f = np.linspace(132, 46, len(t))
    return (np.sin(2 * math.pi * np.cumsum(f) / SR) * 0.9).astype(np.float32) * \
        _env(len(t), a=0.001, d=0.05, s=0.25, r=0.07)


def snare(rnd, dur=0.13):
    x = rnd.standard_normal(int(SR * dur)).astype(np.float32)
    x = np.diff(x, prepend=0)                          # 粗糙高通
    return x * _env(len(x), a=0.001, d=0.03, s=0.12, r=0.05) * 0.55


def hat(rnd, dur=0.045, open_=False):
    d = 0.16 if open_ else dur
    x = rnd.standard_normal(int(SR * d)).astype(np.float32)
    x = np.diff(x, prepend=0)
    return x * _env(len(x), a=0.0005, d=0.01, s=0.05, r=d * 0.5) * (0.30 if open_ else 0.22)


def tick(dur=0.03):
    t = _n(dur)
    return (np.sin(2 * math.pi * 1900 * t) * np.exp(-t * 260)).astype(np.float32) * 0.4


def riser(dur, f0=180, f1=1400, rnd=None):
    rnd = rnd or np.random.default_rng(1)
    t = _n(dur)
    f = np.linspace(f0, f1, len(t))
    x = np.sin(2 * math.pi * np.cumsum(f) / SR).astype(np.float32) * 0.5
    x += rnd.standard_normal(len(t)).astype(np.float32) * 0.25
    return x * (np.linspace(0, 1, len(t)) ** 2).astype(np.float32)


def downlifter(dur, f0=900, f1=120):
    t = _n(dur)
    f = np.linspace(f0, f1, len(t))
    return (np.sin(2 * math.pi * np.cumsum(f) / SR) * 0.6).astype(np.float32) * \
        (np.linspace(1, 0, len(t)) ** 1.5).astype(np.float32)


def piano(f, dur, decay=1.5, bright=2400.0):
    """软起音、长衰减的钢琴音(读书号那种安静配器)。"""
    t = _n(dur)
    x = (np.sin(2 * math.pi * f * t) +
         0.32 * np.sin(2 * math.pi * f * 2 * t) * np.exp(-t * 3.2) +
         0.12 * np.sin(2 * math.pi * f * 3.01 * t) * np.exp(-t * 5.0))
    x = x.astype(np.float32) * (1 - np.exp(-t * 80)).astype(np.float32) * \
        np.exp(-t * decay).astype(np.float32)
    return _onepole(x, bright)


def vinyl(dur, rnd=None, level=0.5):
    """黑胶底噪 + 偶发爆豆。"""
    rnd = rnd or np.random.default_rng(9)
    n = int(SR * dur)
    x = rnd.standard_normal(n).astype(np.float32) * 0.06
    x = _onepole(x, 3800)
    for _ in range(int(dur * 6)):
        i = rnd.integers(0, max(1, n - 400))
        w = rnd.integers(60, 400)
        x[i:i + w] += rnd.standard_normal(w).astype(np.float32) * 0.12
    return (x * level).astype(np.float32)


# --------------------------------------------------------------------------
# 效果
# --------------------------------------------------------------------------
def echo(x, delay=0.28, feedback=0.32, mix=0.28, pingpong=True):
    """单声道回声; 立体声铺开在 build 里做。"""
    d = int(delay * SR)
    y = x.copy()
    buf = np.zeros(len(x) + d, dtype=np.float32)
    buf[:len(x)] = x
    g = feedback
    while g > 0.02:
        buf[d:] += x[:len(buf) - d] * g
        g *= feedback
    y = buf[:len(x)] * (1 - mix) + x * mix
    return y.astype(np.float32)


def lowpass(x, cutoff=3000.0, order=1):
    y = x
    for _ in range(order):
        y = _onepole(y, cutoff)
    return y


def place(dst, x, at, gain=1.0):
    i0 = int(at * SR)
    if i0 >= len(dst):
        return
    seg = x[:len(dst) - i0] * gain
    dst[i0:i0 + len(seg)] += seg


# --------------------------------------------------------------------------
# 编曲
# --------------------------------------------------------------------------
# 每个段落用 style 决定节奏型, 避免写死一大堆积木
BASS_PAT = {
    "hold":  [(0, 2.0)],
    "pulse": [(0, 0.5), (1, 0.5), (2, 0.5), (3, 0.5), (4, 0.5), (5, 0.5), (6, 0.5), (7, 0.5)],
    "drive": [(0, 0.75), (1.5, 0.5), (2, 0.5), (3.5, 0.5), (4, 0.75), (5.5, 0.5), (6, 0.5), (7, 0.5)],
    "stab":  [(0, 0.5), (3, 0.5), (4, 0.5), (6, 0.5)],
    "march": [(0, 0.45), (1, 0.45), (2, 0.45), (3, 0.45), (4, 0.45), (5, 0.45),
              (6, 0.45), (7, 0.45)],
    "long":  [(0, 7.6)],
    "half":  [(0, 3.6), (4, 3.6)],
}
LEAD_PAT = {
    "sparse":  [0, 2, 4],
    "question": [0, 2, 4, 3, 2],
    "rise":    [0, 1, 2, 3, 4, 5, 6],
    "resolve": [4, 2, 0],
    "descend": [6, 4, 3, 2, 0],
    "bounce":  [0, 2, 1, 2, 4, 2, 1, 2],
    "hero":    [0, 1, 2, 3, 4, 3, 2, 1],
    "calm1":   [4],
    "calm2":   [4, 0],
    "calm3":   [4, 2, 0],
    "calm4":   [2, 4, 1, 0],
}


def whale_song(dur=4.0, f0=90.0, f1=260.0, vib=5.0):
    """鲸歌: 缓慢上滑的正弦 + 颤音, 用在段落开头当"呼吸"。"""
    t = _n(dur)
    base = np.linspace(f0, f1, len(t))
    f = base * (1 + 0.03 * np.sin(2 * math.pi * vib * t))
    x = np.sin(2 * math.pi * np.cumsum(f) / SR).astype(np.float32)
    x += 0.25 * np.sin(2 * math.pi * np.cumsum(f * 2.01) / SR).astype(np.float32)
    envl = np.sin(math.pi * np.clip(t / dur, 0, 1)) ** 1.4
    return (x * envl.astype(np.float32) * 0.5).astype(np.float32)


def _chord_tones(chord, mode=MINOR, octave=0):
    """和弦名(如 Am / F / C / G7 / Dm) -> 三个音的音名。"""
    root = chord[0] + (chord[1] if len(chord) > 1 and chord[1] in "#b" else "")
    qual = chord[len(root):]
    base = PITCH[root] + 12 * octave
    third = 3 if qual.startswith("m") and not qual.startswith("maj") else 4
    fifth = 6 if qual.startswith("dim") else (8 if qual.startswith("aug") else 7)
    names = []
    for semi in (0, third, fifth):
        v = base + semi
        name = next((k for k, s in PITCH.items() if s == v % 12 and len(k) <= 2), "C")
        names.append(f"{name}{4 + v // 12}")
    return names


def build(dur: float, sections: list[dict], bpm: float = 96.0, seed: int = 7,
          stereo_width: float = 0.35, master: float = 1.0,
          swing: float = 0.0) -> np.ndarray:
    """按段落编排整首配乐, 返回 (N,2) float32。

    sections: [{"t0","t1","chords":[..],"style":BASS_PAT 键,"lead":LEAD_PAT 键,
                "layers":["pad","arp","lead","bass","kick","snare","hat","tick","bell"],
                "gain":0.9,"swing":0.0}]
    """
    rnd = np.random.default_rng(seed)
    n = int(SR * (dur + 1.5))
    L = np.zeros(n, dtype=np.float32)
    R = np.zeros(n, dtype=np.float32)
    beat = 60.0 / bpm
    eighth = beat / 2
    bar = beat * 4

    def add(x, at, gain, pan=0.0, mono=False):
        gl = gain * math.sqrt(max(0.0, 1 - max(0.0, pan)))
        gr = gain * math.sqrt(max(0.0, 1 + min(0.0, pan)))
        if mono:
            gl = gr = gain
        place(L, x, at, gl)
        place(R, x, at, gr)

    for si, sec in enumerate(sections):
        t0, t1 = float(sec["t0"]), float(sec["t1"])
        chords = sec.get("chords") or ["Am", "F", "C", "G"]
        layers = set(sec.get("layers") or ["pad", "arp", "bass"])
        g = float(sec.get("gain", 1.0))
        style = sec.get("style", "pulse")
        lead_style = sec.get("lead", "sparse")
        nbar = max(1, int(round((t1 - t0) / bar)))
        for b in range(nbar):
            bt = t0 + b * bar
            if bt >= dur:
                break
            chord = chords[b % len(chords)]
            ct = _chord_tones(chord)
            root = ct[0]
            # 段落过渡: 第一小节铺 riser, 最后一小节收 downlifter
            if b == 0 and si > 0:
                add(riser(min(bar * 0.9, 1.6), rnd=rnd), bt - bar * 0.5, 0.16 * g, mono=True)
            if b == nbar - 1 and si < len(sections) - 1:
                add(downlifter(0.7), bt + bar * 0.55, 0.12 * g, mono=True)
            # 垫底和弦
            if "pad" in layers:
                for i, nm in enumerate(ct):
                    add(pad(nf(nm) / 2, bar * 0.98), bt, 0.075 * g,
                        pan=(-0.3 if i == 0 else (0.3 if i == 2 else 0.0)))
            # 贝斯
            if "bass" in layers:
                binst = sec.get("bass_inst", "tri")
                for k, (off, ln) in enumerate(BASS_PAT.get(style, BASS_PAT["pulse"])):
                    nm = root
                    if style == "march":
                        nm = [root, ct[2] if len(ct) > 2 else root, root,
                              root.replace("4", "5") if root.endswith("4") else root][k % 4]
                    f = nf(nm) / 2
                    sw = swing * eighth if int(off * 2) % 2 else 0.0
                    if binst == "piano":
                        x = piano(f, eighth * ln, decay=0.9) * 0.30
                    elif binst == "sub":
                        x = sub(f, eighth * ln) * _env(int(SR * eighth * ln), 0.15, 0.2, 0.7, 0.3) * 0.34
                    else:
                        x = tri(f, eighth * ln) * _env(int(SR * eighth * ln), a=0.004, d=0.05,
                                                       s=0.5, r=0.05) * 0.30
                    add(x, bt + off * eighth + sw, g, mono=True)
                    if binst != "sub":
                        add(sub(f, eighth * ln) * _env(int(SR * eighth * ln), 0.004, 0.05, 0.4, 0.05) * 0.12,
                            bt + off * eighth + sw, g, mono=True)
            # 琶音
            if "arp" in layers:
                for k in range(8):
                    nm = ct[k % len(ct)]
                    f = nf(nm) * (2 if k % 4 >= 2 else 1)
                    x = pulse(f, eighth * 0.85, duty=0.25)
                    x *= _env(len(x), a=0.002, d=0.03, s=0.22, r=0.04) * 0.10
                    add(x, bt + k * eighth + (swing * eighth if k % 2 else 0), g,
                        pan=(-0.45 if k % 2 else 0.45))
            # 主旋律
            if "lead" in layers:
                pat = LEAD_PAT.get(lead_style, LEAD_PAT["sparse"])
                inst = sec.get("lead_inst", "pulse")
                slots = 8
                step = max(1, slots // max(1, len(pat)))
                for k, deg in enumerate(pat):
                    if k * step >= slots:
                        break
                    note = ct[deg % len(ct)]
                    f = nf(note) * (2 if deg >= len(ct) else 1)
                    if inst == "piano":
                        x = piano(f, eighth * 5.0, decay=1.1) * 0.30
                    elif inst == "bell":
                        x = bell(f, eighth * 5.0) * 0.14
                    else:
                        x = pulse(f, eighth * 1.6, duty=0.5) * \
                            _env(int(SR * eighth * 1.6), a=0.006, d=0.07, s=0.45, r=0.10) * 0.16
                        x = echo(x, delay=eighth * 3, feedback=0.28, mix=0.22)
                    kk = k * step
                    add(x, bt + kk * eighth + (swing * eighth if kk % 2 else 0), g, pan=0.15)
            # 鲸歌: 段落开头的一声长鸣
            if "whale" in layers and b == 0:
                add(whale_song(min(5.0, bar * 1.6), f0=70, f1=210), bt + eighth, g * 0.34)
            # 黑胶底噪
            if "vinyl" in layers and b == 0:
                add(vinyl(bar * nbar, rnd, level=0.5), bt, g * 0.5, mono=True)
            # 铃铛点缀
            if "bell" in layers and b % 2 == 1:
                nm = ct[2]
                add(bell(nf(nm) * 2, beat * 1.4) * 0.11, bt + beat * 2, g, pan=-0.25)
            # 鼓组
            if "kick" in layers:
                for off in (0, 2, 4, 6):
                    add(kick(), bt + off * eighth, g, mono=True)
                if style == "drive":
                    add(kick(), bt + 7 * eighth, g, mono=True)
            if "snare" in layers:
                for off in (2, 6):
                    add(snare(rnd), bt + off * eighth, g * 0.9, mono=True)
            if "hat" in layers:
                for k in range(8):
                    add(hat(rnd, open_=(k == 7)), bt + k * eighth,
                        g * (0.9 if k % 2 else 0.55), pan=0.12 if k % 2 else -0.12, mono=True)
            if "tick" in layers:
                for k in range(4):
                    add(tick(), bt + k * beat, g * 0.5, pan=-0.2, mono=True)

    # 收尾: 全局低通去掉毛刺 + 首尾淡入淡出
    L = lowpass(L, 5200.0)
    R = lowpass(R, 5200.0)
    f = int(SR * 1.2)
    fade = np.linspace(0, 1, f, dtype=np.float32)
    L[:f] *= fade
    R[:f] *= fade
    L[-f:] *= fade[::-1]
    R[-f:] *= fade[::-1]
    out = np.stack([L, R], axis=1)[:int(SR * dur)]
    peak = float(np.abs(out).max()) or 1.0
    if peak > 0.85:
        out = out * (0.85 / peak)
    return (out * master).astype(np.float32)


# --------------------------------------------------------------------------
# 两期视频的配乐方案
# --------------------------------------------------------------------------
def psy_song(shots, dur: float) -> np.ndarray:
    """心理学科普: 悬念铺底 -> 实验推进 -> 名词揭示 -> 机制高潮 -> 陷阱紧绷 -> 破解回暖 -> 收束。"""
    s = {x["key"]: x for x in shots}

    def band(key, a=0.0, b=1.0):
        sh = s[key]
        return sh["start"] + sh["dur"] * a, sh["start"] + sh["dur"] * b

    secs = []
    t0, t1 = band("hook", 0.0, 0.55)
    secs.append(dict(t0=t0, t1=t1, chords=["Am", "F", "C", "G"], style="hold",
                     lead="sparse", layers=["pad", "tick", "bell"], gain=0.85))
    t0, t1 = band("hook", 0.55, 1.0)
    secs.append(dict(t0=t0, t1=t1, chords=["Am", "F", "C", "E7"], style="pulse",
                     lead="question", layers=["pad", "arp", "bass", "tick"],
                     gain=0.95))
    t0, t1 = band("experiment", 0.0, 1.0)
    secs.append(dict(t0=t0, t1=t1, chords=["Am", "Am", "F", "G"], style="drive",
                     lead="sparse", layers=["pad", "arp", "bass", "kick", "snare", "hat"],
                     gain=1.0))
    t0, t1 = band("naming", 0.0, 0.45)
    secs.append(dict(t0=t0, t1=t1, chords=["C", "G"], style="stab", lead="rise",
                     layers=["pad", "bell"], gain=0.9))
    t0, t1 = band("naming", 0.45, 1.0)
    secs.append(dict(t0=t0, t1=t1, chords=["C", "Am", "F", "G"], style="pulse",
                     lead="resolve", layers=["pad", "arp", "bass", "bell"], gain=1.0))
    t0, t1 = band("brain", 0.0, 0.55)
    secs.append(dict(t0=t0, t1=t1, chords=["Am", "F", "Dm", "E7"], style="drive",
                     lead="rise", layers=["pad", "arp", "bass", "kick", "hat", "bell"],
                     gain=1.05))
    t0, t1 = band("brain", 0.55, 1.0)
    secs.append(dict(t0=t0, t1=t1, chords=["Dm", "E7", "Am", "G"], style="drive",
                     lead="descend", layers=["pad", "arp", "bass", "kick", "snare", "hat"],
                     gain=1.0))
    t0, t1 = band("traps", 0.0, 1.0)
    secs.append(dict(t0=t0, t1=t1, chords=["Am", "G", "F", "E7"], style="stab",
                     lead="question", layers=["pad", "bass", "tick", "kick", "bell"],
                     gain=0.95))
    t0, t1 = band("escape", 0.0, 1.0)
    secs.append(dict(t0=t0, t1=t1, chords=["C", "G", "Am", "F"], style="pulse",
                     lead="resolve", layers=["pad", "arp", "bass", "hat", "bell"],
                     gain=1.0))
    t0, t1 = band("ending", 0.0, 1.0)
    secs.append(dict(t0=t0, t1=t1, chords=["F", "G", "C", "C"], style="hold",
                     lead="resolve", layers=["pad", "bell"], gain=0.9))
    return build(dur, secs, bpm=92, seed=17)


def ep01_song(shots, dur: float) -> np.ndarray:
    """AI 科普: 明快、好奇、机械感, 结尾留一点「别全信」的小转折。"""
    s = {x["key"]: x for x in shots}

    def band(key, a=0.0, b=1.0):
        sh = s[key]
        return sh["start"] + sh["dur"] * a, sh["start"] + sh["dur"] * b

    secs = []
    t0, t1 = band("hook", 0.0, 0.45)
    secs.append(dict(t0=t0, t1=t1, chords=["C", "G"], style="hold", lead="rise",
                     layers=["pad", "bell"], gain=0.9))
    t0, t1 = band("hook", 0.45, 1.0)
    secs.append(dict(t0=t0, t1=t1, chords=["C", "Am", "F", "G"], style="pulse",
                     lead="question", layers=["pad", "arp", "bass", "hat"], gain=1.0))
    t0, t1 = band("train", 0.0, 1.0)
    secs.append(dict(t0=t0, t1=t1, chords=["C", "G", "Am", "F"], style="drive",
                     lead="sparse", layers=["pad", "arp", "bass", "kick", "snare", "hat"],
                     gain=1.0))
    t0, t1 = band("predict", 0.0, 1.0)
    secs.append(dict(t0=t0, t1=t1, chords=["F", "C", "G", "Am"], style="pulse",
                     lead="question", layers=["pad", "arp", "bass", "hat", "bell"],
                     gain=1.0))
    t0, t1 = band("answer", 0.0, 1.0)
    secs.append(dict(t0=t0, t1=t1, chords=["C", "F", "G", "C"], style="pulse",
                     lead="resolve", layers=["pad", "arp", "bass", "kick", "hat", "bell"],
                     gain=1.05))
    t0, t1 = band("twist", 0.0, 0.55)
    secs.append(dict(t0=t0, t1=t1, chords=["Am", "Dm", "E7", "Am"], style="stab",
                     lead="descend", layers=["pad", "bass", "tick", "bell"], gain=0.95))
    t0, t1 = band("twist", 0.55, 1.0)
    secs.append(dict(t0=t0, t1=t1, chords=["F", "G", "C", "C"], style="hold",
                     lead="resolve", layers=["pad", "bell"], gain=0.9))
    t0, t1 = band("end", 0.0, 1.0)
    secs.append(dict(t0=t0, t1=t1, chords=["C", "G", "C", "C"], style="pulse",
                     lead="resolve", layers=["pad", "arp", "bass", "bell", "hat"], gain=1.0))
    return build(dur, secs, bpm=112, seed=5)


def mario_song(shots, dur: float) -> np.ndarray:
    """马里奥风格: C 大调、快板、摇摆八分、根音-五度行进贝斯, 一路蹦跳向前。

    段落跟着关卡走 —— 探索(平稳) -> 实验(推进) -> 揭示(亮) -> 机制(最密)
    -> 泄气(转小调、配器变薄) -> 重新起跑(回大调) -> 旗杆(收束和弦)。
    """
    s = {x["key"]: x for x in shots}

    def band(key, a=0.0, b=1.0):
        sh = s[key]
        return sh["start"] + sh["dur"] * a, sh["start"] + sh["dur"] * b

    secs = []
    t0, t1 = band("hook", 0.0, 0.5)
    secs.append(dict(t0=t0, t1=t1, chords=["C", "G"], style="march", lead="bounce",
                     layers=["arp", "bass", "hat"], gain=0.95))
    t0, t1 = band("hook", 0.5, 1.0)
    secs.append(dict(t0=t0, t1=t1, chords=["C", "Am", "F", "G"], style="march",
                     lead="hero", layers=["arp", "bass", "lead", "hat", "kick"], gain=1.0))
    t0, t1 = band("experiment", 0.0, 1.0)
    secs.append(dict(t0=t0, t1=t1, chords=["F", "G", "C", "Am"], style="march",
                     lead="bounce", layers=["arp", "bass", "lead", "hat", "kick", "snare"],
                     gain=1.0))
    t0, t1 = band("naming", 0.0, 0.4)
    secs.append(dict(t0=t0, t1=t1, chords=["C", "G"], style="march", lead="rise",
                     layers=["arp", "bass", "bell"], gain=1.0))
    t0, t1 = band("naming", 0.4, 1.0)
    secs.append(dict(t0=t0, t1=t1, chords=["F", "C", "G", "C"], style="march",
                     lead="bounce", layers=["arp", "bass", "lead", "bell", "hat"], gain=1.0))
    t0, t1 = band("brain", 0.0, 1.0)
    secs.append(dict(t0=t0, t1=t1, chords=["C", "Am", "F", "G"], style="march",
                     lead="hero", layers=["arp", "bass", "lead", "kick", "snare", "hat",
                                          "bell"], gain=1.05))
    t0, t1 = band("traps", 0.0, 0.55)
    secs.append(dict(t0=t0, t1=t1, chords=["Am", "Dm", "E7", "Am"], style="stab",
                     lead="descend", layers=["bass", "pad", "tick"], gain=0.9))
    t0, t1 = band("traps", 0.55, 1.0)
    secs.append(dict(t0=t0, t1=t1, chords=["Am", "Am", "E7", "E7"], style="hold",
                     lead="descend", layers=["pad", "tick"], gain=0.75))
    t0, t1 = band("escape", 0.0, 1.0)
    secs.append(dict(t0=t0, t1=t1, chords=["C", "G", "Am", "F"], style="march",
                     lead="bounce", layers=["arp", "bass", "lead", "hat", "kick", "bell"],
                     gain=1.05))
    t0, t1 = band("ending", 0.0, 1.0)
    secs.append(dict(t0=t0, t1=t1, chords=["F", "G", "C", "C"], style="march",
                     lead="resolve", layers=["arp", "bass", "lead", "bell", "hat"],
                     gain=1.05))
    return build(dur, secs, bpm=152, seed=23, swing=0.14)


def calm_song(shots, dur: float) -> np.ndarray:
    """读书号配乐: 62 BPM 的钢琴 + 垫底 + 黑胶底噪, 每段只留几个音, 大量留白。

    段落跟着画面走: 夜海(疏) -> 书桌(暖) -> 雨夜城市(暗) -> 雨窗(收) -> 日出(亮) -> 星空(散)。
    """
    s = {x["key"]: x for x in shots}

    def band(key, a=0.0, b=1.0):
        sh = s[key]
        return sh["start"] + sh["dur"] * a, sh["start"] + sh["dur"] * b

    secs = []
    plan = [
        ("sea", 0.0, 1.0, ["Cmaj7", "Am7"], "calm2", 0.85, ["pad", "lead", "bass", "vinyl"]),
        ("book", 0.0, 1.0, ["Fmaj7", "Cmaj7"], "calm3", 0.95, ["pad", "lead", "bass", "bell", "vinyl"]),
        ("city", 0.0, 1.0, ["Am7", "Fmaj7", "Dm7", "G"], "calm1", 0.9, ["pad", "lead", "bass", "vinyl"]),
        ("rain", 0.0, 1.0, ["Dm7", "G"], "calm2", 0.85, ["pad", "lead", "bass", "vinyl"]),
        ("dawn", 0.0, 1.0, ["F", "G", "C", "Am7"], "calm3", 1.0, ["pad", "lead", "bass", "bell"]),
        ("stars", 0.0, 1.0, ["Cmaj7", "Fmaj7", "Cmaj7", "Cmaj7"], "calm4", 0.95,
         ["pad", "lead", "bass", "bell"]),
    ]
    for key, a, b, chords, lead, gain, layers in plan:
        t0, t1 = band(key, a, b)
        secs.append(dict(t0=t0, t1=t1, chords=chords, style="long", lead=lead,
                         lead_inst="piano", bass_inst="sub", layers=layers, gain=gain))
    return build(dur, secs, bpm=62, seed=41, master=0.9)



def night_song(shots, dur: float) -> np.ndarray:
    """《深夜效应》配乐: 70 BPM, A 小调起步, 末段转 C 大调。

    段落跟画面走:
      天花板(极疏) -> 同一个你(冷暖对峙) -> 刹车没了(紧) -> 情绪曲线(下行)
      -> 反刍(打转) -> 屏幕(冷躁) -> 拔河(时钟滴答) -> 天亮(转大调)
    """
    s = {x["key"]: x for x in shots}

    def band(key, a=0.0, b=1.0):
        sh = s[key]
        return sh["start"] + sh["dur"] * a, sh["start"] + sh["dur"] * b

    plan = [
        ("ceiling_3am",     ["Am7", "Am7", "Fmaj7", "Fmaj7"], "calm2", 0.80,
         ["pad", "lead", "bass", "vinyl"]),
        ("two_yous",        ["Am7", "Fmaj7", "C", "G"],        "calm3", 0.86,
         ["pad", "lead", "bass", "vinyl"]),
        ("brake_gauge",     ["Am", "Dm", "E7", "Am"],          "calm1", 0.92,
         ["pad", "lead", "bass", "tick"]),
        ("emotion_curve",   ["Am7", "Dm7", "G", "Cmaj7"],      "calm2", 0.90,
         ["pad", "lead", "bass", "bell", "vinyl"]),
        ("rumination_loop", ["Dm", "Dm", "Am", "E7"],          "calm1", 0.94,
         ["pad", "lead", "bass", "arp", "tick"]),
        ("feed_glow",       ["Am", "F", "Dm", "E7"],           "calm4", 0.90,
         ["pad", "lead", "bass", "arp", "hat"]),
        ("sleep_tug",       ["Am", "E7", "Am", "E7"],          "calm3", 0.96,
         ["pad", "lead", "bass", "tick", "bell"]),
        ("dawn_three_moves", ["C", "G", "Am", "F"],            "calm4", 1.00,
         ["pad", "lead", "bass", "bell", "hat"]),
    ]
    secs = []
    for key, chords, lead, gain, layers in plan:
        if key not in s:
            continue
        t0, t1 = band(key)
        secs.append(dict(t0=t0, t1=t1, chords=chords, style="half", lead=lead,
                         lead_inst="piano", bass_inst="sub", layers=layers, gain=gain))
    if not secs:                                  # 兜底: 至少有一段
        secs = [dict(t0=0.0, t1=dur, chords=["Am7", "Fmaj7", "C", "G"], style="half",
                     lead="calm3", lead_inst="piano", bass_inst="sub",
                     layers=["pad", "lead", "bass", "vinyl"], gain=0.9)]
    return build(dur, secs, bpm=70, seed=131, master=0.9)


def whalefall_song(shots, dur: float) -> np.ndarray:
    """深海纪录片配乐: 64 BPM, 大提琴式垫底 + 钢琴 + 鲸歌, 情绪按四幕走。

    海面(暖) -> 下沉(沉) -> 罕见(空) -> 清道夫(紧) -> 骨架(静)
    -> 化能合成(惊奇) -> 万物生(辉煌) -> 礁岩(温柔) -> 尾声(升华)
    """
    s = {x["key"]: x for x in shots}

    def band(key, a=0.0, b=1.0):
        sh = s[key]
        return sh["start"] + sh["dur"] * a, sh["start"] + sh["dur"] * b

    plan = [
        ("surface",  ["F", "C", "G", "Am"], "calm3", 0.95, ["pad", "lead", "bass", "bell"]),
        ("descent",  ["Am", "F", "Dm", "E7"], "calm2", 0.90, ["pad", "lead", "bass", "whale"]),
        ("rare",     ["Dm", "Am", "E7", "Am"], "calm1", 0.80, ["pad", "lead", "bass"]),
        ("scavenge", ["Am", "E7", "Am", "E7"], "calm1", 1.00, ["pad", "bass", "kick", "lead"]),
        ("bones",    ["Am", "Dm", "Am", "E7"], "calm2", 0.85, ["pad", "lead", "bass", "bell"]),
        ("chemo",    ["F", "G", "Am", "E7"], "calm3", 1.00, ["pad", "lead", "bass", "bell",
                                                             "whale"]),
        ("bloom",    ["C", "G", "Am", "F"], "calm4", 1.05, ["pad", "lead", "bass", "bell",
                                                            "hat"]),
        ("reef",     ["F", "C", "G", "C"], "calm3", 0.95, ["pad", "lead", "bass", "bell"]),
        ("ending",   ["C", "F", "C", "C"], "calm2", 0.95, ["pad", "lead", "bass", "whale",
                                                           "bell"]),
    ]
    secs = []
    for key, chords, lead, gain, layers in plan:
        if key not in s:
            continue
        t0, t1 = band(key)
        secs.append(dict(t0=t0, t1=t1, chords=chords, style="half", lead=lead,
                         lead_inst="piano", bass_inst="sub", layers=layers, gain=gain))
    return build(dur, secs, bpm=64, seed=77, master=0.92)

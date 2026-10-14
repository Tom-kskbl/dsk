# -*- coding: utf-8 -*-
r"""中文旁白: 多引擎 + SSML 语气 + 拟人化 DSP。

引擎优先级 edge(神经网络, 需联网) -> onecore(WinRT 本地声音) -> sapi(老 SAPI) -> file(自备录音)
本地声音天生"平", 所以补了两件事:
  1) SSML 语气: 按标点切小句, 逐句微调语速/音高, 句间插停顿 —— 破坏机械的平铺直叙;
  2) 拟人化 DSP: 轻微颤音(去平板) + 短房间反射(去干涩) + 频响润色(去刺耳)。
"""
import math
import os
import re
import subprocess
import wave

import numpy as np

from . import config as C

SR = 44100

VOICE_EDGE = "zh-CN-XiaoyiNeural"          # 卡通 / 活泼
VOICE_ONECORE = "Yaoyao"                   # 本地 WinRT 女声(比 Huihui Desktop 新)
VOICE_SAPI = "Microsoft Huihui Desktop"
EDGE_RATE = "+6%"
EDGE_PITCH = "+20Hz"
GTTS_TEMPO = 1.12                          # 谷歌 TTS 语速偏慢, 用 atempo 提一点(不变调)
SAPI_RATE = 1
PITCH_BASE = 12                            # SSML 基础音高提升(卡通感)

# --- 阿里云百炼 / 千问 TTS ---
QWEN_MODEL = "qwen3-tts-flash"             # 千问语音合成(实测可用)
QWEN_VOICE = "Cherry"                      # 千问音色: 芊悦(阳光亲切), 科普讲解; 见 QWEN_VOICES
QWEN_PATH = "/services/aigc/multimodal-generation/generation"
QWEN_DEFAULT_BASE = "https://dashscope.aliyuncs.com/api/v1"
QWEN_CFG_FILE = os.path.join(C.CACHE, "aliyun.json")
QWEN_KEY_ENV = "DASHSCOPE_API_KEY"
QWEN_BASE_ENV = "DASHSCOPE_BASE_URL"
QWEN_MODELS = ["qwen3-tts-flash", "qwen-tts", "qwen-tts-latest"]
# 百炼官方中文音色(适合鲸鱼娘的排在前面)
QWEN_VOICES = ["Chelsie", "Cherry", "Serena", "Ethan", "Jada", "Sunny", "Kiki", "Dylan"]
QWEN_VOICE_NOTE = {"Chelsie": "千雪 · 二次元少女音", "Cherry": "芊悦 · 阳光亲切女声",
                   "Serena": "苏瑶 · 温柔女声", "Ethan": "晨煦 · 阳光男声",
                   "Jada": "阿珍 · 上海话", "Sunny": "晴儿 · 四川话",
                   "Kiki": "Kiki · 俏皮女声", "Dylan": "Dylan · 北京话"}

_TTS_CACHE: dict[str, tuple[np.ndarray, float]] = {}
_ENGINE: str | None = None
VOICE_DIR = os.path.join(C.ROOT, "voice")           # 自备录音放这里: hook.wav / research.wav ...


# --------------------------------------------------------------------------
# SSML: 逐句语气
# --------------------------------------------------------------------------
_CLAUSE = re.compile(r"[^，。！？；：、,.!?;:]+[，。！？；：、,.!?;:]?")


def prosody_ssml(text: str, pitch_base: int = PITCH_BASE, rate_base: float = 1.0) -> str:
    """把小句拆开, 分别给语速/音高, 并在标点处插停顿。"""
    clauses = [c for c in _CLAUSE.findall(text) if c.strip()]
    if not clauses:
        clauses = [text]
    n = len(clauses)
    body = []
    for i, c in enumerate(clauses):
        end = c.rstrip()[-1:]
        p = pitch_base
        if i == 0:
            p += 3                                   # 起句稍扬
        if i == n - 1 and end in "？?":
            p += 7                                   # 问句尾巴挑起来
        elif i == n - 1:
            p -= 2                                   # 陈述句收尾放下
        elif i == n - 2 and end in "，,":
            p += 2
        r = rate_base * (1.06 if len(c) <= 6 else 1.0)
        body.append(f'<prosody rate="{r:.2f}" pitch="{p:+d}%">{c}</prosody>')
        if i < n - 1:
            body.append(f'<break time="{210 if end in "。！？.!?" else 120}ms"/>')
    return ('<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xml:lang="zh-CN">{"".join(body)}</speak>')


# --------------------------------------------------------------------------
# 拟人化 DSP
# --------------------------------------------------------------------------
def _eq(y: np.ndarray) -> np.ndarray:
    """暖化低频、压掉 3.2k 的齿音毛刺、补一点空气感。"""
    n = len(y)
    if n < 512:
        return y
    Y = np.fft.rfft(y)
    f = np.fft.rfftfreq(n, 1 / SR)
    g = np.ones_like(f)
    g *= 1.0 + 0.34 * np.exp(-((f - 200) / 170) ** 2)
    g *= 1.0 - 0.30 * np.exp(-((f - 3200) / 900) ** 2)
    g *= 1.0 + 0.14 * np.exp(-((f - 7200) / 2200) ** 2)
    return np.fft.irfft(Y * g, n).astype(np.float32)


def _vibrato(y: np.ndarray, depth: float = 0.0035, hz: float = 4.6) -> np.ndarray:
    """极浅的时间轴调制 -> 音高有自然微抖(时长变化 <0.5%, 听不出来)。"""
    n = len(y)
    if n < 256:
        return y
    t = np.arange(n, dtype=np.float32) / SR
    warp = 1.0 + depth * np.sin(2 * math.pi * hz * t)
    pos = np.cumsum(warp)
    pos = (pos - pos[0]) / max(1e-6, pos[-1] - pos[0]) * (n - 1)
    return np.interp(pos, np.arange(n), y).astype(np.float32)


def _room(y: np.ndarray) -> np.ndarray:
    """几个早期反射, 去掉"贴脸干声"的机械感。"""
    out = y.copy()
    gain_sum = 0.0
    for d, g in ((0.011, 0.26), (0.017, 0.19), (0.029, 0.13), (0.043, 0.085), (0.061, 0.05)):
        k = int(d * SR)
        if k < len(y):
            out[k:] += y[:-k] * g
            gain_sum += g
    return (out / (1.0 + gain_sum * 0.5)).astype(np.float32)


def humanize(y: np.ndarray, strength: float = 1.0) -> np.ndarray:
    if strength <= 0:
        return y
    y = _eq(_vibrato(y, depth=0.0035 * strength))
    y = _room(y)
    peak = float(np.abs(y).max()) or 1.0
    return (y * (0.92 / peak) if peak > 0.92 else y).astype(np.float32)


# --------------------------------------------------------------------------
# 各引擎
# --------------------------------------------------------------------------
def _pick_engine(engine: str | None) -> str:
    global _ENGINE
    if engine:
        return engine
    if _ENGINE:
        return _ENGINE
    _ENGINE = "auto"
    return _ENGINE


def _decode_media(path: str, tempo: float = 1.0) -> np.ndarray:
    """任意音频 -> 44.1k 单声道 float(借 ffmpeg 解码, tempo 用 atempo 变速不变调)。"""
    import tempfile
    from imageio_ffmpeg import get_ffmpeg_exe
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "d.wav")
        cmd = [get_ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", "-i", path]
        if abs(tempo - 1.0) > 0.001:
            cmd += ["-filter:a", f"atempo={tempo:.4f}"]
        cmd += ["-ac", "1", "-ar", str(SR), out]
        subprocess.run(cmd, check=True)
        with wave.open(out, "rb") as w:
            raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def _edge_tts(text: str, voice: str, rate: str, pitch: str, path: str):
    import asyncio

    import edge_tts

    async def go():
        await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(path)
    asyncio.run(go())


def _gtts_tts(text: str, path: str, slow: bool = False):
    """Google 翻译的 TTS(神经网络, 中文自然度远好于本地拼接音)。"""
    from gtts import gTTS
    gTTS(text, lang="zh-CN", slow=slow).save(path)


def qwen_config() -> tuple[str | None, str]:
    """读百炼配置: (api_key, base_url)。
    优先环境变量, 其次 .cache/aliyun.json(由 tools/aliyun_key.py 从控制台抓取)。
    注意: 控制台提示 dashscope.aliyuncs.com 自 2026-09-30 起进入维护, 业务空间专属域名更稳。
    """
    key = os.environ.get(QWEN_KEY_ENV, "").strip()
    base = os.environ.get(QWEN_BASE_ENV, "").strip()
    if os.path.exists(QWEN_CFG_FILE):
        try:
            import json
            cfg = json.load(open(QWEN_CFG_FILE, encoding="utf-8"))
            key = key or (cfg.get("api_key") or "").strip()
            base = base or (cfg.get("base_url") or "").strip()
        except Exception:
            pass
    return key or None, (base or QWEN_DEFAULT_BASE).rstrip("/")


def qwen_key() -> str | None:
    return qwen_config()[0]


def _qwen_tts(text: str, path: str, model: str = QWEN_MODEL, voice: str = QWEN_VOICE,
              key: str | None = None, base: str | None = None,
              language_type: str = "Chinese"):
    """调用阿里云百炼的千问语音合成, 拿到音频 URL 后下载。"""
    import requests
    key, base = key or None, base or None
    if not key:
        key, base = qwen_config()
    base = base or QWEN_DEFAULT_BASE
    if not key:
        raise RuntimeError("没有百炼 API-KEY(环境变量 DASHSCOPE_API_KEY 或 .cache/aliyun.json)")
    body = {"model": model,
            "input": {"text": text, "voice": voice, "language_type": language_type}}
    r = requests.post(base + QWEN_PATH, timeout=180,
                      headers={"Authorization": f"Bearer {key}",
                               "Content-Type": "application/json"},
                      json=body)
    if r.status_code != 200:
        raise RuntimeError(f"qwen-tts HTTP {r.status_code}: {r.text[:300]}")
    j = r.json()
    audio = (j.get("output") or {}).get("audio") or {}
    url = audio.get("url")
    if not url:
        raise RuntimeError(f"qwen-tts 返回里没有音频 URL: {str(j)[:300]}")
    data = requests.get(url, timeout=180).content
    if len(data) < 1000:
        raise RuntimeError(f"qwen-tts 音频过小: {len(data)} 字节")
    with open(path, "wb") as fh:
        fh.write(data)
    return {"model": model, "voice": voice, "bytes": len(data),
            "usage": j.get("usage"), "request_id": j.get("request_id")}


_ONECORE_PS = r"""
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
  $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($t, $rt) {
  $m = $asTaskGeneric.MakeGenericMethod($rt)
  $task = $m.Invoke($null, @($t)); $task.Wait(-1) | Out-Null; $task.Result
}
[Windows.Media.SpeechSynthesis.SpeechSynthesizer,Windows.Media.SpeechSynthesis,ContentType=WindowsRuntime] | Out-Null
$synth = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
$voice = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices |
         Where-Object { $_.DisplayName -like "*$env:DSH_VOICE*" } | Select-Object -First 1
if (-not $voice) { throw "找不到语音 $env:DSH_VOICE" }
$synth.Voice = $voice
$stream = Await ($synth.SynthesizeSsmlToStreamAsync($env:DSH_SSML)) ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
$net = [System.IO.WindowsRuntimeStreamExtensions]::AsStreamForRead($stream)
$fs = [IO.File]::Create($env:DSH_OUT)
$net.CopyTo($fs); $fs.Close(); $stream.Dispose()
"""


def _onecore_tts(ssml: str, voice: str, path: str):
    import base64
    env = dict(os.environ, DSH_VOICE=voice, DSH_SSML=ssml, DSH_OUT=path)
    enc = base64.b64encode(_ONECORE_PS.encode("utf-16-le")).decode("ascii")
    p = subprocess.run(["powershell.exe", "-NoProfile", "-EncodedCommand", enc],
                       capture_output=True, env=env)
    if p.returncode != 0 or not os.path.exists(path) or os.path.getsize(path) < 2000:
        raise RuntimeError("OneCore TTS 失败: "
                           + (p.stderr.decode("utf-8", "ignore")[:300]
                              or p.stdout.decode("utf-8", "ignore")[:300]))


def _ps_quote(s: str) -> str:
    return s.replace("'", "''")


def _sapi_tts(text: str, voice: str, rate: int, path: str):
    ps = (
        "$ErrorActionPreference='Stop';"
        "Add-Type -AssemblyName System.Speech;"
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        f"$s.SelectVoice('{voice}');"
        f"$s.Rate={rate};"
        "$fmt=$null;"
        "try{$fmt=New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo("
        f"{SR},[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,"
        "[System.Speech.AudioFormat.AudioChannel]::Mono)}catch{};"
        f"if($fmt){{$s.SetOutputToWaveFile('{_ps_quote(path)}',$fmt)}}"
        f"else{{$s.SetOutputToWaveFile('{_ps_quote(path)}')}};"
        f"$s.SpeakSsml('{_ps_quote(text)}');"
        "$s.Dispose();"
    )
    p = subprocess.run(["powershell", "-NoProfile", "-EncodedCommand", _b64_utf16le(ps)],
                       capture_output=True)
    if p.returncode != 0 or not os.path.exists(path):
        msg = p.stderr.decode("utf-8", "ignore") or p.stdout.decode("utf-8", "ignore")
        raise RuntimeError(f"SAPI TTS 失败: {msg[:300]}")


def _read_wav_mono(path: str) -> np.ndarray:
    with wave.open(path, "rb") as w:
        ch, sw, fr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if sw != 2:
        raise RuntimeError(f"只支持 16bit PCM, 实际 {sw*8}bit")
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch == 2:
        a = a.reshape(-1, 2).mean(axis=1)
    if fr != SR:
        idx = np.linspace(0, len(a) - 1, int(len(a) * SR / fr))
        a = np.interp(idx, np.arange(len(a)), a).astype(np.float32)
    return a


# --------------------------------------------------------------------------
# 对外接口
# --------------------------------------------------------------------------
def tts(text: str, voice: str | None = None, rate=None, pitch=None,
        engine: str | None = None, humanize_voice: bool | None = None, ssml: bool = True,
        tempo: float | None = None, tag: str | None = None,
        cache_dir=None) -> tuple[np.ndarray, float]:
    """生成一句中文旁白, 返回 (波形, 时长)。

    中文要么内嵌进 -EncodedCommand, 要么交给库的 Python API —— 绝不能走 PowerShell 的 stdin
    (会按 GBK 解码 UTF-8 字节, 合成出来全是听不懂的乱码怪音)。
    tag: 自备录音(`voice/<tag>.wav`)的文件名, 给了就优先用它。
    """
    eng = _pick_engine(engine)
    # 1) 自备录音优先
    if tag and os.path.exists(os.path.join(VOICE_DIR, tag + ".wav")):
        eng, voice = "file", os.path.join(VOICE_DIR, tag + ".wav")
    elif eng == "auto":
        if qwen_key():
            eng = "qwen"                       # 有百炼 key 就用千问语音(音质最好)
        elif _edge_available():
            eng = "edge"
        elif _gtts_available():
            eng = "gtts"
        else:
            eng = "onecore"
    if eng == "qwen":
        voice = voice or QWEN_VOICE
    elif eng == "edge":
        voice = voice or VOICE_EDGE
        rate = rate or EDGE_RATE
        pitch = pitch or EDGE_PITCH
    elif eng == "gtts":
        voice = voice or "zh-CN"
    elif eng == "onecore":
        voice = voice or VOICE_ONECORE
        rate = 1.0 if rate is None else rate
        pitch = PITCH_BASE if pitch is None else pitch
    elif eng == "sapi":
        voice = voice or VOICE_SAPI
        rate = SAPI_RATE if rate is None else rate
    if humanize_voice is None:
        humanize_voice = eng in ("onecore", "sapi")   # 只有拼接式本地音需要拟人化处理
    if tempo is None:
        tempo = GTTS_TEMPO if eng == "gtts" else 1.0
    model = QWEN_MODEL if eng == "qwen" else "-"
    key = (f"{eng}|{model}|{voice}|{rate}|{pitch}|{int(humanize_voice)}|{int(ssml)}"
           f"|{tempo:.4f}|{text}")
    if key in _TTS_CACHE:
        return _TTS_CACHE[key]
    cache_dir = cache_dir or os.path.join(C.CACHE, "tts")
    os.makedirs(cache_dir, exist_ok=True)
    import hashlib
    stem = hashlib.md5(key.encode("utf-8")).hexdigest()
    npy = os.path.join(cache_dir, stem + ".npy")
    if os.path.exists(npy):
        a = np.load(npy)
    else:
        net = eng in ("edge", "gtts", "qwen")
        raw = os.path.join(cache_dir, stem + (".mp3" if eng in ("edge", "gtts") else ".wav"))
        if os.path.exists(raw) and os.path.getsize(raw) < 1024:
            os.remove(raw)                      # 上次合成失败留下的空文件
        if eng == "file":
            a = _decode_media(voice)
        else:
            if not os.path.exists(raw):
                if ssml:
                    marked = prosody_ssml(
                        text,
                        int(pitch) if isinstance(pitch, (int, float)) else PITCH_BASE,
                        float(rate) if isinstance(rate, (int, float)) else 1.0)
                else:
                    marked = (f'<speak version="1.0" '
                              f'xmlns="http://www.w3.org/2001/10/synthesis" '
                              f'xml:lang="zh-CN">{text}</speak>')
                try:
                    if eng == "qwen":
                        _qwen_tts(text, raw, model=model, voice=voice)
                    elif eng == "edge":
                        _edge_tts(text, voice, rate, pitch, raw)
                    elif eng == "gtts":
                        _gtts_tts(text, raw, slow=bool(rate and rate == "slow"))
                    elif eng == "onecore":
                        _onecore_tts(marked, voice, raw)
                    else:
                        _sapi_tts(marked, voice, int(rate), raw)
                except Exception as e:
                    if os.path.exists(raw) and os.path.getsize(raw) < 1024:
                        os.remove(raw)
                    fallback = {"qwen": "gtts" if _gtts_available() else "onecore",
                                "edge": "gtts", "gtts": "onecore"}.get(eng)
                    if fallback:
                        global _ENGINE
                        _ENGINE = fallback       # 记住失败, 后面几句不再试
                        print(f"  [旁白] {eng} 不可用({type(e).__name__}), 改用 {fallback}")
                        return tts(text, engine=fallback, humanize_voice=humanize_voice,
                                   ssml=ssml, tag=tag, cache_dir=cache_dir)
                    raise
            a = (_decode_media(raw, tempo) if net else _read_wav_mono(raw))
        # 去首尾静音
        thr = 0.012
        nz = np.where(np.abs(a) > thr)[0]
        if len(nz):
            a = a[max(0, nz[0] - int(0.03 * SR)):min(len(a), nz[-1] + int(0.10 * SR))]
        if humanize_voice:
            a = humanize(a)
        np.save(npy, a)
    _TTS_CACHE[key] = (a, len(a) / SR)
    return _TTS_CACHE[key]


def _edge_available() -> bool:
    global _ENGINE
    if _ENGINE in ("onecore", "sapi", "file", "gtts"):
        return False
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        return False
    return True


def _gtts_available() -> bool:
    global _ENGINE
    if _ENGINE in ("onecore", "sapi", "file"):
        return False
    try:
        import gtts  # noqa: F401
    except ImportError:
        return False
    return True


def _b64_utf16le(s: str) -> str:
    import base64
    return base64.b64encode(s.encode("utf-16-le")).decode("ascii")


# --------------------------------------------------------------------------
# 芯片音乐音效(BGM / SFX) 见文件下半部分
# --------------------------------------------------------------------------

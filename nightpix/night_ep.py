# -*- coding: utf-8 -*-
"""《深夜效应》时间轴 + 文案 + 混音。

时长账(实测口径): 千问 qwen3-tts-flash 中文旁白约 5.1 字/秒;
每段 LEAD 1.10 + TAIL 1.80 = 2.9 s, 8 段 = 23.2 s; hook 追加片名卡 3.0 s;
外加结尾卡 outro 3.4 s。目标 178±8 s -> 旁白 ~150 s -> 约 760-800 字。

改文案只需改 NARRATION, 画面节奏会自动跟着新配音时长重排。
"""
import numpy as np
import pygame

from . import audio
from . import config as C
from . import keeper as K
from . import music
from . import paint as P
from . import pixeltext as T
from . import props as R
from . import scenes as S
from . import tts as _tts

TITLE = "深夜效应"
SUBTITLE = "一到凌晨你就想哭，不是矫情，是刹车没了"
FILENAME = C.FILENAME

# 旁白(目标总字数 ~780)
NARRATION = {
    "hook": "凌晨两点半，你躺在床上，突然就想哭。"
            "白天那件小事，此刻重得像块石头。别急着说矫情，先记一个事实。",
    "research": "同一个你，下午三点看到「已读不回」，耸耸肩就过去了。"
                "凌晨两点半再看到，整个人都塌了。事情没变，变的是你的大脑。"
                "研究者让同一批人白天和深夜做同一套情绪测试，"
                "越到深夜，中性的事越容易被读成坏消息。",
    "brake": "原因之一，是刹车没了。大脑里管「忍住别冲动」的前额叶，"
             "白天电量满格。可它一整天都在消耗——做决定、压情绪、假装没事。"
             "到了深夜，它对情绪的刹车力掉到最低，"
             "而负责报警的杏仁核还在正常拉响。油门没变，刹车没了。",
    "curve": "所以你会有一种错觉：好像深夜的难过更真实。"
             "其实它只是更大声。有研究让同一个人重复做同一套情绪任务，"
             "情绪唤起的强度会随着时间往上走，"
             "而白天那种「还好」的平静，正在一点点往下掉。"
             "曲线交叉的那个点，大概在凌晨两点前后。"
             "也就是说，不是那件事变严重了，是你变敏感了。",
    "loop": "更麻烦的是反刍。白天有事推着你走，"
            "深夜安静下来，脑子开始把同一件事翻回来：我是不是说错话了，"
            "他为什么没回我，是不是我又不够好。"
            "你以为你在思考，其实你在原地打转——每个问题都像钩子，钩着下一个。"
            "心理学把这个过程叫反刍，它跟抑郁的关系，比那件事本身紧密得多。",
    "scroll": "这时候你摸到手机，等于给这个循环加柴。"
              "蓝光压住褪黑素，信息流一秒钟送你十件新的烦心事，"
              "下一条永远还有下一条。屏幕越亮，你越暗。",
    "tug": "然后你决定：必须马上睡着。这是最危险的一步。"
           "因为你开始努力睡觉，心跳快了，肌肉紧了，"
           "大脑判定你正在应对威胁——睡眠是放松的产物，"
           "你却在跟它拔河。你越用力，越赢不了。",
    "ending": "所以深夜的眼泪，从来不是证据，只是副作用。"
              "下一次，你可以只做三件事：把担心写下来，标上发生的概率；"
              "躺了二十分钟还睡不着，就离开床；"
              "以及最重要的一条——别在凌晨三点做决定。"
              "天亮以后，你会觉得还好。",
}
ORDER = ["hook", "research", "brake", "curve", "loop", "scroll", "tug", "ending"]

# 叙事段 -> 场景函数名(scenes.SCENES 的键)
SCENE_OF = {
    "hook": "ceiling_3am", "research": "two_yous", "brake": "brake_gauge",
    "curve": "emotion_curve", "loop": "rumination_loop", "scroll": "feed_glow",
    "tug": "sleep_tug", "ending": "dawn_three_moves",
}

STEP_LABEL = {
    "hook": "00 · 凌晨两点半", "research": "01 · 同一个你",
    "brake": "02 · 刹车没了", "curve": "03 · 情绪夜曲线",
    "loop": "04 · 反刍", "scroll": "05 · 屏幕在喂它",
    "tug": "06 · 越想睡越睡不着", "ending": "07 · 天亮了",
}
# 底部的"信息条"(不是游戏 HUD, 只做轻微索引)
KW = {
    "hook": "深夜效应", "research": "同一件事，两种感受",
    "brake": "前额叶 / 杏仁核", "curve": "情绪唤起 ↑ 平静 ↓",
    "loop": "反刍思维", "scroll": "蓝光 + 信息流",
    "tug": "睡眠努力悖论", "ending": "三件今天就能做的事",
}
HIGHLIGHT = ("深夜效应", "刹车", "反刍", "前额叶", "杏仁核", "蓝光",
             "写下来", "别硬躺", "别在凌晨三点做决定", "还好")


class Context:
    def __init__(self, lib=None):
        self.t = 0.0
        self.dt = 1 / C.FPS
        self.rnd = __import__("random").Random(20261014)
        self.keeper = K.Keeper()
        self.fx = P.NightFX(seed=11, grain=0.5, vignette=1.0)
        self.bg_room = P.make_gradient((14, 19, 34), (7, 10, 20))
        self.bg_ceil = P.make_gradient((10, 14, 26), (20, 26, 44))
        self.page_text = None
        self.page_chars = 0.0


class Timeline:
    LEAD = 1.10
    TAIL = 1.80
    TITLE_T = 3.00          # hook 前的片名卡
    OUTRO = 3.40
    SPEED = 30.0            # 字幕逐字速度(字/秒)
    GRAIN = True            # 胶片颗粒; 关掉可显著降码率(噪声对 x264 极贵)

    def __init__(self, tts=True):
        self.ctx = Context()
        self.tts_map = {}
        plan = []
        for key in ORDER:
            text = NARRATION[key]
            if tts:
                wav, d = _tts.tts(text, tag="night_" + key)
            else:
                wav, d = None, len(text) / 5.1
            self.tts_map[key] = (wav, d)
            dur = self.LEAD + d + self.TAIL + (self.TITLE_T if key == "hook" else 0.0)
            plan.append((key, dur, text))
        t, self.shots = 0.0, []
        for key, dur, text in plan:
            start_narr = self.TITLE_T if key == "hook" else self.LEAD
            self.shots.append(dict(key=key, scene=SCENE_OF[key], start=t, dur=dur, text=text,
                                   narr_at=t + start_narr, narr_dur=self.tts_map[key][1],
                                   _plan=None))
            t += dur
        self.duration = t
        self.ctx.bg_room = P.make_gradient((14, 19, 34), (7, 10, 20))
        for s in self.shots:                       # 字幕分页(与旁白时长对齐)
            s["_plan"] = _caption_plan(s["text"], s["narr_dur"])

    # ---- 查询 ----------------------------------------------------------
    def shot_at(self, t):
        for s in self.shots:
            if s["start"] <= t < s["start"] + s["dur"]:
                return s
        return self.shots[-1]

    def caption_for(self, shot, t):
        """返回当前该显示的字幕行(k_in 用 0..1 表示浮出进度)。"""
        el = t - shot["narr_at"]
        if el < 0:
            return None
        for (t0, t1, lines) in shot["_plan"]:
            if t0 <= el < t1 or (lines == shot["_plan"][-1][2] and el >= t0):
                return lines, min(1.0, (el - t0) / 0.22)
        return None

    # ---- 绘制 ----------------------------------------------------------
    def draw(self, surf, t):
        ctx = self.ctx
        ctx.t, ctx.dt = t, 1 / C.FPS
        shot = self.shot_at(t)
        lt = t - shot["start"]
        S.SCENES[shot["scene"]](surf, ctx, lt, shot["dur"])
        # 段落转场
        if lt < 0.35 and shot["key"] != ORDER[0]:
            P.bars_wipe(surf, 1 - lt / 0.35, C.VOID, bars=12)
        # 片名卡
        if shot["key"] == "hook" and lt < self.TITLE_T:
            k = min(1.0, lt / 0.6)
            P.dim(surf, max(0.15, 1 - k * 0.85))
            P.title_card(surf, TITLE, SUBTITLE, k)
        # 字幕
        if not (shot["key"] == "hook" and lt < self.TITLE_T):
            cap = self.caption_for(shot, t)
            if cap:
                lines, k_in = cap
                P.caption_band(surf, k_in)
                T.draw_lines(surf, lines, CX_MID, 292, color=C.BRIGHT,
                             size=C.FONT_SIZE_BIG, highlight=HIGHLIGHT, lh=22, alpha=int(255 * k_in))
        # 版面元素
        P.progress_line(surf, t / self.duration)
        if shot["key"] not in ("hook",):
            P.act_tag(surf, STEP_LABEL.get(shot["key"], ""))
        P.watermark(surf)
        T.draw(surf, KW.get(shot["key"], ""), CX_MID, 336, color=(96, 108, 136),
               size=C.FONT_SIZE_SMALL, anchor="midtop")
        if t >= self.duration:
            self._outro(surf, t)
        ctx.fx.apply(surf, t, grain=self.GRAIN, scan=True, vignette=True)
        return surf

    def _outro(self, surf, t):
        k = min(1.0, (t - self.duration) / 0.7)
        P.dim(surf, max(0.0, 1 - k * 0.9))
        T.draw(surf, "天亮以后，你会觉得还好", CX_MID, 150, color=C.BRIGHT,
               size=C.FONT_SIZE_TITLE, bold=True, anchor="center")
        if k > 0.4 and math_sin(t) > -0.3:
            T.draw(surf, "@提灯的人 · 深夜研究", CX_MID, 208, color=C.MUTE,
                   size=C.FONT_SIZE, anchor="center")
        T.draw(surf, "关注 · 下一期：《为什么你越想睡越睡不着》", CX_MID, 236,
               color=(110, 124, 156), size=C.FONT_SIZE_SMALL, anchor="center")

    # ---- 音频 ----------------------------------------------------------
    def events(self):
        ev = []
        for s in self.shots:
            ev.append((s["narr_at"] - 0.10, "page", 0.5))
            for (t0, _t1, _lines) in s["_plan"]:
                ev.append((s["narr_at"] + t0, "chime", 0.32))
            ev.append((s["start"] + 0.15, "amb_rain", 1.0))
            if s["key"] == "ending":
                for i in range(3):
                    ev.append((s["start"] + s["dur"] * (0.35 + 0.18 * i), "confirm", 0.6))
            if s["key"] == "tug":
                for i in range(6):
                    ev.append((s["start"] + 0.9 * i + 0.5, "pop", 0.18))
            ev.append((s["start"] + s["dur"] - self.TAIL * 0.5, "pop", 0.25))
        return ev

    def build_audio(self, path, music_gain=0.95, amb_gain=0.12, duck=0.35):
        dur = self.duration + self.OUTRO
        n = int(audio.SR * dur)
        voice = np.zeros(n, dtype=np.float32)
        amb = np.zeros(n, dtype=np.float32)
        for s in self.shots:
            wav, _ = self.tts_map.get(s["key"], (None, 0))
            if wav is not None:
                i0 = int(s["narr_at"] * audio.SR)
                voice[i0:i0 + len(wav)] += wav[:max(0, n - i0)]
        for t, name, gain in self.events():
            if name.startswith("amb_"):
                w = audio.ambience(name[4:], min(30.0, max(1.0, self.duration - t))) * (amb_gain * gain)
            else:
                w = audio.sfx(name) * (0.5 * gain)
            i0 = int(t * audio.SR)
            amb[i0:i0 + len(w)] += w[:max(0, n - i0)]
        # 旁白包络 -> BGM 闪避
        blk = int(0.01 * audio.SR)
        m = (n // blk) * blk
        env = np.abs(voice[:m]).reshape(-1, blk).max(axis=1)
        env = np.convolve(env, np.ones(14, dtype=np.float32) / 14, mode="same")
        env = np.clip(env * 4.0, 0, 1)
        env = np.repeat(env, blk)
        env = np.pad(env, (0, max(0, n - len(env))))
        bgm = music.night_song(self.shots, dur)[:n]
        mix = (np.stack([voice, voice], axis=1)
               + bgm * (music_gain * (1.0 - duck * env))[:, None]
               + np.stack([amb, amb], axis=1))
        mix = audio.compress(mix, thresh_db=-16.0, ratio=2.6, makeup_db=3.0)
        peak = float(np.max(np.abs(mix))) or 1.0
        mix = mix * (0.95 / peak)
        return audio.write_wav(path, mix)


CX_MID = C.VW // 2


def math_sin(t):
    import math
    return math.sin(t * 5.0)


def _split_clauses(text, max_chars):
    """按标点切条, 每条不超过 max_chars 字(给字幕用)。"""
    import re
    parts = re.findall(r"[^，。！？；：、,\.!?;:]+[，。！？；：、,\.!?;:」』”]?", text)
    out, cur = [], ""
    for p in parts:
        if len(cur) + len(p) <= max_chars:
            cur += p
        else:
            if cur:
                out.append(cur)
            cur = p
    if cur:
        out.append(cur)
    return out or [text]


def _wrap_lines(s, per_line=20):
    return [s[i:i + per_line] for i in range(0, len(s), per_line)] or [""]


def _caption_plan(text, dur, per_line=20):
    """按字数把一段旁白切成若干条字幕, 每条时长按字数占比分配。"""
    clauses = _split_clauses(text, per_line * 2)
    total = sum(len(c) for c in clauses) or 1
    plan, t0 = [], 0.0
    for c in clauses:
        d = dur * len(c) / total
        plan.append((t0, t0 + d, _wrap_lines(c, per_line)))
        t0 += d
    return plan


def make_timeline(tts=True) -> Timeline:
    return Timeline(tts=tts)

# -*- coding: utf-8 -*-
"""nightpix —— 《深夜效应》像素短片引擎。

与 whalegirl_studio 完全解耦: 只有字体引擎(pixeltext)与千问 TTS 多引擎降级链(tts)
是移植过来的成熟部件, 其余(配置/特效/形象/道具/场景/时间轴/配乐)为本片重写。
"""

__all__ = ["config", "pixeltext", "paint", "keeper", "props", "scenes",
           "night_ep", "audio", "music", "tts", "render"]

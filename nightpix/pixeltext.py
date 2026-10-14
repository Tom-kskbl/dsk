# -*- coding: utf-8 -*-
"""像素文字: 无抗锯齿 + 描边 + 中文折行 + 打字机 + 居中多行(字幕用)。"""
import functools

import pygame

from . import config as C

# 不能出现在行首 / 行尾的标点
NO_LINE_START = set("，。、；：？！）》」』%…·,.;:?!)]}")
NO_LINE_END = set("（《「『([{")


@functools.lru_cache(maxsize=64)
def get_font(size: int, bold: bool = False) -> pygame.font.Font:
    return pygame.font.Font(C.FONT_MAIN if bold else C.FONT_BODY, size)


def measure(s: str, size: int = C.FONT_SIZE, bold: bool = False) -> tuple[int, int]:
    return get_font(size, bold).size(s)


def line_h(size: int = C.FONT_SIZE) -> int:
    """行高(含行距)。"""
    return int(size * 1.45)


def _render(s: str, size: int, color, bold: bool, outline, shadow):
    f = get_font(size, bold)
    base = f.render(s, False, color)              # False = 无抗锯齿, 保住像素边
    if not outline and not shadow:
        return base
    ow = 1 if outline else 0
    pad = ow + (1 if shadow else 0)
    surf = pygame.Surface((base.get_width() + pad * 2, base.get_height() + pad * 2),
                          pygame.SRCALPHA)
    if shadow:
        surf.blit(f.render(s, False, C.SHADOW), (pad + 1, pad + 1))
    if outline:
        oc = f.render(s, False, outline if isinstance(outline, tuple) else C.SHADOW)
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            surf.blit(oc, (pad + dx, pad + dy))
    surf.blit(base, (pad, pad))
    return surf


def draw(surf: pygame.Surface, s: str, x: int, y: int, color=C.TEXT,
         size: int = C.FONT_SIZE, bold: bool = False, outline=C.SHADOW,
         shadow: bool = False, anchor: str = "topleft") -> pygame.Rect:
    img = _render(s, size, color, bold, outline, shadow)
    rect = img.get_rect(**{anchor: (x, y)})
    surf.blit(img, rect)
    return rect


def draw_lines(surf: pygame.Surface, lines: list[str], cx: int, cy: int,
               color=C.TEXT, size: int = C.FONT_SIZE_BIG, bold: bool = False,
               outline=C.SHADOW, lh: int | None = None, alpha: int = 255,
               highlight: tuple[str, ...] = (), hl_color=C.WARM) -> None:
    """多行居中(整体相对 cy 垂直居中)。highlight 里的词渲染成 hl_color。"""
    lh = lh or line_h(size)
    total = lh * len(lines)
    y0 = int(cy - total / 2)
    for i, ln in enumerate(lines):
        y = y0 + i * lh
        if highlight and any(k in ln for k in highlight):
            _draw_mixed(surf, ln, cx, y, color, size, bold, outline, alpha, highlight, hl_color)
        else:
            _blit_center(surf, _render(ln, size, color, bold, outline, False), cx, y, alpha)


def _blit_center(surf, img, cx, y, alpha=255):
    if alpha < 255:
        img = img.copy()
        img.set_alpha(alpha)
    surf.blit(img, img.get_rect(midtop=(cx, y)))


def _draw_mixed(surf, ln, cx, y, color, size, bold, outline, alpha, highlight, hl_color):
    """一行里混两种颜色(关键词高亮), 逐段渲染后整体居中。"""
    segs, cur, warm = [], "", False
    i = 0
    while i < len(ln):
        hit = False
        for kw in highlight:
            if ln.startswith(kw, i):
                if cur:
                    segs.append((cur, warm))
                    cur = ""
                segs.append((kw, True))
                i += len(kw)
                hit = True
                break
        if hit:
            continue
        cur += ln[i]
        i += 1
    if cur:
        segs.append((cur, warm))
    imgs = [_render(t, size, hl_color if w else color, bold, outline, False) for t, w in segs]
    total = sum(im.get_width() for im in imgs)
    x = cx - total // 2
    for im in imgs:
        if alpha < 255:
            im = im.copy()
            im.set_alpha(alpha)
        surf.blit(im, (x, y))
        x += im.get_width()


def wrap(s: str, max_w: int, size: int = C.FONT_SIZE, bold: bool = False) -> list[str]:
    """按像素宽度折行, 中文可断在任意字之间, 但要避开标点规则。"""
    f = get_font(size, bold)
    lines, cur = [], ""
    for ch in s:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        trial = cur + ch
        if f.size(trial)[0] <= max_w:
            cur = trial
        elif ch in NO_LINE_START and cur:
            lines.append(cur + ch)                # 标点挤在行尾
            cur = ""
        elif cur and cur[-1] in NO_LINE_END:
            lines.append(cur[:-1])
            cur = cur[-1] + ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines or [""]


def typewriter(page: str, chars: float, max_w: int, size: int = C.FONT_SIZE,
               bold: bool = False) -> list[str]:
    """按"已显示字数"返回分页行 —— 先全文折行, 再按字数截断。"""
    lines = wrap(page, max_w, size, bold)
    out, left = [], int(chars)
    for ln in lines:
        if left <= 0:
            break
        out.append(ln[:left])
        left -= len(ln)
    return out or [""]


def paginate(s: str, max_w: int, max_lines: int, size: int = C.FONT_SIZE,
             bold: bool = False) -> list[list[str]]:
    """把长台词切成若干"页", 每页最多 max_lines 行。"""
    lines = wrap(s, max_w, size, bold)
    return [lines[i:i + max_lines] for i in range(0, len(lines), max_lines)] or [[""]]

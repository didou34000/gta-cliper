"""Encadrés blancs façon TikTok (texte noir gras + emojis en couleur), rendus avec Pillow.

Style demandé le 18/11 : un titre en haut dans un encadré blanc aux coins arrondis, une
courte réaction en bas, pas de sous-titres. Polices fournies avec le bot (assets/fonts) :
TikTok Sans ExtraBold (OFL) et Noto Color Emoji (OFL)."""
from __future__ import annotations

import re
from pathlib import Path

from .subtitles import FONTS_DIR

TEXT_FONT = FONTS_DIR / "TikTokSans-ExtraBold.ttf"
EMOJI_FONT = FONTS_DIR / "NotoColorEmoji.ttf"
EMOJI_SIZE = 109  # seule taille des images couleur de Noto Color Emoji

# Emojis : pictogrammes + modificateurs (teinte, ZWJ, sélecteur de variante, drapeaux).
_EMOJI = re.compile(
    "(?:[\U0001F1E6-\U0001F1FF]{2}"
    "|[☀-➿\U0001F000-\U0001FAFF⬀-⯿⌀-⏿]"
    "[️\U0001F3FB-\U0001F3FF]*"
    "(?:‍[☀-➿\U0001F000-\U0001FAFF][️\U0001F3FB-\U0001F3FF]*)*)"
)


def _runs(text: str) -> list[tuple[bool, str]]:
    out, pos = [], 0
    for m in _EMOJI.finditer(text):
        if m.start() > pos:
            out.append((False, text[pos:m.start()]))
        out.append((True, m.group()))
        pos = m.end()
    if pos < len(text):
        out.append((False, text[pos:]))
    return [(e, t.replace("️", "") if not e else t) for e, t in out if t]


class _Painter:
    def __init__(self, size: int):
        from PIL import ImageFont
        self.size = size
        self.font = ImageFont.truetype(str(TEXT_FONT), size)
        try:
            self.efont = ImageFont.truetype(str(EMOJI_FONT), EMOJI_SIZE)
        except OSError:
            self.efont = None
        self.esz = int(size * 1.08)

    def emoji(self, e: str):
        from PIL import Image, ImageDraw
        if not self.efont:
            return None
        im = Image.new("RGBA", (EMOJI_SIZE * 3, EMOJI_SIZE * 2), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((0, 0), e, font=self.efont, embedded_color=True)
        box = im.getbbox()
        if not box:
            return None
        im = im.crop(box)
        h = self.esz
        return im.resize((max(1, int(im.width * h / im.height)), h), Image.LANCZOS)

    def width(self, text: str) -> float:
        from PIL import Image, ImageDraw
        d = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        w = 0.0
        for is_e, t in _runs(text):
            if is_e:
                im = self.emoji(t)
                w += (im.width if im else 0) + self.size * 0.06
            else:
                w += d.textlength(t, font=self.font)
        return w

    def draw(self, canvas, x: float, y: float, text: str) -> None:
        from PIL import ImageDraw
        d = ImageDraw.Draw(canvas)
        asc, desc = self.font.getmetrics()
        for is_e, t in _runs(text):
            if is_e:
                im = self.emoji(t)
                if im:
                    ey = int(y + (asc + desc - im.height) / 2 - self.size * 0.02)
                    canvas.alpha_composite(im, (int(x + self.size * 0.03), max(0, ey)))
                    x += im.width + self.size * 0.06
            else:
                d.text((x, y), t, font=self.font, fill=(0, 0, 0, 255))
                x += d.textlength(t, font=self.font)


def _wrap(p: _Painter, text: str, max_w: int) -> list[str]:
    lines, cur = [], ""
    for w in text.split():
        t = f"{cur} {w}".strip()
        if p.width(t) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def make_box(text: str, out: Path, *, size: int = 64, max_w: int = 900, max_lines: int = 3) -> Path | None:
    """Une ligne par « rangée » d'encadré blanc, chaque ligne centrée et à sa largeur (comme
    l'outil texte de TikTok). PNG transparent, bord à bord : à placer avec ffmpeg."""
    from PIL import Image, ImageDraw
    text = " ".join((text or "").split())
    if not text:
        return None
    for s in (size, int(size * 0.9), int(size * 0.8), int(size * 0.72)):
        p = _Painter(s)
        lines = _wrap(p, text, max_w - int(s * 0.7))
        if len(lines) <= max_lines:
            break
    pad_x, pad_y = int(s * 0.36), int(s * 0.14)
    asc, desc = p.font.getmetrics()
    lh = asc + desc + 2 * pad_y
    widths = [p.width(ln) + 2 * pad_x for ln in lines]
    W, H = int(max(widths)) + 4, lh * len(lines) + 4
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    r = int(s * 0.22)
    for k, (ln, w) in enumerate(zip(lines, widths)):
        x0, y0 = (W - w) / 2, 2 + k * lh
        # rangées collées : les coins se rejoignent (look « bulle » de TikTok)
        d.rounded_rectangle((x0, y0, x0 + w, y0 + lh + (r if k < len(lines) - 1 else 0)),
                            radius=r, fill=(255, 255, 255, 255))
    for k, (ln, w) in enumerate(zip(lines, widths)):
        p.draw(im, (W - w) / 2 + pad_x, 2 + k * lh + pad_y - int(s * 0.04), ln)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    return out

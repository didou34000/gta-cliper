"""Sous-titres animés mot par mot (style TikTok/Shorts), au format ASS pour libass.

Chaque ligne affiche un petit groupe de mots ; le mot en cours de prononciation
passe en couleur d'accent avec un léger "pop" (agrandissement rapide).
"""
from __future__ import annotations

from pathlib import Path

from .media import Word

FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
EM = 0.644  # taille réelle du cadratin Montserrat par point ASS (libass)


def _ts(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _esc(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


def group_words(words: list[Word], per_line: int = 3, max_gap: float = 0.6,
                size: int = 0, max_width: float = 0, uppercase: bool = True) -> list[list[Word]]:
    """Coupe en groupes courts ; coupe aussi sur ponctuation forte, silence, et dès que la
    ligne mesurée dépasserait max_width (le mot actif grossit de 15 %, on garde la marge)."""
    def wide(ws: list[Word]) -> float:
        t = " ".join(w.text.upper() if uppercase else w.text for w in ws)
        return text_width(t, size) * 1.15
    groups: list[list[Word]] = []
    cur: list[Word] = []
    for w in words:
        if cur and (len(cur) >= per_line or w.start - cur[-1].end > max_gap
                    or cur[-1].text[-1:] in ".?!,"
                    or (size and max_width and wide(cur + [w]) > max_width)):
            groups.append(cur)
            cur = []
        cur.append(w)
    if cur:
        groups.append(cur)
    return groups


def wrap_hook(text: str, max_chars: int = 18, size: int = 0, max_width: float = 880) -> list[str]:
    """Coupe l'accroche en 1 à 3 lignes (libass ne coupe pas avec WrapStyle 2).

    Avec size > 0, coupe selon la largeur réelle du texte dans la police ; sinon en caractères.
    """
    too_long = ((lambda t: text_width(t, size) > max_width) if size
                else (lambda t: len(t) > max_chars))
    words, lines, cur = text.split(), [], ""
    for w in words:
        nxt = f"{cur} {w}".strip()
        if cur and too_long(nxt):
            lines.append(cur)
            cur = w
        else:
            cur = nxt
    if cur:
        lines.append(cur)
    return lines[:3]


def text_width(text: str, size: int, font_file: str = "Montserrat-Black.ttf") -> float:
    """Largeur du texte en pixels (police fournie dans assets/fonts), estimation sinon."""
    try:
        from PIL import ImageFont
        # libass dimensionne la police sur sa hauteur de ligne Windows, pas sur le cadratin :
        # pour Montserrat, 1 point ASS = 0,644 px de cadratin (mesuré sur un rendu libass).
        return ImageFont.truetype(str(FONTS_DIR / font_file), 100).getlength(text) * size * EM / 100
    except Exception:
        return len(text) * size * 0.4


def rounded_box(w: float, h: float, r: float) -> str:
    """Rectangle aux coins arrondis en dessin ASS (\\p1), origine en haut à gauche."""
    w, h, r = round(w), round(h), round(min(r, h / 2, w / 2))
    k = round(r * 0.45)  # poignées de Bézier ≈ quart de cercle
    return (f"m {r} 0 l {w - r} 0 b {w - k} 0 {w} {k} {w} {r} "
            f"l {w} {h - r} b {w} {h - k} {w - k} {h} {w - r} {h} "
            f"l {r} {h} b {k} {h} 0 {h - k} 0 {h - r} "
            f"l 0 {r} b 0 {k} {k} 0 {r} 0")


def build_ass(words: list[Word], out: Path, *, width: int = 1080, height: int = 1920,
              font: str = "Montserrat Black", font_size: int = 92, per_line: int = 3,
              color: str = "&H00FFFFFF", highlight: str = "&H00A53EFF", outline: int = 6,
              outline_color: str = "&H003D0A2A", hook_bg: str = "&H00A53EFF",
              hook_fg: str = "&H00FFFFFF", max_width: int = 0,
              pos_y: int = 1350, uppercase: bool = True, time_offset: float = 0.0,
              hook: str = "", hook_y: int = 330, hook_size: int = 104,
              hook_duration: float = 0.0) -> Path:
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},{font_size},{color},{color},{outline_color},&H803D0A2A,0,0,0,0,100,100,1,0,1,{outline},4,5,60,60,0,1
Style: Hook,{font},{hook_size},{hook_fg},{hook_fg},&H00FFFFFF,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,60,60,0,1
Style: Box,{font},{hook_size},{hook_bg},{hook_bg},{hook_bg},&H50000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    cx = width // 2
    if hook and hook_duration > 0:
        # Accroche en haut, façon titre TikTok/CapCut : texte noir, un bandeau blanc
        # aux coins arrondis par ligne (largeur ajustée au texte), visible tout le clip.
        rows = wrap_hook(_esc(hook.upper()), size=hook_size)
        em = hook_size * EM
        box_h = int(em * 1.5)
        step = box_h - 2  # les bandeaux se touchent, comme dans CapCut
        pad = int(em * 0.5)
        y0 = hook_y - step * (len(rows) - 1) // 2
        fade = "\\fad(150,0)"
        for k, row in enumerate(rows):
            y = y0 + k * step
            w = text_width(row, hook_size) + 2 * pad
            x = cx - w / 2
            lines.append(
                f"Dialogue: 1,{_ts(0)},{_ts(hook_duration)},Box,,0,0,0,,"
                "{\\an7\\pos(" + f"{x:.0f},{y - box_h / 2:.0f}" + ")" + fade + "\\p1}"
                + rounded_box(w, box_h, box_h * 0.32) + "{\\p0}"
            )
            lines.append(
                f"Dialogue: 2,{_ts(0)},{_ts(hook_duration)},Hook,,0,0,0,,"
                "{\\an5\\pos(" + f"{cx},{y + 2}" + ")" + fade + "}" + row
            )
    max_w = max_width or int(width * 0.84)  # ~8 % de marge de chaque côté
    for g in group_words(words, per_line, size=font_size, max_width=max_w, uppercase=uppercase):
        texts = [_esc(w.text.upper() if uppercase else w.text) for w in g]
        # Un mot seul trop long (ex. « INCROYABLEMENT ») : on réduit la taille de ce groupe.
        need = text_width(" ".join(texts), font_size) * 1.15
        fs = "" if need <= max_w else f"\\fs{int(font_size * max_w / need)}"
        g_end = g[-1].end
        for i, w in enumerate(g):
            # Le mot i est actif de son début jusqu'au début du mot suivant (pas de trou).
            start = w.start
            end = g[i + 1].start if i + 1 < len(g) else max(g_end, w.start + 0.15)
            parts = []
            for j, t in enumerate(texts):
                if j == i:
                    parts.append(
                        "{\\c" + highlight + "&\\fscx108\\fscy108"
                        "\\t(0,80,\\fscx115\\fscy115)\\t(80,160,\\fscx108\\fscy108)}"
                        + t + "{\\c" + color + "&\\fscx100\\fscy100}"
                    )
                else:
                    parts.append(t)
            # Apparition du groupe : petit pop sur le premier mot seulement.
            intro = "\\fad(40,0)" if i == 0 else ""
            text = "{\\an5\\pos(" + f"{cx},{pos_y}" + ")" + intro + fs + "}" + " ".join(parts)
            lines.append(
                f"Dialogue: 0,{_ts(start - time_offset)},{_ts(end - time_offset)},Cap,,0,0,0,,{text}"
            )
    out.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return out

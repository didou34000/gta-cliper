"""Sous-titres animés mot par mot (style TikTok/Shorts), au format ASS pour libass.

Chaque ligne affiche un petit groupe de mots ; le mot en cours de prononciation
passe en couleur d'accent avec un léger "pop" (agrandissement rapide).
"""
from __future__ import annotations

from pathlib import Path

from .media import Word


def _ts(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _esc(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


def group_words(words: list[Word], per_line: int = 3, max_gap: float = 0.6) -> list[list[Word]]:
    """Coupe en groupes courts ; coupe aussi sur ponctuation forte ou silence."""
    groups: list[list[Word]] = []
    cur: list[Word] = []
    for w in words:
        if cur and (len(cur) >= per_line or w.start - cur[-1].end > max_gap
                    or cur[-1].text[-1:] in ".?!,"):
            groups.append(cur)
            cur = []
        cur.append(w)
    if cur:
        groups.append(cur)
    return groups


def wrap_hook(text: str, max_chars: int = 18) -> list[str]:
    """Coupe l'accroche en 1 à 3 lignes équilibrées (libass ne coupe pas avec WrapStyle 2)."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines[:3]


def build_ass(words: list[Word], out: Path, *, width: int = 1080, height: int = 1920,
              font: str = "Montserrat ExtraBold", font_size: int = 92, per_line: int = 3,
              color: str = "&H00FFFFFF", highlight: str = "&H0000E1FF", outline: int = 6,
              pos_y: int = 1350, uppercase: bool = True, time_offset: float = 0.0,
              hook: str = "", hook_y: int = 330, hook_size: int = 76,
              hook_duration: float = 0.0) -> Path:
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},{font_size},{color},{color},&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{outline},3,5,60,60,0,1
Style: Hook,{font},{hook_size},&H00000000,&H00000000,&H00FFFFFF,&H64000000,-1,0,0,0,100,100,0,0,3,18,0,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    cx = width // 2
    if hook and hook_duration > 0:
        # Accroche en haut : texte noir sur bandeau blanc, une ligne de bandeau par ligne
        # de texte (comme les titres TikTok), visible pendant tout le clip.
        rows = wrap_hook(_esc(hook.upper()))
        step = int(hook_size * 1.32)
        y0 = hook_y - step * (len(rows) - 1) // 2
        for k, row in enumerate(rows):
            lines.append(
                f"Dialogue: 1,{_ts(0)},{_ts(hook_duration)},Hook,,0,0,0,,"
                "{\\an5\\pos(" + f"{cx},{y0 + k * step}" + ")\\fad(150,0)}" + row
            )
    for g in group_words(words, per_line):
        texts = [_esc(w.text.upper() if uppercase else w.text) for w in g]
        g_end = g[-1].end
        for i, w in enumerate(g):
            # Le mot i est actif de son début jusqu'au début du mot suivant (pas de trou).
            start = w.start
            end = g[i + 1].start if i + 1 < len(g) else max(g_end, w.start + 0.15)
            parts = []
            for j, t in enumerate(texts):
                if j == i:
                    parts.append(
                        "{\\c" + highlight + "&\\fscx112\\fscy112"
                        "\\t(0,80,\\fscx122\\fscy122)\\t(80,160,\\fscx112\\fscy112)}"
                        + t + "{\\c" + color + "&\\fscx100\\fscy100}"
                    )
                else:
                    parts.append(t)
            # Apparition du groupe : petit pop sur le premier mot seulement.
            intro = "\\fad(40,0)" if i == 0 else ""
            text = "{\\an5\\pos(" + f"{cx},{pos_y}" + ")" + intro + "}" + " ".join(parts)
            lines.append(
                f"Dialogue: 0,{_ts(start - time_offset)},{_ts(end - time_offset)},Cap,,0,0,0,,{text}"
            )
    out.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return out

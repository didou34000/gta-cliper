"""Recadrage vertical 9:16 et incrustation des sous-titres avec ffmpeg."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def build_filter(layout: str, W: int, H: int, facecam: dict | None, ass_name: str) -> str:
    if facecam:
        fx, fy, fw, fh = facecam["x"], facecam["y"], facecam["w"], facecam["h"]
        cam_h = int(W * fh / fw) // 2 * 2
        game_h = H - cam_h
        g = (
            f"[0:v]crop={fw}:{fh}:{fx}:{fy},scale={W}:{cam_h}[cam];"
            f"[0:v]scale=-2:{game_h},crop={W}:{game_h}[game];"
            f"[cam][game]vstack=inputs=2[v0]"
        )
    elif layout == "crop":
        g = f"[0:v]scale=-2:{H},crop={W}:{H}[v0]"
    else:  # blur
        g = (
            f"[0:v]split=2[a][b];"
            f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"boxblur=25:3,eq=brightness=-0.10[bg];"
            f"[b]scale={W}:-2[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[v0]"
        )
    return g + f";[v0]ass={ass_name}:fontsdir=fonts,setsar=1,format=yuv420p[v]"


def render_vertical(src: Path, ass: Path, out: Path, *, width: int = 1080, height: int = 1920,
                    layout: str = "blur", facecam: dict | None = None,
                    start: float = 0.0, duration: float | None = None) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    workdir = ass.parent
    # ffmpeg échappe mal les chemins dans les filtres : on travaille avec des noms simples.
    ass_local = workdir / "subs.ass"
    if ass.resolve() != ass_local.resolve():
        shutil.copy(ass, ass_local)
    # Polices fournies avec le bot (Montserrat, style CapCut), lues par libass.
    from .subtitles import FONTS_DIR
    if FONTS_DIR.is_dir():
        shutil.copytree(FONTS_DIR, workdir / "fonts", dirs_exist_ok=True)
    fg = build_filter(layout, width, height, facecam, "subs.ass")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(src.resolve())]
    if duration:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += [
        "-filter_complex", fg, "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-r", "30",
        "-maxrate", "4M", "-bufsize", "8M",  # ~30 Mo par minute : tient dans le stockage gratuit
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
        str(out.resolve()),
    ]
    subprocess.run(cmd, check=True, cwd=workdir)
    return out


def extract_thumbnail(video: Path, out: Path, at: float = 1.0) -> Path:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", str(at),
                    "-i", str(video), "-frames:v", "1", "-q:v", "3", str(out)], check=True)
    return out


# ---------------------------------------------------------------------------
# Miniature (couverture) : image du moment fort + titre en gros + nom du compte.
# Gratuit (Pillow + ffmpeg). Les réseaux n'acceptent pas d'image de couverture envoyée à part :
# on l'incruste sur les 3 premières images de la vidéo, et Buffer dit à TikTok de prendre
# cette image comme couverture (thumbnailOffset). YouTube choisit lui-même sa miniature.
COVER_SECONDS = 0.1
PINK, VIOLET = (255, 62, 165), (42, 10, 61)


def _font(size: int, black: bool = True):
    from PIL import ImageFont
    from .subtitles import FONTS_DIR
    f = FONTS_DIR / ("Montserrat-Black.ttf" if black else "Montserrat-ExtraBold.ttf")
    try:
        return ImageFont.truetype(str(f), size)
    except OSError:
        return ImageFont.load_default()


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    lines, cur = [], ""
    for w in text.split():
        t = f"{cur} {w}".strip()
        if draw.textlength(t, font=font) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def make_cover(src: Path, at: float, title: str, handle: str, out: Path,
               W: int = 1080, H: int = 1920) -> Path:
    """Couverture 9:16 : fond flouté du moment fort, titre en majuscules sur bandeaux roses."""
    from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
    frame = out.with_suffix(".src.jpg")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{max(0, at):.2f}",
                    "-i", str(src), "-frames:v", "1", "-q:v", "2", str(frame)], check=True)
    im = Image.open(frame).convert("RGB")
    # fond : image agrandie, floutée et assombrie ; devant : l'image entière, centrée
    s = max(W / im.width, H / im.height)
    bg = im.resize((int(im.width * s) + 1, int(im.height * s) + 1)).crop((0, 0, W, H))
    bg = ImageEnhance.Brightness(bg.filter(ImageFilter.GaussianBlur(28))).enhance(0.55)
    fg = im.resize((W, int(im.height * W / im.width)))
    canvas = bg.copy()
    canvas.paste(fg, (0, (H - fg.height) // 2 + 120))
    d = ImageDraw.Draw(canvas)
    # titre : la plus grande taille qui tient en 5 lignes max
    text = " ".join(title.upper().split())
    for size in (118, 108, 98, 90, 82, 74, 66):
        font = _font(size)
        lines = _wrap(d, text, font, W - 140)
        if len(lines) <= 5:
            break
    lh = int(size * 1.22)
    y = 250
    for ln in lines:
        tw = d.textlength(ln, font=font)
        x = (W - tw) / 2
        d.rounded_rectangle((x - 26, y - 10, x + tw + 26, y + lh - 4), radius=18, fill=PINK)
        d.text((x, y), ln, font=font, fill="white", stroke_width=5, stroke_fill=VIOLET)
        y += lh + 8
    # nom du compte, en bas
    if handle:
        hf = _font(54, black=False)
        tw = d.textlength(handle, font=hf)
        d.rounded_rectangle(((W - tw) / 2 - 30, H - 300, (W + tw) / 2 + 30, H - 210), radius=45,
                            fill=(0, 0, 0))
        d.text(((W - tw) / 2, H - 290), handle, font=hf, fill="white")
    canvas.save(out, quality=92)
    frame.unlink(missing_ok=True)
    return out


def add_cover(video: Path, cover: Path, seconds: float = COVER_SECONDS) -> Path:
    """Incruste la couverture sur le tout début de la vidéo (3 images à 30 i/s)."""
    tmp = video.with_suffix(".cover.mp4")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(video),
                    "-i", str(cover), "-filter_complex",
                    f"[1:v]scale=iw:ih[c];[0:v][c]overlay=0:0:enable='lt(t,{seconds})',format=yuv420p[v]",
                    "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                    "-r", "30", "-maxrate", "4M", "-bufsize", "8M", "-c:a", "copy",
                    "-movflags", "+faststart", str(tmp)], check=True)
    tmp.replace(video)
    return video

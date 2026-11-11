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
    return g + f";[v0]ass={ass_name},setsar=1,format=yuv420p[v]"


def render_vertical(src: Path, ass: Path, out: Path, *, width: int = 1080, height: int = 1920,
                    layout: str = "blur", facecam: dict | None = None,
                    start: float = 0.0, duration: float | None = None) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    workdir = ass.parent
    # ffmpeg échappe mal les chemins dans les filtres : on travaille avec des noms simples.
    ass_local = workdir / "subs.ass"
    if ass.resolve() != ass_local.resolve():
        shutil.copy(ass, ass_local)
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

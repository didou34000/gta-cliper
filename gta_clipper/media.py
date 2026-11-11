"""Téléchargement (yt-dlp), transcription (faster-whisper) et outils ffmpeg."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path


def download(url: str, out: Path, start: float | None = None, end: float | None = None,
             max_mb: int = 400) -> Path:
    """Télécharge un clip Twitch, ou une section d'une VOD si start/end sont donnés."""
    import yt_dlp
    from yt_dlp.utils import download_range_func

    out.parent.mkdir(parents=True, exist_ok=True)
    opts = {
        "outtmpl": str(out.with_suffix("")) + ".%(ext)s",
        "format": "best[height<=1080]/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "noprogress": True,
        "max_filesize": max_mb * 1024 * 1024,  # garde-fou taille
    }
    if start is not None and end is not None:
        opts["download_ranges"] = download_range_func(None, [(start, end)])
        opts["force_keyframes_at_cuts"] = True
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = Path(ydl.prepare_filename(info))
    if path.suffix != ".mp4" and path.with_suffix(".mp4").exists():
        path = path.with_suffix(".mp4")
    if not path.exists():
        raise RuntimeError(f"Téléchargement refusé ou vide (taille max {max_mb} Mo)")
    return path


def probe_duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return float(json.loads(r.stdout)["format"]["duration"])


def probe_size(path: Path) -> tuple[int, int]:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height", "-of", "json", str(path)],
                       capture_output=True, text=True, check=True)
    s = json.loads(r.stdout)["streams"][0]
    return int(s["width"]), int(s["height"])


@dataclass
class Word:
    start: float
    end: float
    text: str


_whisper_model = None


def transcribe(path: Path, model: str = "large-v3", device: str = "auto",
               compute_type: str = "auto") -> list[Word]:
    """Transcription FR avec horodatage au mot (nécessaire pour les sous-titres animés)."""
    global _whisper_model
    from faster_whisper import WhisperModel

    if _whisper_model is None:
        _whisper_model = WhisperModel(model, device=device, compute_type=compute_type)
    segments, _ = _whisper_model.transcribe(
        str(path), language="fr", word_timestamps=True, vad_filter=True,
        condition_on_previous_text=False,
    )
    words: list[Word] = []
    for seg in segments:
        for w in seg.words or []:
            t = w.word.strip()
            if t:
                words.append(Word(start=float(w.start), end=float(w.end), text=t))
    return words


def save_words(words: list[Word], path: Path) -> None:
    path.write_text(json.dumps([asdict(w) for w in words], ensure_ascii=False, indent=1),
                    encoding="utf-8")


def load_words(path: Path) -> list[Word]:
    return [Word(**w) for w in json.loads(path.read_text(encoding="utf-8"))]


def transcript_text(words: list[Word]) -> str:
    return " ".join(w.text for w in words)

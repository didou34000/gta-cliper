"""Mode « lien YouTube », façon Opus Clip : on donne une vidéo longue, le bot trouve
lui-même les meilleurs moments et en fait des clips verticaux sous-titrés.

Étapes (les plus lourdes ne portent que sur les moments retenus) :
1. on télécharge uniquement le son de la vidéo (≈ 50 Mo par heure) ;
2. pics de volume (gratuit, calculé ici) : cris, rires, explosions ;
3. transcription rapide de toute la vidéo (Whisper « small », horodatée par phrase) ;
4. Claude lit la transcription + les pics et choisit les N meilleurs moments (20 à 60 s) ;
5. pour chaque moment, on télécharge seulement ce passage en vidéo, puis la chaîne
   habituelle : Whisper précis mot à mot, titre/accroche, montage 9:16, sous-titres roses.

YouTube bloque souvent les serveurs (GitHub Actions compris) : depuis un Mac ou un PC
à la maison, ça passe. Les cookies d'un compte YouTube (variable YT_COOKIES, contenu d'un
fichier cookies.txt) aident parfois depuis un serveur.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

log = logging.getLogger("gta_clipper")

YT_RE = re.compile(r"^https?://(www\.|m\.|music\.)?(youtube\.com/(watch\?|shorts/|live/)|youtu\.be/)",
                   re.I)


def is_youtube(url: str) -> bool:
    return bool(YT_RE.match((url or "").strip()))


class YouTubeBlocked(RuntimeError):
    """YouTube refuse le téléchargement (serveur repéré comme robot)."""


def _cookie_file() -> str | None:
    """YT_COOKIES = contenu d'un cookies.txt (format Netscape), ou chemin d'un fichier."""
    raw = (os.environ.get("YT_COOKIES") or "").strip()
    if not raw:
        return None
    if "\n" not in raw and Path(raw).exists():
        return raw
    p = Path("data/yt_cookies.txt")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(raw if raw.endswith("\n") else raw + "\n", encoding="utf-8")
    return str(p)


def ydl_opts(**extra) -> dict:
    """Options yt-dlp communes : cookies si fournis, solveur JavaScript (deno, ou node)."""
    opts: dict = {"quiet": True, "noprogress": True, "noplaylist": True}
    ck = _cookie_file()
    if ck:
        opts["cookiefile"] = ck
    from shutil import which
    if not which("deno") and which("node"):
        opts["js_runtimes"] = {"node": {}}
    opts.update(extra)
    return opts


def _wrap(e: Exception) -> Exception:
    s = str(e)
    if any(k in s for k in ("Sign in to confirm", "not a bot", "HTTP Error 403", "HTTP Error 429")):
        return YouTubeBlocked(
            "YouTube bloque le téléchargement depuis cette machine (protection anti-robot). "
            "Lance-le depuis ton Mac, ou ajoute des cookies YouTube (secret YT_COOKIES).")
    return e


def video_info(url: str) -> dict:
    import yt_dlp
    try:
        with yt_dlp.YoutubeDL(ydl_opts(skip_download=True)) as ydl:
            i = ydl.extract_info(url, download=False)
    except Exception as e:
        raise _wrap(e) from e
    return {"id": i.get("id", ""), "title": i.get("title", ""),
            "channel": i.get("channel") or i.get("uploader") or "",
            "duration": float(i.get("duration") or 0), "is_live": bool(i.get("is_live"))}


def download_audio(url: str, out: Path, max_seconds: float | None = None) -> Path:
    """Son seul (m4a/webm), éventuellement limité aux max_seconds premières secondes."""
    import yt_dlp
    from yt_dlp.utils import download_range_func
    out.parent.mkdir(parents=True, exist_ok=True)
    opts = ydl_opts(format="ba[abr<=160]/ba/b", outtmpl=str(out.with_suffix("")) + ".%(ext)s")
    if max_seconds:
        opts["download_ranges"] = download_range_func(None, [(0, max_seconds)])
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = Path(ydl.prepare_filename(info))
    except Exception as e:
        raise _wrap(e) from e
    if not path.exists():
        cands = sorted(out.parent.glob(out.stem + ".*"))
        if not cands:
            raise RuntimeError("Téléchargement du son vide")
        path = cands[0]
    return path


# --- 2. pics de volume -------------------------------------------------------

@dataclass
class Peak:
    t: float      # seconde du pic
    z: float      # force du pic par rapport aux 5 minutes autour


def loudness_peaks(samples, sr: int = 16000, max_n: int = 25, min_gap: float = 45.0) -> list[Peak]:
    """Moments où le son monte nettement au-dessus de son niveau local (cris, rires…)."""
    import numpy as np
    if samples is None or len(samples) < sr * 10:
        return []
    n = len(samples) // sr
    x = samples[: n * sr].reshape(n, sr)
    db = 20 * np.log10(np.sqrt((x.astype(np.float64) ** 2).mean(axis=1)) + 1e-6)
    # Lissage sur 3 s, puis comparaison au niveau des 5 minutes autour.
    k = np.ones(3) / 3
    sm = np.convolve(db, k, mode="same")
    ctx = 150
    pad = np.pad(sm, ctx, mode="edge")
    cs = np.cumsum(np.insert(pad, 0, 0))
    cs2 = np.cumsum(np.insert(pad ** 2, 0, 0))
    w = 2 * ctx + 1
    mu = (cs[w:] - cs[:-w]) / w
    sd = np.sqrt(np.maximum((cs2[w:] - cs2[:-w]) / w - mu ** 2, 1e-6))
    z = (sm - mu[:n]) / np.maximum(sd[:n], 1.5)
    order = np.argsort(-z)
    picked: list[Peak] = []
    for i in order:
        if z[i] < 1.5 or len(picked) >= max_n:
            break
        if all(abs(i - p.t) >= min_gap for p in picked):
            picked.append(Peak(t=float(i), z=round(float(z[i]), 2)))
    return sorted(picked, key=lambda p: p.t)


# --- 3. transcription rapide -------------------------------------------------

@dataclass
class Seg:
    start: float
    end: float
    text: str


_fast_model = None


def rough_transcript(samples, model: str = "small", device: str = "auto",
                     compute_type: str = "auto", prompt: str = "") -> list[Seg]:
    """Transcription de toute la vidéo, horodatée par phrase (rapide, pour choisir les moments)."""
    global _fast_model
    from faster_whisper import WhisperModel
    if _fast_model is None:
        _fast_model = WhisperModel(model, device=device, compute_type=compute_type)
    segs, _ = _fast_model.transcribe(samples, language="fr", vad_filter=True, beam_size=1,
                                     condition_on_previous_text=False,
                                     initial_prompt=prompt or None)
    return [Seg(float(s.start), float(s.end), s.text.strip()) for s in segs if s.text.strip()]


def _ts(t: float) -> str:
    t = int(t)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


# --- 4. choix des moments par Claude ----------------------------------------

SYSTEM = """Tu es monteur de clips courts (TikTok, YouTube Shorts, Reels) pour une page \
française. On te donne la transcription horodatée d'une longue vidéo (souvent un stream ou \
une vidéo gaming) et la liste des pics de volume (cris, rires, explosions).

Choisis les meilleurs moments à couper en clips verticaux :
- chaque clip dure entre 20 et 60 secondes et se comprend SANS le reste de la vidéo ;
- il commence juste avant l'action ou la phrase d'accroche (pas au milieu d'une phrase) et \
se termine sur la chute, la réaction ou la fin de l'idée ;
- privilégie : découverte marquante, action folle, fail, fou rire, rage, réplique culte, \
info surprenante, moment d'émotion. Un pic de volume aide mais ne suffit pas ;
- évite les passages calmes, menus, chargements, pubs/sponsors, intro et outro ;
- pas de chevauchement entre deux clips ;
- note chaque moment de 1 à 10 (potentiel viral), honnêtement : un moment moyen vaut 4-5.
Donne pour chacun le sujet concret en quelques mots (ex. "découvre les stations essence", \
"se fait braquer par un PNJ") et une raison courte."""


class Moment(BaseModel):
    start: float = Field(description="Début en secondes")
    end: float = Field(description="Fin en secondes")
    score: int = Field(description="Potentiel de 1 à 10")
    sujet: str = Field(description="Sujet concret du moment, 8 mots max")
    raison: str = Field(description="Pourquoi ça marche, 12 mots max")


class Moments(BaseModel):
    moments: list[Moment]


def pick_moments(segs: list[Seg], peaks: list[Peak], n: int, *, title: str = "",
                 channel: str = "", game: str = "", model: str = "claude-haiku-5-5",
                 duration: float = 0) -> list[dict]:
    """Demande à Claude les n meilleurs moments. Sans clé / en cas d'échec : pics de volume."""
    from .guard import Guard
    if os.environ.get("ANTHROPIC_API_KEY") and segs and Guard.get().allow_llm():
        lines = "\n".join(f"[{_ts(s.start)}-{_ts(s.end)}] {s.text}" for s in segs)
        pk = ", ".join(f"{_ts(p.t)} (force {p.z})" for p in peaks) or "aucun"
        msg = (f"Vidéo : « {title} » · chaîne : {channel or '?'} · jeu : {game or '?'} · "
               f"durée {_ts(duration)}.\nDonne les {n + 2} meilleurs moments, du meilleur au "
               f"moins bon (temps en secondes).\n\nPics de volume : {pk}\n\n"
               f"Transcription :\n{lines[:400_000]}")
        try:
            import anthropic
            client = anthropic.Anthropic(max_retries=2, timeout=180)
            resp = client.messages.parse(
                model=model, max_tokens=4000, system=SYSTEM,
                messages=[{"role": "user", "content": msg}], output_format=Moments)
            got = resp.parsed_output.moments if resp.parsed_output else []
            out = _clean([m.model_dump() for m in got], segs, duration)
            if out:
                return out[:n]
        except Exception as e:
            log.warning("Choix des moments par l'IA impossible : %s", e)
    # Repli gratuit : autour des plus gros pics de volume (le pic arrive souvent en fin d'action).
    best = sorted(peaks, key=lambda p: -p.z)
    raw = [{"start": p.t - 25, "end": p.t + 15, "score": 0, "sujet": "",
            "raison": f"pic de volume (force {p.z})"} for p in best]
    return _clean(raw, segs, duration)[:n]


def _clean(moments: list[dict], segs: list[Seg], duration: float) -> list[dict]:
    """Recale les bornes sur des débuts/fins de phrase, impose 20-60 s, retire les chevauchements."""
    out: list[dict] = []
    for m in moments:
        s, e = float(m["start"]), float(m["end"])
        if e <= s:
            continue
        starts = [g.start for g in segs if abs(g.start - s) <= 4]
        ends = [g.end for g in segs if abs(g.end - e) <= 4]
        if starts:
            s = min(starts, key=lambda x: abs(x - s))
        if ends:
            e = min(ends, key=lambda x: abs(x - e))
        s = max(0.0, s - 0.3)
        e = e + 0.5
        if e - s < 20:
            e = s + 20
        if e - s > 60:
            e = s + 60
        if duration:
            e = min(e, duration)
            s = max(0.0, min(s, e - 20))
        if any(not (e <= o["start"] or s >= o["end"]) for o in out):
            continue
        out.append({**m, "start": round(s, 2), "end": round(e, 2),
                    "score": max(0, min(10, int(m.get("score") or 0)))})
    return out

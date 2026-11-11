"""Orchestration : sources Twitch -> moments forts -> clip vertical sous-titré -> file de validation."""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import media, render, subtitles
from .highlights import chat_spikes
from .metadata import generate_metadata

log = logging.getLogger("gta_clipper")


def load_config(path: str | Path = "config.yaml") -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()[:60] or "clip"


def seen_ids(cfg: dict) -> set[str]:
    ids = set()
    for key in ("review", "approved", "rejected"):
        for meta in Path(cfg["paths"][key]).glob("*/meta.json"):
            ids.add(json.loads(meta.read_text(encoding="utf-8")).get("source_id", ""))
    return ids


def process_clip(cfg: dict, *, source_id: str, streamer_name: str, video: Path,
                 twitch_title: str = "", source_url: str = "", extra: dict | None = None,
                 skip_llm: bool = False, words: list | None = None) -> Path:
    """Prend une vidéo horizontale déjà téléchargée et produit un dossier prêt à valider."""
    rc, sc, wc = cfg["render"], cfg["subtitles"], cfg["whisper"]
    item_dir = Path(cfg["paths"]["review"]) / f"{datetime.now():%Y%m%d-%H%M%S}-{slug(source_id)}"
    item_dir.mkdir(parents=True, exist_ok=True)

    duration = min(media.probe_duration(video), float(rc.get("max_duration", 60)))

    if words is None:
        log.info("Transcription de %s", video.name)
        words = media.transcribe(video, wc["model"], wc["device"], wc["compute_type"])
    words = [w for w in words if w.start < duration]
    media.save_words(words, item_dir / "transcript.json")

    ass = subtitles.build_ass(
        words, item_dir / "subs.ass", width=rc["width"], height=rc["height"],
        font=sc["font"], font_size=sc["font_size"], per_line=sc["words_per_line"],
        color=sc["color"], highlight=sc["highlight_color"], outline=sc["outline"],
        pos_y=sc["position_y"], uppercase=sc["uppercase"],
    )
    out = item_dir / "clip.mp4"
    log.info("Rendu vertical -> %s", out)
    render.render_vertical(video, ass, out, width=rc["width"], height=rc["height"],
                           layout=rc["layout"], facecam=rc.get("facecam"), duration=duration)
    render.extract_thumbnail(out, item_dir / "thumb.jpg", at=min(1.5, duration / 2))

    text = media.transcript_text(words)
    if skip_llm:
        meta = {"title": f"{streamer_name} sur GTA 6", "alt_titles": [], "description": "",
                "hashtags": cfg["llm"]["base_hashtags"], "confidence": "low"}
    else:
        m = generate_metadata(streamer_name, text, twitch_title, cfg["llm"]["model"],
                              cfg["llm"]["base_hashtags"])
        meta = m.model_dump()

    meta.update({
        "source_id": source_id, "source_url": source_url, "streamer": streamer_name,
        "twitch_title": twitch_title, "duration": round(duration, 2),
        "transcript": text, "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(), **(extra or {}),
    })
    (item_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    return item_dir


def run(cfg: dict, skip_llm: bool = False, chat_dir: str | None = None) -> list[Path]:
    from .twitch import TwitchClient, fetch_chat_offsets_gql, load_chat_offsets

    tw = TwitchClient()
    game_id = tw.game_id(cfg["game_name"])
    if not game_id:
        log.warning("Jeu '%s' introuvable sur Twitch : aucun filtre par jeu.", cfg["game_name"])
    already = seen_ids(cfg)
    work = Path(cfg["paths"]["work"])
    produced: list[Path] = []

    for st in cfg["streamers"]:
        uid = tw.user_id(st["login"])
        if not uid:
            log.warning("Streamer introuvable : %s", st["login"])
            continue

        # 1) Clips viewers les plus vus
        clips = tw.top_clips(uid, cfg["lookback_hours"], game_id, cfg["min_clip_views"],
                             cfg["max_clips_per_streamer"])
        log.info("%s : %d clip(s) retenu(s)", st["name"], len(clips))
        for c in clips:
            sid = f"clip-{c.id}"
            if sid in already:
                continue
            try:
                video = media.download(c.url, work / sid / "source.mp4")
                produced.append(process_clip(
                    cfg, source_id=sid, streamer_name=st["name"], video=video,
                    twitch_title=c.title, source_url=c.url, skip_llm=skip_llm,
                    extra={"views": c.view_count, "kind": "twitch_clip"}))
                already.add(sid)
            except Exception:
                log.exception("Échec sur le clip %s", c.url)

        # 2) Pics de chat dans la dernière VOD (optionnel)
        vc = cfg.get("vod", {})
        if not vc.get("enabled"):
            continue
        for v in tw.recent_vods(uid, vc.get("max_vods_per_streamer", 1)):
            try:
                local = Path(chat_dir) / f"{v.id}.json" if chat_dir else None
                offsets = (load_chat_offsets(local) if local and local.exists()
                           else fetch_chat_offsets_gql(v.id))
            except Exception as e:
                log.warning("Chat indisponible pour la VOD %s : %s", v.id, e)
                continue
            hls = chat_spikes(offsets, v.duration_s, vc["window_seconds"], vc["min_zscore"],
                              vc["clip_before"], vc["clip_after"], vc["max_highlights_per_vod"])
            log.info("VOD %s : %d pic(s) de chat", v.id, len(hls))
            for h in hls:
                sid = f"vod-{v.id}-{int(h.start)}"
                if sid in already:
                    continue
                try:
                    video = media.download(v.url, work / sid / "source.mp4", h.start, h.end)
                    produced.append(process_clip(
                        cfg, source_id=sid, streamer_name=st["name"], video=video,
                        twitch_title=v.title, source_url=f"{v.url}?t={int(h.start)}s",
                        skip_llm=skip_llm,
                        extra={"kind": "vod_chat_spike", "chat_zscore": h.score}))
                    already.add(sid)
                except Exception:
                    log.exception("Échec sur le moment %s", sid)
    return produced

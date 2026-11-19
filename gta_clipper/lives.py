"""Mode « lives » (règle du 19/11 : « va voir sur les lives directement, et quand tu vois un
truc intéressant tu clipes, sur plusieurs streamers, on fait les clips nous-mêmes »).

Au lieu d'attendre les clips des viewers, le bot regarde lui-même les lives FR en cours sur
le jeu (les plus regardés), par tranches :
1. il prend la VOD du live en cours (Twitch l'enregistre pendant le live) ;
2. il télécharge le son de la dernière tranche pas encore lue (≈ 1 h) ;
3. pics de volume (cris, rires) + transcription rapide (Whisper small) ;
4. Claude lit la transcription et ne garde que les moments vraiment drôles (7/10 minimum) ;
5. chaque moment retenu est téléchargé en vidéo puis monté comme d'habitude (encadrés,
   sous-titres, note de clic, envoi au site, validation auto si ≥ 7).

La position lue est gardée dans R2 (lives/<vod>.json) : chaque passage reprend où le
précédent s'était arrêté, rien n'est lu deux fois.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from . import media
from .guard import Guard, LimitReached

log = logging.getLogger("gta_clipper")

LIVE_SYSTEM = """Tu es le meilleur clippeur TikTok FR. On te donne la transcription horodatée \
d'une tranche de live Twitch d'un streamer français qui joue à {game}, et les pics de volume \
(cris, rires, explosions).

Ton seul but : trouver les moments VRAIMENT DRÔLES ou complètement fous, ceux qu'on envoie à \
ses potes : fou rire, rage absurde, réplique culte, bug hilarant, situation WTF, panique \
ridicule, chute inattendue, clash entre potes, découverte qui choque.

Règles :
- chaque moment dure 20 à 60 secondes et se comprend SANS le reste du live ;
- il commence juste avant l'action ou la phrase d'accroche et finit sur la chute ou la réaction ;
- pas de chevauchement entre deux moments.

Note de 1 à 10, sois très exigeant (la plupart des passages valent 3 à 5) :
- 9-10 : on pleure de rire, réplique culte ou situation folle compréhensible sans contexte ;
- 7-8 : vraiment drôle ou surprenant, une vraie chute, ça marche sans connaître le streamer ;
- 4-6 : sympa mais banal : il commente, il conduit, il découvre le décor, il écrase quelqu'un, \
il vole une voiture, course-poursuite classique ;
- 1-3 : rien ne se passe, discussion, menu, attente, pub/sponsor, ou contenu sexuel / \
strip-club / nudité (interdit sur TikTok, toujours 1).
Si rien ne vaut 7, dis-le avec des notes basses : ne gonfle jamais une note.
Donne le sujet concret en quelques mots et une raison qui cite la phrase drôle.
Champ jeu : le jeu réellement joué ("GTA 6"…), vide si incertain."""


def _ts_of(iso: str) -> float:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _state_key(vod_id: str) -> str:
    return f"lives/{vod_id}.json"


def _read_pos(vod_id: str) -> float:
    from . import s3lite
    if not s3lite.configured():
        return 0.0
    try:
        raw = s3lite.get(_state_key(vod_id))
        return float(json.loads(raw or b"{}").get("until", 0)) if raw else 0.0
    except Exception as e:
        log.warning("Position de lecture illisible pour la VOD %s : %s", vod_id, e)
        return 0.0


def _save_pos(vod_id: str, until: float) -> None:
    from .remote import enabled, put
    if not enabled():
        return
    try:
        put(_state_key(vod_id), json.dumps({"until": round(until, 1),
                                            "at": datetime.now(timezone.utc).isoformat()}).encode(),
            "application/json", random_suffix=False, important=True)
    except Exception as e:
        log.warning("Position de lecture non enregistrée (VOD %s) : %s", vod_id, e)


def download_vod_audio(url: str, out: Path, start: float, end: float) -> Path:
    """Son seul d'une tranche de VOD Twitch (format audio_only de Twitch)."""
    import yt_dlp
    from yt_dlp.utils import download_range_func
    out.parent.mkdir(parents=True, exist_ok=True)
    opts = {"quiet": True, "noprogress": True, "format": "audio_only/ba/worst",
            "outtmpl": str(out.with_suffix("")) + ".%(ext)s",
            "download_ranges": download_range_func(None, [(start, end)])}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = Path(ydl.prepare_filename(info))
    if not path.exists():
        cands = sorted(out.parent.glob(out.stem + ".*"))
        if not cands:
            raise RuntimeError("Téléchargement du son vide")
        path = cands[0]
    return path


def live_streams(tw, game_id: str, lang: str, n: int, only: list[str]) -> list[dict]:
    """Les lives en cours sur le jeu, les plus regardés d'abord (ou ceux demandés)."""
    params = {"game_id": game_id, "first": 100}
    if lang not in ("any", ""):
        params["language"] = lang
    if only:
        params = {"user_login": only[:100], "first": 100}
    streams = tw._get("/streams", params).get("data", [])
    if only:
        streams = [s for s in streams if s.get("game_id") == game_id]
    streams.sort(key=lambda s: s.get("viewer_count", 0), reverse=True)
    return streams[:n]


def run_lives(cfg: dict, skip_llm: bool = False) -> list[Path]:
    from . import youtube
    from .pipeline import _budget_stop, _make_clip, _prune, game_label, seen_ids, slug
    from .remote import Reporter, seen_on_site
    from .twitch import TwitchClient, parse_twitch_duration

    lc = cfg.get("lives", {})
    top = int(os.environ.get("LIVE_TOP") or lc.get("top", 4))
    only = [s.strip().lower() for s in (os.environ.get("LIVE_STREAMERS") or "").split(",") if s.strip()]
    window = float(os.environ.get("LIVE_WINDOW_MIN") or lc.get("window_minutes", 60)) * 60
    min_fun = int(os.environ.get("LIVE_MIN") or lc.get("min_score", 7))
    per = int(lc.get("max_clips_per_streamer", 2))
    lag = float(lc.get("lag_seconds", 90))  # la fin de la VOD d'un live arrive avec un peu de retard

    guard = Guard(cfg, Path(cfg["paths"]["work"]).parent / "usage.json")
    rep = Reporter()
    rep.kind = "lives"
    _budget_stop(rep)
    if guard.stopped():
        rep.beat("idle", "Arrêt d'urgence actif", "aucun passage")
        return []
    game = game_label(cfg)
    cfg["_run"] = {
        "id": os.environ.get("GITHUB_RUN_ID") or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
        "at": datetime.now(timezone.utc).isoformat(), "trigger": "lives en direct",
        "game": cfg["game_name"], "max_clips": top * per,
    }
    rep.beat("running", "Lecture des lives", f"{top} lives FR sur {game}", node="twitch")
    work = Path(cfg["paths"]["work"])
    produced: list[Path] = []
    try:
        tw = TwitchClient()
        game_id = tw.game_id(cfg["game_name"])
        if not game_id:
            rep.event(f"Jeu « {cfg['game_name']} » introuvable sur Twitch", level="error", force=True)
            return []
        lang = cfg.get("stream_language", "fr")
        streams = live_streams(tw, game_id, lang, top, only)
        if not streams:
            rep.event(f"Aucun live {lang.upper()} en cours sur {game}", node="twitch", force=True)
            return []
        rep.event("Lives regardés : " + ", ".join(
            f"{s['user_name']} ({s.get('viewer_count', 0)} viewers)" for s in streams),
            node="twitch", force=True)
        already = seen_ids(cfg) | seen_on_site()
        _prune(cfg, rep)
        wc = cfg["whisper"]
        model = cfg.get("llm", {}).get("live_model") or cfg.get("llm", {}).get("moments_model",
                                                                              "claude-haiku-5-5")
        for s in streams:
            name = s["user_name"]
            rep.current = name
            info = rep.streamer(name)
            info["etat"] = "en cours"
            vods = tw._get("/videos", {"user_id": s["user_id"], "type": "archive", "first": 1}).get("data", [])
            started = s.get("started_at", "")
            if not vods or (started and _ts_of(vods[0].get("created_at", "")) < _ts_of(started) - 600):
                rep.event(f"[{name}] Pas de rediffusion du live en cours (VOD désactivées) : impossible "
                          f"de le lire", node="twitch", level="warn", force=True)
                info["etat"] = "non retenu"
                continue
            v = vods[0]
            dur = parse_twitch_duration(v["duration"])
            end = max(0.0, dur - lag)
            pos = _read_pos(v["id"])
            start = max(pos, end - window, 0.0)
            if end - start < 120:
                rep.event(f"[{name}] Rien de neuf depuis le dernier passage", node="twitch")
                info["etat"] = "non retenu"
                continue
            rep.event(f"[{name}] Lecture du live de {youtube._ts(start)} à {youtube._ts(end)} "
                      f"(« {v['title'][:80]} »)", node="twitch", force=True)
            sid0 = f"live-{v['id']}"
            try:
                audio = download_vod_audio(v["url"], work / f"{sid0}-{int(start)}" / "audio", start, end)
                samples = media.load_audio(audio)
            except Exception as e:
                rep.stats["erreurs"] += 1
                rep.event(f"[{name}] Son du live illisible : {str(e)[:200]}", level="error", force=True)
                continue
            peaks = youtube.loudness_peaks(samples)
            segs = youtube.rough_transcript(
                samples, cfg.get("youtube", {}).get("analysis_model", "small"), wc["device"],
                wc["compute_type"], prompt=f"Live Twitch de {name} en français sur {game}. {v['title']}")
            seg_dur = len(samples) / 16000
            del samples
            rep.event(f"[{name}] {len(segs)} phrases transcrites, {len(peaks)} pic(s) de volume",
                      node="transcription")
            if skip_llm or not segs:
                _save_pos(v["id"], end)
                continue
            moments = youtube.pick_moments(
                segs, peaks, per + 1, title=v["title"], channel=name, game=game, model=model,
                duration=seg_dur, system=LIVE_SYSTEM.format(game=game), fallback=False)
            _save_pos(v["id"], end)
            if moments:
                rep.event(f"[{name}] Moments lus : " + " · ".join(
                    f"{youtube._ts(start + m['start'])} {m['score']}/10 ({m.get('sujet') or '?'} : "
                    f"{(m.get('raison') or '')[:90]})" for m in moments), node="scoring", force=True)
            good = [m for m in moments if m["score"] >= min_fun][:per]
            if not good:
                rep.event(f"[{name}] Aucun moment drôle à {min_fun}/10 ou plus dans cette tranche",
                          node="scoring", force=True)
                info["etat"] = "non retenu"
                continue
            for k, m in enumerate(good, 1):
                a, b = start + m["start"], start + m["end"]
                sid = f"{sid0}-{int(a) // 60 * 60}"
                if slug(sid) in already or sid in already:
                    continue
                label = f"moment drôle {k}/{len(good)} à {youtube._ts(a)} « {m.get('sujet', '')} » " \
                        f"({m['score']}/10 au live)"
                _make_clip(cfg, rep, produced, already, sid=sid, name=name, label=label,
                           video_fn=lambda a=a, b=b, sid=sid: media.download(
                               v["url"], work / sid / "source.mp4", a, b,
                               max_mb=Guard.get().limits["max_download_mb"]),
                           twitch_title=(m.get("sujet") or v["title"])[:80],
                           source_url=f"{v['url']}?t={int(a)}s", skip_llm=skip_llm,
                           extra={"kind": "live", "fun_score": m["score"],
                                  "potential_reason": m.get("raison", ""), "vod_start": a})
    except LimitReached as e:
        rep.event(f"Garde-fou : {e}", level="warn", force=True)
    except Exception as e:
        log.exception("Lecture des lives en échec")
        rep.stats["erreurs"] += 1
        rep.current = ""
        rep.beat("error", "Lecture des lives en échec", str(e)[:300], with_logs=True)
        raise
    finally:
        for info_s in rep.streamers.values():
            if info_s.get("etat") == "en cours":
                info_s["etat"] = "fini" if info_s.get("produits") else "non retenu"
    rep.current = ""
    rep.beat("idle", "Lecture des lives terminée",
             f"{rep.stats['clips_produits']} clip(s) produit(s) · {guard.summary()}", with_logs=True)
    return produced

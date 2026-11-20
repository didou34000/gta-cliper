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

Beaucoup de gros streamers (Squeezie, JLTomy, Kamet0…) réservent leurs VOD aux abonnés :
pour eux, le bot enregistre directement le live public (streamlink, sans les pubs) pendant
LIVE_RECORD_MIN minutes, en parallèle, puis lit l'enregistrement de la même façon et coupe
les moments drôles dans le fichier enregistré.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from . import chat as chatmod
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

Le chat Twitch : on te donne aussi les pics de rires du chat (MDR, KEKW, 😂… comparés à la \
normale). La transcription ne voit pas l'image ; le chat, lui, réagit à ce qu'il VOIT. Un gros \
pic (×4 ou plus) prouve que des milliers de viewers ont ri ou halluciné : c'est ton meilleur \
indice. Cherche ce qui se passe juste AVANT et pendant chaque gros pic, place le moment pour \
qu'il finisse sur la réaction, et note-le au moins 7 si la transcription montre une action ou \
une réaction claire à cet endroit (8-9 si le pic est énorme, ×8 ou plus). Sans pic de chat, \
un passage ne dépasse 7 que si la réplique est vraiment culte à l'écrit.

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


def vod_readable(url: str) -> tuple[bool, str]:
    """La VOD est-elle lisible sans compte ? (souvent réservée aux abonnés pendant le live)"""
    import yt_dlp
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "noprogress": True, "skip_download": True}) as ydl:
            ydl.extract_info(url, download=False)
        return True, ""
    except Exception as e:
        s = str(e)
        return False, ("réservée aux abonnés" if "subscriber-only" in s else s[:150])


def start_recording(login: str, out: Path, minutes: float) -> subprocess.Popen:
    """Enregistre le live public (sans pubs) pendant `minutes`, en tâche de fond."""
    out.parent.mkdir(parents=True, exist_ok=True)
    h, m = divmod(int(minutes), 60)
    # Streamlink filtre lui-même les pubs Twitch. 720p : 3 à 4 enregistrements parallèles
    # de 40 min tiennent sur le disque d'un serveur GitHub (≈ 1,5 Go chacun).
    cmd = ["streamlink", "--hls-duration", f"{h:02d}:{m:02d}:00",
           "--retry-streams", "10", "--retry-max", "3",
           "-o", str(out), "--force", f"https://www.twitch.tv/{login}", "720p60,720p,best"]
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def cut_local(src: Path, out: Path, a: float, b: float) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{a:.2f}", "-to", f"{b:.2f}",
                    "-i", str(src), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                    "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)],
                   check=True, capture_output=True)
    return out


def run_lives(cfg: dict, skip_llm: bool = False) -> list[Path]:
    from . import youtube
    from .pipeline import _budget_stop, _make_clip, _prune, game_label, seen_ids, slug
    from .remote import Reporter, seen_on_site
    from .twitch import TwitchClient, parse_twitch_duration

    lc = cfg.get("lives", {})
    top = int(os.environ.get("LIVE_TOP") or lc.get("top", 4))
    only = [s.strip().lower() for s in (os.environ.get("LIVE_STREAMERS") or "").split(",") if s.strip()]
    window = float(os.environ.get("LIVE_WINDOW_MIN") or lc.get("window_minutes", 60)) * 60
    rec_min = float(os.environ.get("LIVE_RECORD_MIN") or lc.get("record_minutes", 40))
    min_fun = int(os.environ.get("LIVE_MIN") or lc.get("min_score", 7))
    per = int(lc.get("max_clips_per_streamer", 2))
    lag = float(lc.get("lag_seconds", 90))  # la fin de la VOD d'un live arrive avec un peu de retard
    # Règle du 20/11 : on enregistre tous les lives (même ceux dont la VOD est lisible) pour lire
    # le chat en même temps, ce que la VOD ne permet pas. LIVE_VOD=1 remet l'ancienne lecture.
    use_vod = (os.environ.get("LIVE_VOD") or str(lc.get("use_vod", ""))).lower() in ("1", "true", "yes")

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
    wc = cfg["whisper"]
    model = cfg.get("llm", {}).get("live_model") or cfg.get("llm", {}).get("moments_model",
                                                                          "claude-haiku-5-5")
    recs: list[tuple[dict, Path, subprocess.Popen, float, chatmod.ChatLog]] = []

    def analyse(name: str, title: str, audio: Path, offset: float, make_video, sid0: str,
                source_url, already: set, log_chat=None) -> None:
        """Transcrit, fait noter par Claude, monte les moments ≥ min_fun."""
        info = rep.streamer(name)
        samples = media.load_audio(audio)
        peaks = youtube.loudness_peaks(samples)
        segs = youtube.rough_transcript(
            samples, cfg.get("youtube", {}).get("analysis_model", "small"), wc["device"],
            wc["compute_type"], prompt=f"Live Twitch de {name} en français sur {game}. {title}")
        seg_dur = len(samples) / 16000
        del samples
        rep.event(f"{len(segs)} phrases transcrites ({youtube._ts(seg_dur)} de live), "
                  f"{len(peaks)} pic(s) de volume", node="transcription")
        spk: list = []
        if log_chat is not None:
            spk = chatmod.spikes(log_chat.messages, seg_dur)
            rep.event(f"Chat lu : {len(log_chat.messages)} messages, {len(spk)} pic(s) de rires"
                      + (" (" + ", ".join(f"{youtube._ts(x.t)} ×{x.ratio}" for x in spk) + ")"
                         if spk else "")
                      + (f" · coupures : {log_chat.error}" if log_chat.error and not log_chat.messages
                         else ""), node="scoring", force=True)
        if skip_llm or not segs:
            return
        moments = youtube.pick_moments(
            segs, peaks, per + 1, title=title, channel=name, game=game, model=model,
            duration=seg_dur, system=LIVE_SYSTEM.format(game=game), fallback=False,
            extra=chatmod.describe(spk, youtube._ts) if log_chat is not None else "")
        for m in moments:
            hit = chatmod.best_overlap(spk, m["start"], m["end"])
            m["chat"] = (f"{hit.count} messages de rire en 20 s dans le chat Twitch (×{hit.ratio} "
                         f"la normale)" + (f", ex. « {' » « '.join(hit.examples[:3])} »"
                                          if hit.examples else "")) if hit else ""
        if moments:
            rep.event(f"Moments lus : " + " · ".join(
                f"{youtube._ts(offset + m['start'])} {m['score']}/10 ({m.get('sujet') or '?'} : "
                f"{(m.get('raison') or '')[:90]}"
                + (f" · chat ×{chatmod.best_overlap(spk, m['start'], m['end']).ratio}" if m.get("chat") else "")
                + ")" for m in moments), node="scoring", force=True)
        good = [m for m in moments if m["score"] >= min_fun][:per]
        if not good:
            rep.event(f"Aucun moment drôle à {min_fun}/10 ou plus dans cette tranche",
                      node="scoring", force=True)
            info["etat"] = "non retenu"
            return
        for k, m in enumerate(good, 1):
            a, b = m["start"], m["end"]
            sid = f"{sid0}-{int(offset + a) // 60 * 60}"
            if slug(sid) in already or sid in already:
                continue
            label = f"moment drôle {k}/{len(good)} « {m.get('sujet', '')} » ({m['score']}/10 au live)"
            _make_clip(cfg, rep, produced, already, sid=sid, name=name, label=label,
                       video_fn=lambda a=a, b=b, sid=sid: make_video(a, b, work / sid / "source.mp4"),
                       twitch_title=(m.get("sujet") or title)[:80],
                       source_url=source_url(offset + a), skip_llm=skip_llm,
                       extra={"kind": "live", "fun_score": m["score"],
                              "potential_reason": m.get("raison", ""),
                              "chat_note": m.get("chat", "")})

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

        # 1) Qui a une VOD lisible ? Les autres : on enregistre le live tout de suite.
        vod_jobs = []
        for s in streams:
            name = s["user_name"]
            rep.current = name
            rep.streamer(name)["etat"] = "en cours"
            vods = tw._get("/videos", {"user_id": s["user_id"], "type": "archive", "first": 1}).get("data", [])
            started = s.get("started_at", "")
            ok, why = False, "pas de rediffusion"
            if not use_vod:
                why = "non utilisée (on lit le chat en direct)"
            elif vods and not (started and _ts_of(vods[0].get("created_at", "")) < _ts_of(started) - 600):
                ok, why = vod_readable(vods[0]["url"])
            if ok:
                vod_jobs.append((s, vods[0]))
                continue
            out = work / f"rec-{s['user_login']}" / f"{int(time.time())}.ts"
            t0 = time.time()
            proc = start_recording(s["user_login"], out, rec_min)
            cl = chatmod.ChatLog(s["user_login"], t0)
            cl.start()
            recs.append((s, out, proc, t0, cl))
            rep.event(f"VOD {why} : j'enregistre son live et son chat pendant {rec_min:.0f} min",
                      node="twitch", force=True)

        # 2) Pendant les enregistrements : lecture des VOD lisibles.
        for s, v in vod_jobs:
            name = s["user_name"]
            rep.current = name
            dur = parse_twitch_duration(v["duration"])
            end = max(0.0, dur - lag)
            start = max(_read_pos(v["id"]), end - window, 0.0)
            if end - start < 120:
                rep.event(f"Rien de neuf depuis le dernier passage", node="twitch")
                continue
            rep.event(f"Lecture de la VOD du live de {youtube._ts(start)} à "
                      f"{youtube._ts(end)} (« {v['title'][:80]} »)", node="twitch", force=True)
            try:
                audio = download_vod_audio(v["url"], work / f"live-{v['id']}-{int(start)}" / "audio",
                                           start, end)
            except Exception as e:
                rep.stats["erreurs"] += 1
                rep.event(f"Son de la VOD illisible : {str(e)[:200]}", level="error", force=True)
                continue
            _save_pos(v["id"], end)
            analyse(name, v["title"], audio, start,
                    lambda a, b, out, v=v, start=start: media.download(
                        v["url"], out, start + a, start + b,
                        max_mb=Guard.get().limits["max_download_mb"]),
                    f"live-{v['id']}", lambda t, v=v: f"{v['url']}?t={int(t)}s", already)

        # 3) Enregistrements : on attend la fin, puis même lecture sur le fichier.
        for s, out, proc, t0, cl in recs:
            name = s["user_name"]
            rep.current = name
            try:
                _, err = proc.communicate(timeout=max(60, rec_min * 60 + 300 - (time.time() - t0)))
            except subprocess.TimeoutExpired:
                proc.terminate()
                _, err = proc.communicate()
            cl.stop()
            if not out.exists() or out.stat().st_size < 5_000_000:
                rep.stats["erreurs"] += 1
                rep.event(f"Enregistrement du live raté : "
                          f"{(err or b'').decode(errors='ignore')[-200:]}", level="error", force=True)
                continue
            rep.event(f"Live enregistré ({out.stat().st_size / 1e9:.1f} Go)", node="twitch")
            analyse(name, s.get("title", ""), out, 0.0,
                    lambda a, b, dst, out=out: cut_local(out, dst, a, b),
                    f"rec-{s['user_login']}-{int(t0)}",
                    lambda t, s=s: f"https://www.twitch.tv/{s['user_login']}", already,
                    log_chat=cl)
            out.unlink(missing_ok=True)
    except LimitReached as e:
        rep.event(f"Garde-fou : {e}", level="warn", force=True)
    except Exception as e:
        log.exception("Lecture des lives en échec")
        rep.stats["erreurs"] += 1
        rep.current = ""
        rep.beat("error", "Lecture des lives en échec", str(e)[:300], with_logs=True)
        raise
    finally:
        for _, _, proc, _, cl in recs:
            cl.stop()
            if proc.poll() is None:
                proc.terminate()
        for info_s in rep.streamers.values():
            if info_s.get("etat") == "en cours":
                info_s["etat"] = "fini" if info_s.get("produits") else "non retenu"
    rep.current = ""
    rep.beat("idle", "Lecture des lives terminée",
             f"{rep.stats['clips_produits']} clip(s) produit(s) · {guard.summary()}", with_logs=True)
    return produced

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
from .guard import Guard, LimitReached
from .metadata import generate_metadata

log = logging.getLogger("gta_clipper")


def load_config(path: str | Path = "config.yaml") -> dict:
    import os
    p = Path(path)
    if not p.exists() and p.name == "config.yaml" and Path("config.example.yaml").exists():
        p = Path("config.example.yaml")
    cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
    # Réglages Whisper surchargeables par variables d'environnement (serveur sans GPU…)
    for key, env in (("model", "WHISPER_MODEL"), ("device", "WHISPER_DEVICE"),
                     ("compute_type", "WHISPER_COMPUTE")):
        if os.environ.get(env):
            cfg["whisper"][key] = os.environ[env]
    apply_launch_overrides(cfg, os.environ)
    if (os.environ.get("MIN_VIEWS") or "").isdigit():
        cfg["min_clip_views"] = int(os.environ["MIN_VIEWS"])
    return cfg


ALL_GAMES = {"", "tous", "tous les jeux", "all", "*", "off"}


def apply_launch_overrides(cfg: dict, env) -> dict:
    """Choix faits au lancement manuel (site ou GitHub) : jeu et liste de streamers.

    GAME_NAME : nom exact du jeu sur Twitch, ou « tous » pour ne pas filtrer.
    STREAMERS : logins Twitch séparés par des virgules ; vide = liste du fichier de config.
    """
    game = (env.get("GAME_NAME") or "").strip()
    if game:
        if game.lower() in ALL_GAMES:
            env_game_filter_off(cfg)
        else:
            cfg["game_name"] = game[:80]
    raw = (env.get("STREAMERS") or "").strip()
    if raw:
        known = {st["login"].lower(): st for st in cfg.get("streamers", [])}
        chosen = []
        for login in re.split(r"[\s,;]+", raw.lower()):
            login = login.strip().lstrip("@")
            if re.fullmatch(r"[a-z0-9_]{3,25}", login) and login not in [c["login"] for c in chosen]:
                chosen.append(known.get(login, {"login": login, "name": login.capitalize()}))
        if chosen:
            cfg["streamers"] = chosen[:20]
    return cfg


def env_game_filter_off(cfg: dict) -> None:
    cfg["game_filter"] = False


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()[:60] or "clip"


def seen_ids(cfg: dict) -> set[str]:
    ids = set()
    for key in ("review", "approved", "rejected"):
        for meta in Path(cfg["paths"][key]).glob("*/meta.json"):
            ids.add(json.loads(meta.read_text(encoding="utf-8")).get("source_id", ""))
    return ids


def fallback_hook(streamer: str, twitch_title: str = "") -> str:
    """Accroche sans IA : le titre du clip Twitch s'il est parlant, sinon un titre générique."""
    t = " ".join((twitch_title or "").split())
    if len(t) >= 8 and not t.isdigit() and len(t) <= 45:
        return t
    return f"{streamer} découvre GTA 6"


def apply_corrections(words: list, corrections: list[dict]) -> list[dict]:
    """Applique les corrections de l'IA : un mot remplacé par un mot (horodatage gardé),
    ou un mot supprimé quand un nom avait été coupé en deux. Modifie la liste en place."""
    done, drop = [], set()
    for c in corrections or []:
        i, new = c.get("i"), " ".join(str(c.get("text", "")).split())
        if not (isinstance(i, int) and 0 <= i < len(words)) or " " in new or len(new) > 30:
            continue
        if not new:
            if i > 0 and i - 1 not in drop:  # fusion avec le mot précédent
                drop.add(i)
                done.append({"i": i, "avant": words[i].text, "apres": ""})
        elif new != words[i].text:
            done.append({"i": i, "avant": words[i].text, "apres": new})
            words[i].text = new
    for i in sorted(drop, reverse=True):
        words[i - 1].end = words[i].end
        del words[i]
    return done


def process_clip(cfg: dict, *, source_id: str, streamer_name: str, video: Path,
                 twitch_title: str = "", source_url: str = "", extra: dict | None = None,
                 skip_llm: bool = False, words: list | None = None, beat=None) -> Path:
    """Prend une vidéo horizontale déjà téléchargée et produit un dossier prêt à valider."""
    beat = beat or (lambda node, msg="": None)
    rc, sc, wc = cfg["render"], cfg["subtitles"], cfg["whisper"]
    item_dir = Path(cfg["paths"]["review"]) / f"{datetime.now():%Y%m%d-%H%M%S}-{slug(source_id)}"
    item_dir.mkdir(parents=True, exist_ok=True)

    duration = min(media.probe_duration(video), float(rc.get("max_duration", 60)))

    if words is None:
        beat("transcription", f"Transcription Whisper de {duration:.0f} s de vidéo "
                              f"(modèle {wc['model']}, sur {wc['device']})")
        words = media.transcribe(video, wc["model"], wc["device"], wc["compute_type"],
                                 streamer=streamer_name)
    words = [w for w in words if w.start < duration]
    beat("transcription", f"{len(words)} mots reconnus" if words
         else "Aucune parole détectée : clip sans sous-titres")
    media.save_words(words, item_dir / "transcript.json")

    # 1) Titre, accroche et corrections d'abord : l'accroche est incrustée dans la vidéo.
    text = media.transcript_text(words)
    meta = {"title": f"{streamer_name} sur GTA 6", "alt_titles": [], "description": "",
            "hashtags": cfg["llm"]["base_hashtags"], "confidence": "low",
            "hook": fallback_hook(streamer_name, twitch_title)}
    import os
    if not skip_llm and not os.environ.get("ANTHROPIC_API_KEY"):
        beat("titre", "Pas de clé ANTHROPIC_API_KEY : titre et accroche provisoires")
        skip_llm = True
    if not skip_llm:
        beat("titre", f"Claude écrit le titre et relit {len(words)} mots de transcription")
        try:
            m = generate_metadata(streamer_name, text, twitch_title, cfg["llm"]["model"],
                                  cfg["llm"]["base_hashtags"], words=words).model_dump()
            fixes = apply_corrections(words, m.pop("corrections", []))
            if fixes:
                media.save_words(words, item_dir / "transcript.json")
                text = media.transcript_text(words)
            meta = {**m, "hook": m.get("hook") or meta["hook"], "corrections": fixes}
            beat("titre", f"Titre : « {meta['title']} » · accroche : « {meta['hook']} »"
                          + (f" · {len(fixes)} mot(s) corrigé(s)" if fixes else "")
                          + (" (peu sûr, à vérifier)" if meta.get("confidence") == "low" else ""))
        except Exception as e:  # garde-fou ou panne de l'API : le clip n'est pas perdu
            log.warning("Titre IA impossible : %s", e)
            beat("titre", f"Titre IA impossible ({str(e)[:120]}) : titre provisoire")

    # 2) Montage vertical avec accroche en haut et sous-titres animés.
    ass = subtitles.build_ass(
        words, item_dir / "subs.ass", width=rc["width"], height=rc["height"],
        font=sc["font"], font_size=sc["font_size"], per_line=sc["words_per_line"],
        color=sc["color"], highlight=sc["highlight_color"], outline=sc["outline"],
        pos_y=sc["position_y"], uppercase=sc["uppercase"],
        hook=meta["hook"] if sc.get("hook", True) else "", hook_y=sc.get("hook_y", 330),
        hook_size=sc.get("hook_size", 76), hook_duration=duration,
    )
    beat("render", f"Montage vertical {rc['width']}×{rc['height']} (mode {rc['layout']}) "
                   f"+ accroche en haut + sous-titres {sc['words_per_line']} mots par ligne")
    out = item_dir / "clip.mp4"
    render.render_vertical(video, ass, out, width=rc["width"], height=rc["height"],
                           layout=rc["layout"], facecam=rc.get("facecam"), duration=duration)
    render.extract_thumbnail(out, item_dir / "thumb.jpg", at=min(1.5, duration / 2))
    beat("render", f"Vidéo prête ({out.stat().st_size / 1e6:.1f} Mo, {duration:.0f} s)")

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
    from .remote import Reporter
    guard = Guard(cfg, Path(cfg["paths"]["work"]).parent / "usage.json")
    rep = Reporter()
    if guard.stopped():
        rep.beat("idle", "Arrêt d'urgence actif", "fichier STOP présent : aucun passage")
        return []
    import os
    top_n = int(os.environ.get("TOP_STREAMERS") or cfg.get("top_streamers") or 0)
    if top_n <= 0:
        for st in cfg["streamers"]:
            rep.streamer(st["name"])
    what = (f"les {top_n} plus gros streamers FR sur {cfg['game_name'] if cfg.get('game_filter', True) else 'tous les jeux'}"
            if top_n > 0 else f"{len(cfg['streamers'])} streamer(s) à vérifier")
    rep.beat("running", "Démarrage du passage", what, node="twitch")
    try:
        out = _run(cfg, skip_llm, chat_dir, rep)
    except Exception as e:
        log.exception("Passage interrompu")
        rep.stats["erreurs"] += 1
        rep.beat("error", "Passage interrompu", str(e)[:300], with_logs=True)
        raise
    rep.current = ""
    rep.beat("idle", "Passage terminé",
             f"{rep.stats['clips_produits']} nouveau(x) clip(s) à valider · {guard.summary()}",
             with_logs=True)
    return out


def _make_clip(cfg, rep, produced, already, *, sid, name, video_fn, label, **kw) -> None:
    """Télécharge, monte, titre et envoie un clip, en racontant chaque étape.
    Lève LimitReached si un garde-fou bloque : le passage s'arrête proprement."""
    guard = Guard.get()
    guard.check_clip()
    try:
        rep.event(f"Téléchargement de {label}", node="twitch")
        video = video_fn()
        rep.event(f"Téléchargé ({video.stat().st_size / 1e6:.1f} Mo)", node="twitch")
        item = process_clip(cfg, source_id=sid, streamer_name=name, video=video,
                            beat=lambda n, m="": rep.event(m, node=n), **kw)
        produced.append(item)
        already.add(sid)
        guard.clip_done()
        rep.stats["clips_produits"] += 1
        rep.add(name, "produits")
        from .remote import enabled, upload_clip
        if enabled():
            rep.event("Envoi de la vidéo sur le site", node="site")
            try:
                upload_clip(item)
                _prune(cfg, rep, keep=item.name)
                rep.event(f"Clip prêt à valider : {label}", node="site", force=True)
            except Exception as e:
                rep.stats["erreurs"] += 1
                rep.event(f"Clip prêt en local mais pas envoyé sur le site : {e}",
                          node="site", level="error")
        else:
            rep.event(f"Clip prêt en local : {item.name}", node="site")
    except LimitReached:
        raise
    except Exception as e:
        log.exception("Échec sur %s", sid)
        guard.clip_failed()
        rep.stats["erreurs"] += 1
        rep.event(f"Échec sur {label} : {str(e)[:200]}", level="error")


def _prune(cfg: dict, rep, keep: str = "") -> None:
    """Plafond de clips sur le site (stockage Vercel) : on supprime les plus inutiles."""
    from .remote import prune_site
    try:
        gone = prune_site(int(cfg.get("limits", {}).get("max_clips_on_site", 20)), keep=keep)
        if gone:
            rep.event(f"Ménage : {len(gone)} ancien(s) clip(s) supprimé(s) du site "
                      f"(plafond {cfg.get('limits', {}).get('max_clips_on_site', 20)})", node="site")
    except Exception as e:
        log.warning("Ménage du site impossible : %s", e)


def _run(cfg: dict, skip_llm: bool, chat_dir: str | None, rep) -> list[Path]:
    from .twitch import TwitchClient, fetch_chat_offsets_gql, load_chat_offsets

    import os
    tw = TwitchClient()
    if not cfg.get("game_filter", True) or \
            os.environ.get("GAME_FILTER", "on").lower() in ("off", "0", "non", "all"):
        game_id = None
        rep.event("Filtre jeu désactivé pour ce passage : tous les jeux sont pris", node="twitch",
                  level="warn")
    else:
        game_id = tw.game_id(cfg["game_name"])
    if game_id:
        rep.event(f"Jeu « {cfg['game_name']} » trouvé sur Twitch (id {game_id})", node="twitch")
    elif cfg.get("game_filter", True) and \
            os.environ.get("GAME_FILTER", "on").lower() not in ("off", "0", "non", "all"):
        # On s'arrête plutôt que de prendre tous les jeux sans le dire.
        rep.event(f"Jeu « {cfg['game_name']} » introuvable sur Twitch : vérifie le nom exact "
                  f"(ou choisis « Tous les jeux »). Passage arrêté.",
                  node="twitch", level="error", force=True)
        return []
    top_n = int(os.environ.get("TOP_STREAMERS") or cfg.get("top_streamers") or 0)
    if top_n > 0:
        game_label = cfg["game_name"] if game_id else "tous les jeux"
        rep.event(f"Recherche des {top_n} plus gros streamers FR sur {game_label}", node="twitch",
                  force=True)
        top = tw.top_streamers(game_id, n=min(top_n, 20), hours=cfg["lookback_hours"],
                               known=[s["login"] for s in cfg.get("streamers", [])],
                               min_views=cfg["min_clip_views"])
        st = getattr(tw, "last_top_stats", {})
        if not top:
            rep.event(f"Aucun streamer FR n'a de clip à {cfg['min_clip_views']} vues ou plus sur "
                      f"{game_label} dans les {cfg['lookback_hours']} dernières heures "
                      f"({st.get('candidats', 0)} streamers vérifiés"
                      + (f" ; meilleur clip trouvé : {st['meilleur'][0]} vues chez {st['meilleur'][1]}"
                         if st.get("meilleur", (0,))[0] else " ; aucun clip sur ce jeu")
                      + "). Baisse les vues minimum ou choisis un autre jeu. Passage arrêté.",
                      node="twitch", level="warn", force=True)
            return []
        cfg["streamers"] = [{"login": t["login"], "name": t["name"]} for t in top]
        for t in top:
            rep.streamer(t["name"])
        rep.event("Streamers retenus : " + ", ".join(f"{t['name']} ({t['why']})" for t in top),
                  node="twitch", force=True)
    already = seen_ids(cfg)
    from .remote import seen_on_site
    _prune(cfg, rep)
    on_site = seen_on_site()  # clips déjà envoyés (utile quand le disque est vidé à chaque passage)
    if on_site:
        already |= {sid for sid in on_site}
    work = Path(cfg["paths"]["work"])
    produced: list[Path] = []
    hours, min_views = cfg["lookback_hours"], cfg["min_clip_views"]

    try:
        _streamers_loop(cfg, skip_llm, chat_dir, rep, tw, game_id, already, work, produced,
                        hours, min_views)
    except LimitReached as e:
        info = rep.streamer(rep.current) if rep.current else None
        if info:
            info["etat"] = "arrêté"
        rep.event(f"Garde-fou : {e}. Reprise au prochain passage.", level="warn", force=True)
    return produced


def _streamers_loop(cfg, skip_llm, chat_dir, rep, tw, game_id, already, work, produced,
                    hours, min_views):
    from .twitch import fetch_chat_offsets_gql, load_chat_offsets
    for idx, st in enumerate(cfg["streamers"], 1):
        name = rep.current = st["name"]
        info = rep.streamer(name)
        info["etat"] = "en cours"
        rep.event(f"Streamer {idx}/{len(cfg['streamers'])} : recherche de la chaîne "
                  f"twitch.tv/{st['login']}", node="twitch", force=True)
        uid = tw.user_id(st["login"])
        if not uid:
            info["etat"] = "erreur"
            rep.event(f"Chaîne twitch.tv/{st['login']} introuvable (login à corriger dans "
                      f"config.yaml)", node="twitch", level="error")
            continue

        # 1) Clips viewers les plus vus
        rep.event(f"Lecture des clips des {hours} dernières heures", node="twitch")
        clips = tw.top_clips(uid, hours, game_id, min_views, cfg["max_clips_per_streamer"])
        cs = getattr(tw, "last_clip_stats", {})
        info["clips_vus"] += cs.get("total", 0)
        info["retenus"] += len(clips)
        rep.stats["clips_trouves"] += len(clips)
        rep.event(
            f"{cs.get('total', 0)} clip(s) trouvés : {cs.get('hors_jeu', 0)} hors jeu, "
            f"{cs.get('sous_seuil', 0)} sous {min_views} vues, {cs.get('doublons', 0)} doublon(s), "
            f"{cs.get('hors_quota', 0)} hors quota → {len(clips)} retenu(s)"
            + (f" (le plus vu : {cs['max_vues']} vues)" if cs.get("max_vues") else ""),
            node="scoring")
        for n, c in enumerate(clips, 1):
            sid = f"clip-{c.id}"
            label = f"clip {n}/{len(clips)} « {c.title} » ({c.view_count} vues)"
            if sid in already or slug(sid) in already:
                info["deja_faits"] += 1
                rep.event(f"Déjà traité, ignoré : {label}", node="scoring")
                continue
            _make_clip(cfg, rep, produced, already, sid=sid, name=name, label=label,
                       video_fn=lambda c=c, sid=sid: media.download(c.url, work / sid / "source.mp4", max_mb=Guard.get().limits["max_download_mb"]),
                       twitch_title=c.title, source_url=c.url, skip_llm=skip_llm,
                       extra={"views": c.view_count, "kind": "twitch_clip"})

        # 2) Pics de chat dans la dernière VOD (optionnel)
        vc = cfg.get("vod", {})
        if vc.get("enabled"):
            for v in tw.recent_vods(uid, vc.get("max_vods_per_streamer", 1)):
                rep.event(f"Lecture du chat de la VOD « {v.title} » ({v.duration_s // 60} min)",
                          node="scoring")
                try:
                    local = Path(chat_dir) / f"{v.id}.json" if chat_dir else None
                    offsets = (load_chat_offsets(local) if local and local.exists()
                               else fetch_chat_offsets_gql(v.id))
                except Exception as e:
                    rep.event(f"Chat indisponible pour la VOD {v.id} : {str(e)[:150]}",
                              node="scoring", level="warn")
                    continue
                hls = chat_spikes(offsets, v.duration_s, vc["window_seconds"], vc["min_zscore"],
                                  vc["clip_before"], vc["clip_after"], vc["max_highlights_per_vod"])
                info["pics_chat"] += len(hls)
                rep.event(f"{len(offsets)} messages analysés → {len(hls)} pic(s) avec z ≥ "
                          f"{vc['min_zscore']}", node="scoring")
                for n, h in enumerate(hls, 1):
                    sid = f"vod-{v.id}-{int(h.start)}"
                    t = f"{int(h.start) // 3600}h{int(h.start) % 3600 // 60:02d}"
                    label = f"pic de chat {n}/{len(hls)} à {t} (z = {h.score:.1f})"
                    if sid in already or slug(sid) in already:
                        info["deja_faits"] += 1
                        rep.event(f"Déjà traité, ignoré : {label}", node="scoring")
                        continue
                    _make_clip(cfg, rep, produced, already, sid=sid, name=name, label=label,
                               video_fn=lambda v=v, h=h, sid=sid: media.download(
                                   v.url, work / sid / "source.mp4", h.start, h.end,
                                   max_mb=Guard.get().limits["max_download_mb"]),
                               twitch_title=v.title, source_url=f"{v.url}?t={int(h.start)}s",
                               skip_llm=skip_llm,
                               extra={"kind": "vod_chat_spike", "chat_zscore": h.score})
        info["etat"] = "erreur" if info["erreurs"] and not info["produits"] else "fini"
        rep.event(f"Terminé : {info['produits']} clip(s) produit(s), {info['deja_faits']} déjà "
                  f"faits, {info['erreurs']} erreur(s)", node="site", force=True)
    return produced

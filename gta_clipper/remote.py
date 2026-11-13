"""Envoi du statut du bot et des clips vers le site privé (stockage Cloudflare R2).

Configuration (variables d'environnement, les mêmes que sur Vercel) :
  R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_PUBLIC_URL (https://pub-….r2.dev)
  R2_BUCKET (facultatif, « gta-clipper » par défaut).
Sans ces variables, tout est ignoré et le bot fonctionne en local comme avant.

Les fichiers ne sont jamais écrasés (suffixe aléatoire), pour éviter les caches.
Quota gratuit R2 : 10 Go, 1 million d'écritures/listages et 10 millions de lectures par mois.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import requests

log = logging.getLogger("gta_clipper")

from . import s3lite


def enabled() -> bool:
    return s3lite.configured()


def _suffixed(pathname: str) -> str:
    stem, dot, ext = pathname.rpartition(".")
    tag = secrets.token_hex(5)
    return f"{stem}-{tag}.{ext}" if dot and "/" not in ext else f"{pathname}-{tag}"


def put(pathname: str, data: bytes, content_type: str, random_suffix: bool = True,
        important: bool = True) -> dict:
    from .guard import Guard
    if not Guard.get().allow_upload(important):
        raise RuntimeError("Plafond quotidien d'envois vers le site atteint")
    key = _suffixed(pathname) if random_suffix else pathname
    try:
        s3lite.put(key, data, content_type, "public, max-age=31536000, immutable"
                   if random_suffix else "no-cache")
    except Exception as e:
        raise RuntimeError(f"Envoi vers le stockage R2 échoué ({pathname}) : {e}") from e
    return {"pathname": key, "url": s3lite.public_url(key)}


def _list(prefix: str) -> list[dict]:
    return s3lite.list_objects(prefix)


def _delete(urls: list[str]) -> None:
    base = s3lite.public_url() + "/"
    s3lite.delete([u[len(base):] if u.startswith(base) else u for u in urls])


# Ordre de suppression quand on dépasse le plafond : d'abord ce qui ne sert plus.
PRUNE_ORDER = {"rejected": 0, "posted": 1, "pending": 2, "approved": 3}


MB = 1024 * 1024


def prune_site(max_clips: int = 0, keep: str = "", high_mb: int = 800, low_mb: int = 400,
               keep_heartbeats: int = 30) -> list[str]:
    """Ménage du stockage (on reste bien sous le quota gratuit) :

    - les clips rejetés partent toujours ;
    - les vieux statuts du bot (heartbeat/) au-delà des keep_heartbeats derniers partent ;
    - dès que le stockage total atteint high_mb (800 Mo), on supprime des clips jusqu'à
      redescendre sous low_mb (400 Mo) : d'abord les publiés, puis les plus anciens
      « à valider », et les « à poster » en tout dernier ; à statut égal, le plus ancien d'abord ;
    - max_clips > 0 ajoute un plafond en nombre de clips (0 = pas de plafond en nombre).
    Un petit repère seen/<id> est gardé pour que le bot ne refasse pas ce clip.
    Renvoie la liste des clips supprimés.
    """
    if not enabled():
        return []
    every = _list("")
    clips: dict[str, list[dict]] = {}
    decisions: dict[str, list[dict]] = {}
    beats: list[dict] = []
    for b in every:
        parts = b["pathname"].split("/")
        if parts[0] == "clips" and len(parts) >= 3:
            clips.setdefault(parts[1], []).append(b)
        elif parts[0] == "decisions" and len(parts) >= 3:
            decisions.setdefault(parts[1], []).append(b)
        elif parts[0] == "heartbeat":
            beats.append(b)
    total = sum(int(b.get("size", 0)) for b in every)

    old_beats = sorted(beats, key=lambda b: b["pathname"])[:-keep_heartbeats] if len(beats) > keep_heartbeats else []
    if old_beats:
        _delete([b["url"] for b in old_beats])
        total -= sum(int(b.get("size", 0)) for b in old_beats)

    def status(cid: str) -> str:
        ds = sorted(decisions.get(cid, []), key=lambda b: b["pathname"])
        if not ds:
            return "pending"
        try:
            return requests.get(ds[-1]["url"], timeout=20).json().get("status", "pending")
        except Exception:
            return "approved"  # dans le doute, on ne supprime pas en priorité

    size = {cid: sum(int(b.get("size", 0)) for b in bl) for cid, bl in clips.items()}
    st = {cid: status(cid) for cid in clips if cid != keep}
    victims = [cid for cid, s in st.items() if s == "rejected"]
    left = total - sum(size[c] for c in victims)
    rest = sorted((c for c in st if c not in victims), key=lambda cid: (PRUNE_ORDER.get(st[cid], 2), cid))
    if total >= high_mb * MB:
        for cid in rest:
            if left <= low_mb * MB:
                break
            victims.append(cid)
            left -= size[cid]
    if max_clips > 0:
        over = len(clips) - len(victims) - max_clips
        victims += [c for c in rest if c not in victims][:max(0, over)]
    for cid in victims:
        put(f"seen/{cid}.json", b"{}", "application/json", random_suffix=False, important=True)
        _delete([b["url"] for b in clips[cid]] + [b["url"] for b in decisions.get(cid, [])])
    if victims:
        log.info("Ménage : %d clip(s) supprimé(s), stockage ~%d Mo", len(victims), left // MB)
    return victims


def seen_on_site() -> set[str]:
    """Identifiants (forme « slug ») des clips déjà faits : ceux présents sur le site
    (clips/AAAAMMJJ-HHMMSS-<slug>/…) et ceux supprimés par le ménage (seen/<dossier>.json)."""
    if not enabled():
        return set()
    import re
    out = set()
    try:
        for prefix in ("clips/", "seen/"):
            for b in _list(prefix):
                parts = b.get("pathname", "").split("/")
                if len(parts) >= 2:
                    name = parts[1].removesuffix(".json")
                    out.add(re.sub(r"^\d{8}-\d{6}-", "", name))
    except Exception as e:
        log.warning("Liste des clips du site illisible : %s", e)
    return out


class LogBuffer(logging.Handler):
    """Garde les dernières lignes de log pour les afficher sur le site."""

    def __init__(self, n: int = 40):
        super().__init__(logging.INFO)
        self.lines: deque[str] = deque(maxlen=n)
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))

    def emit(self, record):
        self.lines.append(self.format(record))


class Reporter:
    """Raconte au site ce que fait le bot : un journal d'événements détaillé
    (quel streamer, quelle étape, quel clip) + un résumé par streamer.

    Chaque envoi contient tout l'état courant (40 derniers événements inclus), donc le
    site n'a besoin de lire que le dernier fichier. Les envois sont espacés d'au moins
    MIN_INTERVAL secondes pour ne pas consommer le quota d'opérations du stockage ;
    le début, la fin et les erreurs partent toujours tout de suite.
    """

    MIN_INTERVAL = 30

    def __init__(self):
        self.on = enabled()
        self.stats = {"clips_trouves": 0, "clips_produits": 0, "erreurs": 0}
        self.streamers: dict[str, dict] = {}
        self.events: deque[dict] = deque(maxlen=40)
        self.status, self.node, self.step, self.message = "idle", "", "", ""
        self.current = ""
        self.kind = "twitch"
        self.usage: dict = {}
        self._last_push = 0.0
        self._dirty = False
        self.buffer = LogBuffer()
        logging.getLogger("gta_clipper").addHandler(self.buffer)

    # --- résumé par streamer ---------------------------------------------
    def streamer(self, name: str) -> dict:
        return self.streamers.setdefault(name, {
            "etat": "en attente", "clips_vus": 0, "retenus": 0, "deja_faits": 0,
            "produits": 0, "erreurs": 0, "pics_chat": 0, "action": "", "ts": "",
        })

    def add(self, name: str, key: str, n: int = 1):
        self.streamer(name)[key] += n

    # --- journal ---------------------------------------------------------
    def event(self, text: str, *, streamer: str = "", node: str = "", level: str = "info",
              status: str = "running", force: bool = False):
        """Ajoute une ligne au journal du site et met à jour l'étape en cours."""
        streamer = streamer or self.current
        self.events.appendleft({"ts": _now(), "streamer": streamer, "node": node,
                                "text": text, "level": level})
        self.status, self.step, self.message = status, text, ""
        if node:
            self.node = node
        if streamer:
            st = self.streamer(streamer)
            st["action"], st["ts"] = text, _now()
            if level == "error":
                st["erreurs"] += 1
        (log.warning if level in ("warn", "error") else log.info)(
            "%s%s", f"[{streamer}] " if streamer else "", text)
        self._dirty = True
        self.push(force=force or level == "error")

    def beat(self, status: str, step: str = "", message: str = "", with_logs: bool = False,
             node: str = ""):
        """Début/fin de passage, test de liaison. En fin de passage, le relevé de
        consommation est enregistré et joint au statut."""
        self.status, self.step, self.message = status, step, message
        if status in ("idle", "error") and "Arrêt d'urgence" not in step:
            from . import usage
            self.usage = usage.save_run(self.kind, "error" if status == "error" else "ok")
        if node:
            self.node = node
        self.events.appendleft({"ts": _now(), "streamer": self.current, "node": node,
                                "text": step + (f" : {message}" if message else ""),
                                "level": "error" if status == "error" else "info"})
        self._dirty = True
        self.push(force=True, with_logs=with_logs)

    def push(self, force: bool = False, with_logs: bool = False):
        if not self.on or not self._dirty:
            return
        if not force and time.time() - self._last_push < self.MIN_INTERVAL:
            return
        hb = {"ts": _now(), "status": self.status, "step": self.step, "message": self.message,
              "node": self.node, "streamer": self.current, "stats": dict(self.stats),
              "streamers": self.streamers, "events": list(self.events), "kind": self.kind}
        if self.usage:
            hb["usage"] = self.usage
        if with_logs:
            hb["logs"] = list(self.buffer.lines)
        try:
            # Un seul fichier réécrit : le site le lit directement, sans listage.
            put("status/live.json", json.dumps(hb, ensure_ascii=False).encode(),
                "application/json", random_suffix=False, important=force)
            self._last_push, self._dirty = time.time(), False
        except Exception as e:  # le site ne doit jamais bloquer le bot
            # On n'insiste pas à chaque ligne : prochain essai dans MIN_INTERVAL secondes,
            # et plus du tout si le stockage est bloqué (quota dépassé, store suspendu).
            self._last_push = time.time()
            if any(w in str(e) for w in ("AccessDenied", "403", "InvalidAccessKeyId", "NoSuchBucket",
                                         "SignatureDoesNotMatch", "name resolution",
                                         "Name or service not known", "Plafond R2")):
                self.on = False
                log.error("Stockage du site bloqué (%s) : le bot continue mais le site ne sera "
                          "plus mis à jour pendant ce passage.", e)
            else:
                log.warning("Statut non envoyé au site : %s", e)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def auto_approve_min() -> int:
    """Seuil de validation automatique réglé sur le site (Programmation) : un clip dont la
    note de potentiel atteint ce seuil passe directement « À poster ». 0 = désactivé."""
    env = os.environ.get("AUTO_APPROVE_MIN")
    if env is not None and env.strip().isdigit():
        return int(env)
    try:
        raw = s3lite.get("schedule/config.json")  # 1 lecture, pas de listage
        if raw:
            return int(json.loads(raw).get("auto_min", 7))
    except Exception as e:
        log.warning("Seuil de validation auto illisible (%s) : validation manuelle", e)
        return 0
    return 7


def approve(cid: str, reason: str) -> None:
    """Valide un clip à la place de l'humain (même format que le bouton « Valider » du site)."""
    put(f"decisions/{cid}/{int(time.time() * 1000)}.json",
        json.dumps({"status": "approved", "auto": True, "reason": reason,
                    "at": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False).encode(),
        "application/json")


def upload_clip(item_dir: Path) -> None:
    """Envoie clip.mp4, thumb.jpg puis meta.json (en dernier : le site n'affiche un clip
    qu'une fois sa meta présente, donc jamais un clip à moitié envoyé)."""
    if not enabled():
        return
    meta = json.loads((item_dir / "meta.json").read_text(encoding="utf-8"))
    cid = item_dir.name
    v = put(f"clips/{cid}/clip.mp4", (item_dir / "clip.mp4").read_bytes(), "video/mp4")
    t = put(f"clips/{cid}/thumb.jpg", (item_dir / "thumb.jpg").read_bytes(), "image/jpeg")
    meta = {k: meta[k] for k in meta if k not in ("status",)}
    meta.update({"video_url": v["url"], "thumb_url": t["url"]})
    put(f"clips/{cid}/meta.json", json.dumps(meta, ensure_ascii=False).encode(),
        "application/json")
    (item_dir / ".uploaded").write_text(datetime.now(timezone.utc).isoformat())
    log.info("Clip envoyé sur le site : %s", meta.get("title"))

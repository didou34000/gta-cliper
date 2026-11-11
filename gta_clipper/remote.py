"""Envoi du statut du bot et des clips vers le site privé (stockage Vercel Blob).

Configuration : variable d'environnement BLOB_READ_WRITE_TOKEN (la même que celle du
projet Vercel, visible dans Vercel > Storage > le store Blob > ".env.local").
Sans cette variable, tout est ignoré et le bot fonctionne en local comme avant.

Les fichiers ne sont jamais écrasés (noms uniques), pour éviter le cache CDN de Blob.
"""
from __future__ import annotations

import json
import logging
import os
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests

log = logging.getLogger("gta_clipper")

API = os.environ.get("VERCEL_BLOB_API_URL", "https://vercel.com/api/blob")
API_VERSION = "12"  # version utilisée par @vercel/blob 2.8


def enabled() -> bool:
    return bool(os.environ.get("BLOB_READ_WRITE_TOKEN"))


def put(pathname: str, data: bytes, content_type: str, random_suffix: bool = True,
        important: bool = True) -> dict:
    from .guard import Guard
    if not Guard.get().allow_upload(important):
        raise RuntimeError("Plafond quotidien d'envois vers le site atteint")
    token = os.environ["BLOB_READ_WRITE_TOKEN"]
    headers = {
        "authorization": f"Bearer {token}",
        "x-api-version": API_VERSION,
        "x-vercel-blob-access": "public",
        "x-content-type": content_type,
        "x-add-random-suffix": "1" if random_suffix else "0",
    }
    url = f"{API}/?{urlencode({'pathname': pathname})}"
    last_err = None
    for attempt in range(4):
        try:
            r = requests.put(url, data=data, headers=headers, timeout=300)
            if r.status_code < 300:
                return r.json()
            last_err = f"HTTP {r.status_code} : {r.text[:300]}"
            if r.status_code < 500 and r.status_code != 429:
                break
        except requests.RequestException as e:
            last_err = str(e)
        time.sleep(2 ** attempt)
    raise RuntimeError(f"Envoi vers Vercel Blob échoué ({pathname}) : {last_err}")


def _list(prefix: str) -> list[dict]:
    out, cursor = [], None
    for _ in range(20):
        params = {"prefix": prefix, "limit": "1000", **({"cursor": cursor} if cursor else {})}
        r = requests.get(f"{API}/?{urlencode(params)}", timeout=30, headers={
            "authorization": f"Bearer {os.environ['BLOB_READ_WRITE_TOKEN']}",
            "x-api-version": API_VERSION})
        r.raise_for_status()
        d = r.json()
        out += d.get("blobs", [])
        cursor = d.get("cursor") if d.get("hasMore") else None
        if not cursor:
            break
    return out


def _delete(urls: list[str]) -> None:
    for i in range(0, len(urls), 100):
        r = requests.post(f"{API}/delete", json={"urls": urls[i:i + 100]}, timeout=60, headers={
            "authorization": f"Bearer {os.environ['BLOB_READ_WRITE_TOKEN']}",
            "x-api-version": API_VERSION, "content-type": "application/json"})
        r.raise_for_status()


# Ordre de suppression quand on dépasse le plafond : d'abord ce qui ne sert plus.
PRUNE_ORDER = {"rejected": 0, "posted": 1, "pending": 2, "approved": 3}


def prune_site(max_clips: int = 20, keep: str = "") -> list[str]:
    """Garde au plus max_clips clips sur le site (plafond de stockage Vercel).

    Supprime d'abord les rejetés, puis les publiés, puis les plus anciens « à valider »,
    et les « à poster » en tout dernier ; à statut égal, le plus ancien part en premier.
    Un petit repère seen/<id> est gardé pour que le bot ne refasse pas ce clip.
    Renvoie la liste des clips supprimés.
    """
    if not enabled() or max_clips <= 0:
        return []
    clips: dict[str, list[dict]] = {}
    for b in _list("clips/"):
        parts = b["pathname"].split("/")
        if len(parts) >= 3:
            clips.setdefault(parts[1], []).append(b)
    decisions: dict[str, list[dict]] = {}
    for b in _list("decisions/"):
        parts = b["pathname"].split("/")
        if len(parts) >= 3:
            decisions.setdefault(parts[1], []).append(b)

    def status(cid: str) -> str:
        ds = sorted(decisions.get(cid, []), key=lambda b: b["pathname"])
        if not ds:
            return "pending"
        try:
            return requests.get(ds[-1]["url"], timeout=20).json().get("status", "pending")
        except Exception:
            return "approved"  # dans le doute, on ne supprime pas en priorité

    st = {cid: status(cid) for cid in clips if cid != keep}
    # Les rejetés partent toujours (le site les supprime déjà, ceci nettoie les anciens).
    victims = [cid for cid, s in st.items() if s == "rejected"]
    rest = sorted((c for c in st if c not in victims), key=lambda cid: (PRUNE_ORDER.get(st[cid], 2), cid))
    over = len(clips) - len(victims) - max_clips
    if over > 0:
        victims += rest[:over]
    for cid in victims:
        put(f"seen/{cid}.json", b"{}", "application/json", random_suffix=False, important=True)
        _delete([b["url"] for b in clips[cid]] + [b["url"] for b in decisions.get(cid, [])])
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
    MIN_INTERVAL secondes pour ne pas consommer le quota d'opérations de Vercel Blob ;
    le début, la fin et les erreurs partent toujours tout de suite.
    """

    MIN_INTERVAL = 20

    def __init__(self):
        self.on = enabled()
        self.stats = {"clips_trouves": 0, "clips_produits": 0, "erreurs": 0}
        self.streamers: dict[str, dict] = {}
        self.events: deque[dict] = deque(maxlen=40)
        self.status, self.node, self.step, self.message = "idle", "", "", ""
        self.current = ""
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
        """Compatibilité : début/fin de passage, test de liaison."""
        self.status, self.step, self.message = status, step, message
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
              "streamers": self.streamers, "events": list(self.events)}
        if with_logs:
            hb["logs"] = list(self.buffer.lines)
        try:
            put(f"heartbeat/{int(time.time() * 1000)}.json",
                json.dumps(hb, ensure_ascii=False).encode(), "application/json",
                important=force)
            self._last_push, self._dirty = time.time(), False
        except Exception as e:  # le site ne doit jamais bloquer le bot
            log.warning("Statut non envoyé au site : %s", e)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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

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


def put(pathname: str, data: bytes, content_type: str, random_suffix: bool = True) -> dict:
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


class LogBuffer(logging.Handler):
    """Garde les dernières lignes de log pour les afficher sur le site."""

    def __init__(self, n: int = 40):
        super().__init__(logging.INFO)
        self.lines: deque[str] = deque(maxlen=n)
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S"))

    def emit(self, record):
        self.lines.append(self.format(record))


class Reporter:
    """Envoie un 'battement de cœur' au site à chaque étape importante."""

    def __init__(self):
        self.on = enabled()
        self.stats = {"clips_trouves": 0, "clips_produits": 0, "erreurs": 0}
        self.buffer = LogBuffer()
        logging.getLogger("gta_clipper").addHandler(self.buffer)

    def beat(self, status: str, step: str = "", message: str = "", with_logs: bool = False):
        if not self.on:
            return
        hb = {"ts": datetime.now(timezone.utc).isoformat(), "status": status, "step": step,
              "message": message, "stats": dict(self.stats)}
        if with_logs:
            hb["logs"] = list(self.buffer.lines)
        try:
            put(f"heartbeat/{int(time.time() * 1000)}.json",
                json.dumps(hb, ensure_ascii=False).encode(), "application/json")
        except Exception as e:  # le site ne doit jamais bloquer le bot
            log.warning("Statut non envoyé au site : %s", e)


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

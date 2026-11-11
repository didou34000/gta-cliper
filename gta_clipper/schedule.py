"""Planification réglée depuis le site.

GitHub lance ce petit script toutes les 20 minutes (sans rien installer). Il lit le réglage
enregistré par le site dans Vercel Blob (schedule/current.json) et décide si c'est l'heure
d'un passage.

Quota : l'offre gratuite de Vercel Blob ne donne que 2 000 « opérations avancées » par mois
(chaque envoi ou chaque liste). On ne liste donc plus rien ici : on lit deux fichiers à nom
fixe par leur adresse publique (lecture simple, quota 10 x plus large). Si oui, il note l'heure (schedule/last-run.json) et donne au
passage le jeu, le nombre de streamers et le nombre de clips choisis.

Uniquement la bibliothèque standard : il tourne avant l'installation des dépendances.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API = os.environ.get("VERCEL_BLOB_API_URL", "https://vercel.com/api/blob")
HEADERS = {"x-api-version": "12"}
TOLERANCE_S = 120  # GitHub déclenche souvent avec une ou deux minutes de retard


def _req(url: str, method: str = "GET", data: bytes | None = None, headers: dict | None = None):
    token = os.environ["BLOB_READ_WRITE_TOKEN"]
    h = {"authorization": f"Bearer {token}", **HEADERS, **(headers or {})}
    r = urllib.request.urlopen(urllib.request.Request(url, data=data, method=method, headers=h),
                               timeout=30)
    return json.loads(r.read() or b"{}")


def public_url(pathname: str) -> str:
    """Adresse publique d'un fichier à nom fixe (même règle que @vercel/blob)."""
    store = os.environ["BLOB_READ_WRITE_TOKEN"].split("_")[3]
    return f"https://{store}.public.blob.vercel-storage.com/{pathname}"


def read_json(pathname: str) -> dict | None:
    """Lit un fichier à nom fixe. None s'il n'existe pas encore."""
    try:
        with urllib.request.urlopen(f"{public_url(pathname)}?t={int(time.time())}", timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def write_json(pathname: str, data: dict) -> None:
    q = urllib.parse.urlencode({"pathname": pathname})
    _req(f"{API}/?{q}", method="PUT", data=json.dumps(data).encode(),
         headers={"x-vercel-blob-access": "public", "x-content-type": "application/json",
                  "x-add-random-suffix": "0", "x-allow-overwrite": "1",
                  "x-cache-control-max-age": "60"})


def latest_config() -> dict | None:
    cfg = read_json("schedule/current.json")
    if cfg is not None:
        return cfg
    # Ancien format (schedule/config-<ms>.json) : une seule liste, puis on recopie le
    # dernier réglage sous le nom fixe pour ne plus jamais avoir à lister.
    q = urllib.parse.urlencode({"prefix": "schedule/config-", "limit": "1000"})
    cfgs = sorted(_req(f"{API}/?{q}").get("blobs", []), key=lambda b: b["uploadedAt"])
    if not cfgs:
        return None
    with urllib.request.urlopen(cfgs[-1]["url"], timeout=30) as r:
        cfg = json.loads(r.read())
    write_json("schedule/current.json", cfg)
    return cfg


def last_run() -> datetime | None:
    d = read_json("schedule/last-run.json")
    try:
        return datetime.fromisoformat(d["at"]) if d and d.get("at") else None
    except ValueError:
        return None


def mark_run(now: datetime) -> None:
    write_json("schedule/last-run.json", {"at": now.isoformat()})


def decide(cfg: dict | None, last: datetime | None, now: datetime) -> tuple[bool, str]:
    if not cfg or not cfg.get("enabled"):
        return False, "programmation arrêtée sur le site"
    every = max(20, int(cfg.get("every_min", 30))) * 60
    if last and (now - last).total_seconds() < every - TOLERANCE_S:
        wait = int((every - (now - last).total_seconds()) // 60) + 1
        return False, f"prochain passage dans ~{wait} min"
    return True, f"passage programmé (toutes les {every // 60} min)"


def main() -> int:
    out = os.environ.get("GITHUB_OUTPUT")
    now = datetime.now(timezone.utc)
    if not os.environ.get("BLOB_READ_WRITE_TOKEN"):
        print("BLOB_READ_WRITE_TOKEN manquant : programmation impossible")
        run, why, cfg = False, "pas de stockage", None
    else:
        cfg = latest_config()
        run, why = decide(cfg, last_run(), now)
        if run:
            mark_run(now)
    print(why)
    values = {"run": "true" if run else "false"}
    if run and cfg:
        values |= {"jeu": str(cfg.get("game") or "Grand Theft Auto VI")[:80],
                   "top": str(int(cfg.get("top", 8))),
                   "max_clips": str(max(1, min(10, int(cfg.get("max_clips", 3))))),
                   "min_views": str(max(0, int(cfg.get("min_views", 200)))),
                   "heures": str(max(1, min(720, int(cfg.get("hours", 48)))))}
    if out:
        with open(out, "a", encoding="utf-8") as f:
            for k, v in values.items():
                f.write(f"{k}={v.replace(chr(10), ' ')}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

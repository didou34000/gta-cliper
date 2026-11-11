"""Planification réglée depuis le site.

GitHub lance ce petit script toutes les 10 minutes (sans rien installer). Il lit le dernier
réglage enregistré par le site dans Vercel Blob (schedule/config-<ms>.json) et décide si
c'est l'heure d'un passage. Si oui, il note l'heure (schedule/last-run.json) et donne au
passage le jeu, le nombre de streamers et le nombre de clips choisis.

Uniquement la bibliothèque standard : il tourne avant l'installation des dépendances.
"""
from __future__ import annotations

import json
import os
import sys
import time
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


def list_schedule() -> list[dict]:
    q = urllib.parse.urlencode({"prefix": "schedule/", "limit": "1000"})
    return _req(f"{API}/?{q}").get("blobs", [])


def latest_config(blobs: list[dict]) -> dict | None:
    cfgs = sorted((b for b in blobs if b["pathname"].startswith("schedule/config-")),
                  key=lambda b: b["uploadedAt"])
    if not cfgs:
        return None
    with urllib.request.urlopen(cfgs[-1]["url"], timeout=30) as r:  # nom unique : pas de cache périmé
        return json.loads(r.read())


def last_run(blobs: list[dict]) -> datetime | None:
    for b in blobs:
        if b["pathname"] == "schedule/last-run.json":
            return datetime.fromisoformat(b["uploadedAt"].replace("Z", "+00:00"))
    return None


def mark_run(now: datetime) -> None:
    q = urllib.parse.urlencode({"pathname": "schedule/last-run.json"})
    _req(f"{API}/?{q}", method="PUT", data=json.dumps({"at": now.isoformat()}).encode(),
         headers={"x-vercel-blob-access": "public", "x-content-type": "application/json",
                  "x-add-random-suffix": "0", "x-allow-overwrite": "1",
                  "x-cache-control-max-age": "60"})


def decide(cfg: dict | None, last: datetime | None, now: datetime) -> tuple[bool, str]:
    if not cfg or not cfg.get("enabled"):
        return False, "programmation arrêtée sur le site"
    every = max(10, int(cfg.get("every_min", 30))) * 60
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
        blobs = list_schedule()
        cfg = latest_config(blobs)
        run, why = decide(cfg, last_run(blobs), now)
        if run:
            mark_run(now)
    print(why)
    values = {"run": "true" if run else "false"}
    if run and cfg:
        values |= {"jeu": str(cfg.get("game") or "Grand Theft Auto VI")[:80],
                   "top": str(int(cfg.get("top", 8))),
                   "max_clips": str(max(1, min(10, int(cfg.get("max_clips", 3))))),
                   "min_views": str(max(0, int(cfg.get("min_views", 200))))}
    if out:
        with open(out, "a", encoding="utf-8") as f:
            for k, v in values.items():
                f.write(f"{k}={v.replace(chr(10), ' ')}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Planification réglée depuis le site.

GitHub lance ce petit script toutes les 20 minutes (sans rien installer). Il lit le réglage
enregistré par le site dans le stockage R2 (schedule/config.json) et décide si c'est l'heure
d'un passage. Si oui, il note l'heure (schedule/last-run.json) et donne au passage le jeu,
le nombre de streamers et le nombre de clips choisis.

Coût par contrôle : 2 lectures (classe B), plus 1 écriture (classe A) seulement s'il lance
un passage. Aucun listage. Bibliothèque standard uniquement : il tourne avant l'installation
des dépendances.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from . import s3lite

TOLERANCE_S = 120  # GitHub déclenche souvent avec une ou deux minutes de retard


def _get_json(key: str) -> dict | None:
    raw = s3lite.get(key)
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def latest_config() -> dict | None:
    return _get_json("schedule/config.json")


def last_run() -> datetime | None:
    d = _get_json("schedule/last-run.json")
    try:
        return datetime.fromisoformat(d["at"].replace("Z", "+00:00")) if d else None
    except (KeyError, ValueError):
        return None


def mark_run(now: datetime) -> None:
    s3lite.put("schedule/last-run.json", json.dumps({"at": now.isoformat()}).encode(),
               "application/json")


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
    if not s3lite.configured():
        print("Clés R2 manquantes (R2_ACCOUNT_ID…) : programmation impossible")
        run, why, cfg = False, "pas de stockage", None
    else:
        try:
            cfg = latest_config()
            run, why = decide(cfg, last_run(), now)
            if run:
                mark_run(now)
        except Exception as e:  # dont le plafond du quota gratuit R2
            print(f"::warning::{e}")
            run, why, cfg = False, f"pas de passage : {e}", None
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

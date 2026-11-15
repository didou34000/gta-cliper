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

TOLERANCE_S = 120
# Sortie de GTA VI : premiers joueurs (Nouvelle-Zélande) le 18/11 vers 11 h UTC. Avant, la
# catégorie Twitch « Grand Theft Auto VI » ne contient que du GTA V / RP mal rangé : on ne
# lance rien (sinon des clips titrés « sur GTA 6 » montreraient en fait GTA V).
GTA6_RELEASE = datetime(2026, 11, 18, 10, 30, tzinfo=timezone.utc)


def before_gta6(game: str, now: datetime) -> bool:
    g = (game or "").lower()
    return now < GTA6_RELEASE and ("theft auto vi" in g or "gta 6" in g or "gta vi" in g)  # GitHub déclenche souvent avec une ou deux minutes de retard


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


PARIS = None


def _paris(now: datetime) -> datetime:
    global PARIS
    if PARIS is None:
        from zoneinfo import ZoneInfo
        PARIS = ZoneInfo("Europe/Paris")
    return now.astimezone(PARIS)


def in_window(h: float, start: int, end: int) -> bool:
    """h dans [start, end) ; une plage 22 → 3 passe minuit ; 0 → 24 = toute la journée."""
    if start == end or (start == 0 and end == 24):
        return True
    return start <= h < end if start < end else (h >= start or h < end)


def allowed(now: datetime, days, start: int, end: int) -> bool:
    p = _paris(now)
    h = p.hour + p.minute / 60
    day = (p.weekday() + 1) % 7  # 0 = dimanche, comme sur le site
    if start > end and h < end:  # après minuit dans une plage de nuit : c'est encore la veille
        day = (day + 6) % 7
    return in_window(h, start, end) and day in (days or range(7))


def every_at(cfg: dict, now: datetime) -> int:
    p = _paris(now)
    peak = int(cfg.get("peak_every_min") or 0)
    if peak and in_window(p.hour + p.minute / 60, int(cfg.get("peak_from", 18)), int(cfg.get("peak_to", 24))):
        return max(20, peak)
    return max(20, int(cfg.get("every_min", 30)))


def decide(cfg: dict | None, last: datetime | None, now: datetime) -> tuple[bool, str]:
    if not cfg or not cfg.get("enabled"):
        return False, "programmation arrêtée sur le site"
    if before_gta6(str(cfg.get("game") or "Grand Theft Auto VI"), now):
        return False, "en attente de la sortie de GTA VI (18/11 vers 11 h 30 heure de Paris)"
    if not allowed(now, cfg.get("days"), int(cfg.get("run_from", 0)), int(cfg.get("run_to", 24))):
        return False, (f"hors des horaires réglés ({int(cfg.get('run_from', 0))} h → "
                       f"{int(cfg.get('run_to', 24))} h, jours choisis)")
    every = every_at(cfg, now) * 60
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

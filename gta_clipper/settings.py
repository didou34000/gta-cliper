"""Lit ou change les réglages du site sans passer par le site (workflow « Réglages »).

Mêmes fichiers que le site : schedule/config.json (Programmation) et publish/state.json
(interrupteur « Publication auto »). Un champ laissé vide n'est pas modifié.
Coût : 3 lectures, et au plus 2 écritures si quelque chose change. Bibliothèque standard.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from . import s3lite

DEFAULTS = {"enabled": False, "every_min": 30, "game": "Grand Theft Auto VI", "top": 8,
            "max_clips": 3, "min_views": 200, "hours": 48, "publish_every_min": 120,
            "auto_min": 7}
INTS = {"every_min": (10, 360), "top": (1, 20), "max_clips": (1, 10), "min_views": (0, 100000),
        "hours": (1, 720), "publish_every_min": (10, 720), "auto_min": (0, 10)}
ON = ("on", "oui", "1", "true", "allumer", "allumée", "allume")
OFF = ("off", "non", "0", "false", "couper", "coupée", "coupe")


def _get(key: str) -> dict:
    raw = s3lite.get(key)
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        return {}


def _flag(v: str) -> bool | None:
    v = (v or "").strip().lower()
    return True if v in ON else False if v in OFF else None


def show_queue() -> None:
    """Affiche les clips dont la dernière décision est « approved » (ce que Buffer prendrait)."""
    latest: dict[str, str] = {}
    for o in s3lite.list_objects("decisions/"):
        parts = o["pathname"].split("/")
        if len(parts) == 3 and parts[2] > latest.get(parts[1], ""):
            latest[parts[1]] = parts[2]
    counts: dict[str, int] = {}
    for cid, f in sorted(latest.items()):
        st = _get(f"decisions/{cid}/{f}").get("status", "?")
        counts[st] = counts.get(st, 0) + 1
        if st == "approved":
            keys = [o["pathname"] for o in s3lite.list_objects(f"clips/{cid}/")
                    if o["pathname"].split("/")[-1].startswith("meta")]
            meta = _get(keys[0]) if keys else {}
            print(f"  À poster : {cid} · {meta.get('title') or meta.get('titre') or '?'} "
                  f"· jeu={meta.get('game') or meta.get('jeu') or '?'}")
    print("Décisions (dernier état par clip) :", counts)


def main() -> int:
    if not s3lite.configured():
        print("::error::Clés R2 manquantes")
        return 1
    now = datetime.now(timezone.utc).isoformat()
    cfg = {**DEFAULTS, **_get("schedule/config.json")}
    pub = _get("publish/state.json")
    last = _get("schedule/last-run.json")
    print("Avant :", json.dumps({"programmation": cfg, "publication": pub, "dernier_passage": last},
                                ensure_ascii=False))

    if os.environ.get("SHOW_QUEUE", "1") != "0":
        show_queue()

    new = dict(cfg)
    prog = _flag(os.environ.get("SET_PROGRAMMATION", ""))
    if prog is not None:
        new["enabled"] = prog
    lang = os.environ.get("SET_LANGUE", "").strip().lower()
    if lang in ("fr", "en", "es", "pt", "de", "it", "ja", "ko", "any"):
        new["lang"] = lang
    game = os.environ.get("SET_JEU", "").strip()
    if game:
        new["game"] = game[:80]
    jours = os.environ.get("SET_JOURS", "").strip().lower()
    if jours:
        if jours in ("tous", "all", "*"):
            new["days"] = list(range(7))
        else:
            names = {"dim": 0, "lun": 1, "mar": 2, "mer": 3, "jeu": 4, "ven": 5, "sam": 6}
            ds = sorted({names.get(x.strip()[:3], int(x) if x.strip().isdigit() else -1)
                         for x in jours.split(",")} & set(range(7)))
            if ds:
                new["days"] = ds
    for k, (lo, hi) in INTS.items():
        v = os.environ.get(f"SET_{k.upper()}", "").strip()
        if v.isdigit():
            new[k] = max(lo, min(hi, int(v)))
    new.pop("at", None)
    old = {k: v for k, v in cfg.items() if k != "at"}
    if new != old:
        s3lite.put("schedule/config.json", json.dumps({**new, "at": now}).encode(),
                   "application/json")
        print("Programmation enregistrée :", json.dumps(new, ensure_ascii=False))

    p = _flag(os.environ.get("SET_PUBLICATION", ""))
    if p is not None and p != bool(pub.get("enabled")):
        s3lite.put("publish/state.json", json.dumps({"enabled": p, "at": now}).encode(),
                   "application/json")
        print("Publication auto :", "allumée" if p else "coupée")
    return 0


if __name__ == "__main__":
    sys.exit(main())

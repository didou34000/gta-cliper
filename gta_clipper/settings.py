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
INTS = {"every_min": (20, 360), "top": (1, 20), "max_clips": (1, 10), "min_views": (0, 100000),
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

    new = dict(cfg)
    prog = _flag(os.environ.get("SET_PROGRAMMATION", ""))
    if prog is not None:
        new["enabled"] = prog
    game = os.environ.get("SET_JEU", "").strip()
    if game:
        new["game"] = game[:80]
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

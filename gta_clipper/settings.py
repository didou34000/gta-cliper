"""Lit ou change les réglages du site sans passer par le site (workflow « Réglages »).

Mêmes fichiers que le site : schedule/config.json (Programmation) et publish/state.json
(interrupteur « Publication auto »). Un champ laissé vide n'est pas modifié.
Coût : 3 lectures, et au plus 2 écritures si quelque chose change. Bibliothèque standard.
"""
from __future__ import annotations

import json
import time
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


def show_queue() -> list[str]:
    """Affiche les clips dont la dernière décision est « approved » (ce que Buffer prendrait)."""
    queue: list[str] = []
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
                  f"· note={meta.get('click_score') or meta.get('potential') or '?'}/10 "
                  f"· streamer={meta.get('streamer') or '?'}")
            queue.append(cid)
    print("Décisions (dernier état par clip) :", counts)
    return queue


def show_today() -> None:
    """Liste les clips montés aujourd'hui (UTC) : streamer, vues, note, raison, titre, vidéo."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    day = now.strftime("%Y%m%d")
    yday = (now - timedelta(days=1)).strftime("%Y%m%d")
    metas = [o for p in (yday, day) for o in s3lite.list_objects(f"clips/{p}")
             if o["pathname"].split("/")[-1].startswith("meta")]
    print(f"Clips montés hier et aujourd'hui ({yday}-{day}) : {len(metas)} (hier : seulement ≥ 1000 vues)")
    for o in sorted(metas, key=lambda o: o["pathname"]):
        m = _get(o["pathname"])
        if o["pathname"].split("/")[1].startswith(yday) and (m.get("views") or 0) < 1000:
            continue
        print(f"  {o['pathname'].split('/')[1]} · {m.get('streamer', '?')} · {m.get('views', '?')} vues "
              f"· note {m.get('click_score', '?')}/10 (Haiku {m.get('click_score_haiku', '-')}) "
              f"· {m.get('click_reason', '')} · « {m.get('title', '')} » · {m.get('video_url', '')}")


def unqueue(ids: list[str]) -> None:
    """Remet des clips « À poster » en « À valider » (rien n'est supprimé, réversible sur le site)."""
    for cid in ids:
        s3lite.put(f"decisions/{cid}/{int(time.time() * 1000)}.json",
                   json.dumps({"status": "pending", "reason": "retiré de la file (Réglages)",
                               "at": datetime.now(timezone.utc).isoformat()}).encode(),
                   "application/json")
        print(f"  Retiré de la file : {cid}")


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

    queue = show_queue() if os.environ.get("SHOW_QUEUE", "1") != "0" else []
    if os.environ.get("SHOW_TODAY", "1") != "0":
        try:
            show_today()
        except Exception as e:
            print("Liste du jour illisible :", e)
    out = os.environ.get("SET_RETIRER", "").strip()
    if out:
        unqueue(queue if out.lower() in ("tout", "all", "*") else
                [x.strip() for x in out.split(",") if x.strip() in queue])

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

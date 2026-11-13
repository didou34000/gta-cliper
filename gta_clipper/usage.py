"""Relevé précis de la consommation d'un passage du bot.

Compté pendant le passage (rien n'est estimé ici) :
- opérations Cloudflare R2 : classe A (envois, listages, suppressions) et classe B (lectures) ;
- appels à Claude : nombre, jetons d'entrée/sortie, coût en dollars au tarif public ;
- clips fabriqués, durée du passage.

À la fin du passage, le relevé est ajouté au registre du mois sur R2
(usage/AAAA-MM.json, un seul fichier réécrit : 1 lecture + 1 écriture par passage).
Le site lit ce fichier pour la page « Consommation ».
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone

log = logging.getLogger("gta_clipper")

# Tarifs publics Anthropic en $ par million de jetons (entrée, sortie), novembre 2026.
# Haiku 5.5 : tarif des requêtes de moins de 100 000 jetons (toujours le cas ici).
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}

RUN = {
    "r2_a": 0, "r2_b": 0,
    "llm_calls": 0, "llm_in": 0, "llm_out": 0, "llm_usd": 0.0,
    "clips": 0, "started": time.time(),
}


def r2(op_class: str) -> None:
    RUN["r2_a" if op_class == "A" else "r2_b"] += 1


def llm(model: str, resp) -> None:
    """À appeler après chaque réponse de Claude (resp.usage)."""
    try:
        u = resp.usage
        tin = (u.input_tokens or 0) + (getattr(u, "cache_creation_input_tokens", 0) or 0)
        cached = getattr(u, "cache_read_input_tokens", 0) or 0
        tout = u.output_tokens or 0
    except Exception:
        return
    pin, pout = PRICES.get(model, PRICES["claude-sonnet-5-5"])
    RUN["llm_calls"] += 1
    RUN["llm_in"] += tin + cached
    RUN["llm_out"] += tout
    RUN["llm_usd"] += (tin * pin + cached * pin * 0.1 + tout * pout) / 1e6


def clip_done() -> None:
    RUN["clips"] += 1


def snapshot() -> dict:
    d = dict(RUN)
    d["seconds"] = int(time.time() - d.pop("started"))
    d["llm_usd"] = round(d["llm_usd"], 5)
    return d


def save_run(kind: str, status: str) -> dict:
    """Ajoute le relevé de ce passage au registre du mois sur R2. Ne bloque jamais le bot."""
    from . import s3lite
    rec = snapshot() | {"at": datetime.now(timezone.utc).isoformat(), "kind": kind,
                        "status": status, "gh_run": os.environ.get("GITHUB_RUN_ID", "")}
    if not s3lite.configured():
        return rec
    key = f"usage/{datetime.now(timezone.utc):%Y-%m}.json"
    try:
        raw = s3lite.get(key)
        book = json.loads(raw) if raw else {"runs": []}
        rec["r2_a"] += 1  # l'écriture ci-dessous
        rec["r2_b"] += 1  # la lecture ci-dessus
        book["runs"] = (book.get("runs") or [])[-499:] + [rec]
        s3lite.put(key, json.dumps(book, ensure_ascii=False).encode(), "application/json")
        log.info("Consommation du passage : %d opérations R2 (A) / %d (B), %d appel(s) Claude "
                 "(%.4f $), %d clip(s), %d s", rec["r2_a"], rec["r2_b"], rec["llm_calls"],
                 rec["llm_usd"], rec["clips"], rec["seconds"])
    except Exception as e:
        log.warning("Relevé de consommation non enregistré : %s", e)
    return rec

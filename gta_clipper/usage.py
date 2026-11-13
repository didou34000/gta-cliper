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


# --- Plafond dur : on ne dépasse JAMAIS le quota gratuit de Cloudflare R2 -----------------
# Quota gratuit par mois : 1 000 000 opérations A, 10 000 000 opérations B. On s'arrête à
# la moitié (réglable par R2_MAX_A / R2_MAX_B) : au-delà, toute opération est refusée et le
# passage s'arrête proprement. Le total du mois (bot + site) est tenu dans
# usage/total-AAAA-MM.json, mis à jour à la fin de chaque passage et par le site.
FREE_A, FREE_B = 1_000_000, 10_000_000
MAX_A = int(os.environ.get("R2_MAX_A") or FREE_A // 2)
MAX_B = int(os.environ.get("R2_MAX_B") or FREE_B // 2)
_BASE: dict | None = None  # total du mois au début du passage
_LOADING = False


class BudgetExceeded(RuntimeError):
    pass


def total_key() -> str:
    return f"usage/total-{datetime.now(timezone.utc):%Y-%m}.json"


def _base() -> dict:
    """Total du mois lu une fois au premier appel (1 lecture B, comptée)."""
    global _BASE, _LOADING
    if _BASE is None and not _LOADING:
        _LOADING = True
        try:
            from . import s3lite
            raw = s3lite.get(total_key())
            d = json.loads(raw) if raw else {}
            _BASE = {"a": int(d.get("a", 0)), "b": int(d.get("b", 0))}
        except Exception as e:  # illisible : on reste prudent sans bloquer pour autant
            log.warning("Total R2 du mois illisible (%s) : plafond calculé sur ce passage seul", e)
            _BASE = {"a": 0, "b": 0}
        finally:
            _LOADING = False
    return _BASE or {"a": 0, "b": 0}


def check_budget(op_class: str) -> None:
    """Appelé AVANT chaque opération R2. Lève BudgetExceeded si le plafond est atteint."""
    if _LOADING:
        return
    b = _base()
    if op_class == "A" and b["a"] + RUN["r2_a"] >= MAX_A:
        raise BudgetExceeded(f"Plafond R2 atteint : {b['a'] + RUN['r2_a']:,} opérations A ce mois-ci "
                             f"(limite fixée à {MAX_A:,} sur {FREE_A:,} gratuites). Plus aucun envoi "
                             f"jusqu'au 1er du mois prochain.")
    if op_class == "B" and b["b"] + RUN["r2_b"] >= MAX_B:
        raise BudgetExceeded(f"Plafond R2 atteint : {b['b'] + RUN['r2_b']:,} opérations B ce mois-ci "
                             f"(limite {MAX_B:,} sur {FREE_B:,} gratuites).")


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
        # Total du mois (bot + site) servant au plafond : relu juste avant pour limiter les
        # écarts si le site l'a mis à jour pendant le passage.
        raw_t = s3lite.get(total_key())
        t = json.loads(raw_t) if raw_t else {}
        rec["r2_a"] += 1
        rec["r2_b"] += 1
        t = {"a": int(t.get("a", 0)) + rec["r2_a"], "b": int(t.get("b", 0)) + rec["r2_b"],
             "at": rec["at"]}
        s3lite.put(total_key(), json.dumps(t).encode(), "application/json")
        log.info("Consommation du passage : %d opérations R2 (A) / %d (B), %d appel(s) Claude "
                 "(%.4f $), %d clip(s), %d s", rec["r2_a"], rec["r2_b"], rec["llm_calls"],
                 rec["llm_usd"], rec["clips"], rec["seconds"])
    except Exception as e:
        log.warning("Relevé de consommation non enregistré : %s", e)
    return rec

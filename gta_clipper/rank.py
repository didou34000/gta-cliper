"""Présélection rapide et bon marché des clips candidats avant le montage.

Claude Haiku regarde, pour chaque candidat, la miniature Twitch, le titre donné par le viewer,
les vues, la durée et le streamer, puis note son potentiel en format court (TikTok/Shorts).
On ne monte ensuite que les meilleurs : moins de minutes de calcul, et les meilleurs en premier.
Coût : une seule requête par passage, de l'ordre d'un dixième de centime.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

SYSTEM = """Tu sélectionnes des clips Twitch de streamers français à republier en format \
court (TikTok, YouTube Shorts, Reels). Pour chaque candidat tu as la miniature, le titre écrit \
par le viewer qui a fait le clip, les vues, la durée et le streamer.

Note le potentiel viral de 1 à 10 : un moment fort compréhensible sans contexte (action \
folle, fou rire, rage, découverte, fail, moment émouvant, réplique culte) vaut plus qu'un \
passage calme, un écran de chargement, un menu ou un moment qui demande trop de contexte. \
Les vues comptent mais ne décident pas tout. Un titre vide ou générique ("clip", le titre \
du live) n'est pas un mauvais signe en soi : juge surtout sur l'image et l'ensemble. \
Donne une raison courte (10 mots max) par clip."""


class Score(BaseModel):
    n: int = Field(description="Numéro du candidat")
    score: int = Field(description="Potentiel de 1 à 10")
    raison: str = Field(description="Raison courte, 10 mots max")


class Ranking(BaseModel):
    scores: list[Score]


def _fetch_thumb(url: str) -> str:
    """Miniature Twitch en base64. On la télécharge nous-mêmes : l'API Anthropic refuse
    de la récupérer par URL (robots.txt de Twitch)."""
    if not url:
        return ""
    try:
        import base64
        import requests
        r = requests.get(url, timeout=10)
        if r.ok and r.headers.get("content-type", "").startswith("image/jpeg") and len(r.content) < 2_000_000:
            return base64.b64encode(r.content).decode()
    except Exception as e:
        log.info("Miniature indisponible (%s) : %s", url[:80], e)
    return ""


def rank_candidates(cands: list[dict], game: str = "", model: str = "claude-haiku-5-5") -> list[dict]:
    """Ajoute 'score' et 'raison' à chaque candidat et renvoie la liste triée (meilleur d'abord).

    En cas d'échec (pas de clé, panne, plafond), garde l'ordre par vues sans planter.
    """
    import os
    if len(cands) <= 1 or not os.environ.get("ANTHROPIC_API_KEY"):
        return cands
    from .guard import Guard
    if not Guard.get().allow_llm():
        return cands
    import anthropic
    content: list = [{"type": "text", "text": f"Jeu : {game or '(divers)'}. "
                      f"{len(cands)} candidats :"}]
    for i, c in enumerate(cands):
        content.append({"type": "text", "text":
                        f"[{i}] {c['streamer']} · {c['views']} vues · {c['duration']:.0f} s · "
                        f"titre : {c['title'] or '(vide)'}"})
        img = _fetch_thumb(c.get("thumb", ""))
        if img:
            content.append({"type": "image", "source": {
                "type": "base64", "media_type": "image/jpeg", "data": img}})
    try:
        client = anthropic.Anthropic(max_retries=2, timeout=60)
        resp = client.messages.parse(
            model=model, max_tokens=2000, system=SYSTEM,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": content}],
            output_format=Ranking,
        )
        scores = {s.n: s for s in (resp.parsed_output.scores if resp.parsed_output else [])}
    except Exception as e:  # miniature introuvable, panne… : on garde l'ordre par vues
        log.warning("Présélection IA impossible : %s", e)
        return cands
    for i, c in enumerate(cands):
        s = scores.get(i)
        c["score"] = max(1, min(10, s.score)) if s else 0
        c["raison"] = s.raison[:80] if s else ""
    # Le potentiel d'abord ; à égalité, les vues.
    return sorted(cands, key=lambda c: (c.get("score", 0), c["views"]), reverse=True)

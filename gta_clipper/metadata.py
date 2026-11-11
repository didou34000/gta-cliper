"""Titre, description et hashtags générés par Claude à partir de la transcription."""
from __future__ import annotations

import anthropic
from pydantic import BaseModel, Field

FALLBACK_MODEL = "claude-opus-4-8"

SYSTEM = """Tu écris les métadonnées de clips courts (TikTok, YouTube Shorts, Reels) \
pour une page de clips de streamers français qui découvrent GTA VI.

Règles du titre :
- Format accrocheur centré sur le streamer et l'action : "Squeezie découvre le manoir", \
"Gotaga se fait braquer en 10 secondes", "ZeratoR tombe sur le pire PNJ du jeu".
- 70 caractères max, en français naturel, sans guillemets, 0 ou 1 emoji.
- Le titre doit décrire ce qui se passe VRAIMENT dans la transcription. \
N'invente pas d'événement, de lieu ou de réaction absents du contenu. \
Si la transcription est trop pauvre pour savoir ce qui se passe, reste général \
("Squeezie réagit à sa première mission sur GTA 6") et mets confidence à "low".
- Pas de faux clickbait ("il a quitté le stream !!!") si ce n'est pas dans le clip.

Description : 1 à 2 phrases, ton naturel, mentionne le streamer et GTA 6, \
termine par une incitation légère (ex. "Abonne-toi pour plus de clips GTA 6").

Hashtags : 5 à 8, pertinents, en commençant par ceux du jeu et du streamer."""


class ClipMetadata(BaseModel):
    title: str = Field(description="Titre accrocheur, 70 caractères max")
    alt_titles: list[str] = Field(description="2 titres alternatifs")
    description: str
    hashtags: list[str] = Field(description="Hashtags avec #")
    confidence: str = Field(description="high | medium | low : à quel point le titre colle au contenu")


def generate_metadata(streamer_name: str, transcript: str, twitch_title: str = "",
                      model: str = "claude-opus-5-5",
                      base_hashtags: list[str] | None = None) -> ClipMetadata:
    from .guard import Guard, LimitReached
    client = anthropic.Anthropic(max_retries=2, timeout=90)
    transcript = (transcript or '')[:4000]  # un clip fait 60 s max : borne de sécurité
    user = (
        f"Streamer : {streamer_name}\n"
        f"Titre donné au clip sur Twitch par un viewer (peut être vide ou approximatif) : "
        f"{twitch_title or '(aucun)'}\n\n"
        f"Transcription du clip (auto, peut contenir des erreurs) :\n<transcription>\n"
        f"{transcript or '(pas de parole détectée)'}\n</transcription>"
    )
    meta = None
    for m in (model, FALLBACK_MODEL):
        if not Guard.get().allow_llm():
            raise LimitReached("Plafond quotidien d'appels à l'IA atteint")
        resp = client.messages.parse(
            model=m,
            max_tokens=1500,
            system=SYSTEM,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": user}],
            output_format=ClipMetadata,
        )
        if resp.stop_reason == "refusal":
            continue  # on retente sur le modèle de secours
        meta = resp.parsed_output
        break
    if meta is None:
        raise RuntimeError("Le modèle a refusé de générer les métadonnées pour ce clip.")

    tags = list(dict.fromkeys((base_hashtags or []) + [
        t if t.startswith("#") else f"#{t}" for t in meta.hashtags
    ]))
    meta.hashtags = tags[:10]
    meta.title = meta.title.strip().strip('"')[:100]
    return meta

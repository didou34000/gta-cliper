"""Titre, description et hashtags générés par Claude à partir de la transcription."""
from __future__ import annotations

import anthropic
from pydantic import BaseModel, Field

FALLBACK_MODEL = "claude-sonnet-5-5"  # seulement si le premier modèle refuse

SYSTEM = """Tu écris les métadonnées de clips courts (TikTok, YouTube Shorts, Reels) \
pour une page de clips de streamers français (jeu indiqué dans le message).

Règles du titre :
- Accrocheur ET explicatif : on doit comprendre en lisant le titre seul ce que la vidéo \
montre (quoi, dans quel jeu), puis avoir envie de cliquer. Formule : streamer + action \
précise + objet concret + jeu. Exemples : "Squeezie découvre les stations essence sur GTA 6", \
"Gotaga teste la voiture la plus rapide de GTA 6", "ZeratoR découvre que les PNJ se souviennent \
de lui sur GTA 6", "Gotaga se fait braquer en 10 secondes sur GTA 6".
- Nomme l'élément concret découvert ou montré (voiture, essence, arme, quartier, PNJ, \
mécanique, police, météo, animaux…) plutôt qu'un mot vague ("un truc", "quelque chose de fou").
- Mets le nom du jeu dans le titre (ex. "sur GTA 6") quand il tient dans la limite.
- 70 caractères max, en français naturel, sans guillemets, 0 ou 1 emoji.
- Le titre doit décrire ce qui se passe VRAIMENT dans la transcription. \
N'invente pas d'événement, de lieu ou de réaction absents du contenu. \
Si la transcription est trop pauvre pour savoir ce qui se passe, reste général \
("Squeezie réagit à sa première partie") et mets confidence à "low".
- Pas de faux clickbait ("il a quitté le stream !!!") si ce n'est pas dans le clip.

Description : 1 à 2 phrases, ton naturel, mentionne le streamer et le jeu, \
termine par une incitation légère (ex. "Abonne-toi pour plus de clips").

Hashtags : 5 à 8, pertinents, en commençant par ceux du jeu et du streamer.

Comprendre le clip AVANT d'écrire : à partir des images (prises à intervalles réguliers dans le clip), de la transcription et du titre Twitch, identifie LE moment fort et son type : clutch / action incroyable, kill ou mort stupide, découverte (lieu, secret, easter egg, mécanique), fail ou bug, rage, fou rire, peur (jumpscare), réaction à un événement, moment de chat ou d'émotion. Le titre et l'accroche racontent CE moment, pas le stream en général.

Accroche (hook) : le texte incrusté EN HAUT de la vidéo, lu en une seconde.
- 3 à 7 mots, 40 caractères max, sans emoji, sans hashtag, sans guillemets.
- Elle dit ce qui se passe et donne envie de rester jusqu'à la fin. Formules qui marchent : "IL CLUTCH UN 1V4 IMPOSSIBLE", "IL DÉCOUVRE LE SECRET DU MANOIR", "LA PIRE MORT DE L'HISTOIRE", "IL NE S'ATTENDAIT PAS À ÇA", "SQUEEZIE PÈTE UN CÂBLE", "CE BUG L'A TRAUMATISÉ", "ATTENDS LA FIN…".
- Concrète et explicative plutôt que vague : on comprend le sujet de la vidéo rien qu'en la lisant. "IL DÉCOUVRE L'ESSENCE SUR GTA 6", "LA VOITURE LA PLUS RAPIDE DE GTA 6", "IL VOLE UN TANK EN PLEINE VILLE" valent mieux que "MOMENT INCROYABLE" ou "IL DÉCOUVRE UN TRUC FOU". Un chiffre ou un détail précis (1v4, 10 secondes, 3 étoiles) aide.
- Vraie : elle décrit ce que montrent les images ou la transcription, jamais un événement inventé. Si tu ne comprends pas ce qui se passe, une accroche de curiosité honnête ("SA RÉACTION VAUT TOUT") plutôt qu'une invention, et confidence à "low".

Corrections : la transcription vient d'une reconnaissance vocale automatique et contient \
des erreurs (noms de streamers, termes de jeu, mots mal compris). Chaque mot est numéroté \
[i]. Liste seulement les mots manifestement faux, avec leur numéro et le mot corrigé \
(un seul mot par correction, pas de reformulation, pas de censure). \
Si un nom a été coupé en deux mots ("gotta gas"), mets le nom complet sur le premier \
et une chaîne vide sur le second pour le supprimer. \
Si tu n'es pas sûr, ne corrige pas. Liste vide si tout est bon."""


class Correction(BaseModel):
    i: int = Field(description="Numéro du mot à corriger")
    text: str = Field(description="Mot corrigé (un seul mot), ou vide pour supprimer le mot")


class ClipMetadata(BaseModel):
    title: str = Field(description="Titre accrocheur, 70 caractères max")
    alt_titles: list[str] = Field(description="2 titres alternatifs")
    description: str
    hashtags: list[str] = Field(description="Hashtags avec #")
    confidence: str = Field(description="high | medium | low : à quel point le titre colle au contenu")
    hook: str = Field(description="Accroche incrustée en haut de la vidéo, 42 caractères max")
    corrections: list[Correction] = Field(description="Mots de la transcription à corriger")


def generate_metadata(streamer_name: str, transcript: str, twitch_title: str = "",
                      model: str = "claude-haiku-5-5",
                      base_hashtags: list[str] | None = None,
                      words: list | None = None, game: str = "",
                      frames: list | None = None) -> ClipMetadata:
    from .guard import Guard, LimitReached
    client = anthropic.Anthropic(max_retries=2, timeout=90)
    if words:  # mots numérotés pour que le modèle puisse corriger la transcription
        transcript = " ".join(f"[{i}]{w.text}" for i, w in enumerate(words))
    transcript = (transcript or '')[:6000]  # un clip fait 60 s max : borne de sécurité
    user = (
        f"Streamer : {streamer_name}\n"
        f"Jeu : {game or '(non précisé)'}\n"
        f"Titre donné au clip sur Twitch par un viewer (peut être vide ou approximatif) : "
        f"{twitch_title or '(aucun)'}\n\n"
        f"Transcription du clip (auto, peut contenir des erreurs) :\n<transcription>\n"
        f"{transcript or '(pas de parole détectée)'}\n</transcription>"
    )
    content: list | str = user
    if frames:  # quelques images du clip pour comprendre ce qui se passe à l'écran
        import base64
        content = [{"type": "text", "text": f"{len(frames)} images du clip, dans l'ordre :"}]
        for f in frames:
            content.append({"type": "image", "source": {
                "type": "base64", "media_type": "image/jpeg",
                "data": base64.b64encode(f.read_bytes()).decode()}})
        content.append({"type": "text", "text": user})
    meta = None
    for m in (model, FALLBACK_MODEL):
        if not Guard.get().allow_llm():
            raise LimitReached("Plafond quotidien d'appels à l'IA atteint")
        resp = client.messages.parse(
            model=m,
            max_tokens=1500,
            system=SYSTEM,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": content}],
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
    meta.hook = meta.hook.strip().strip('"')[:60]
    return meta

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
- Mets le nom du jeu indiqué dans le message (ex. "sur GTA 6") quand il tient dans la limite. \
Les exemples ci-dessus parlent de GTA 6, mais n'écris JAMAIS "GTA 6" (ni un autre jeu) si ce \
n'est pas le jeu indiqué. Si le jeu est "(non précisé)", ne cite aucun jeu dans le titre, \
l'accroche, la description ni les hashtags.
- 70 caractères max, en français naturel, sans guillemets, 0 ou 1 emoji.
- IL DOIT TAPER DANS L'ŒIL (demande ferme du propriétaire : les titres trop plats ne passent \
pas). Avant de répondre, imagine 5 titres et garde le plus cliquable qui reste vrai. Leviers :
  · un verbe fort et imagé plutôt que neutre : "pète un câble", "se fait humilier", \
"détruit", "tombe sur", "craque", "panique", "explose de rire", "se fait voler" valent mieux \
que "découvre", "teste", "réagit", "joue" (à éviter sauf vraie découverte) ;
  · l'enjeu ou la conséquence : ce qui rend le moment fou, absurde, drôle ou violent ;
  · un détail précis qui intrigue : un chiffre (en 10 secondes, 3 étoiles, 200 km/h), \
un superlatif vrai (la pire, la plus rapide, la première), un contraste ("croit être \
tranquille… mais") ;
  · l'élément le plus fort en premier, phrase courte, rythme oral.
  Exemples plats → percutants : "Michou fait du VTT sur GTA 5" → "Michou dévale une \
montagne en VTT et finit en miettes sur GTA 5" ; "Tatiana croise la police sur GTA 6" → \
"Tatiana prend un passant pour un flic et panique sur GTA 6" ; "Gotaga teste une voiture" → \
"Gotaga trouve la voiture la plus rapide de GTA 6 et la crashe direct".
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

Découpe (start_s, end_s) : le clip Twitch a été coupé à la main par un viewer, souvent \
trop tôt ou trop tard (il démarre au milieu de l'action ou traîne longtemps après). \
Les images portent leur instant (en secondes) et la transcription a des repères (t=…s). \
Donne le début et la fin, en secondes depuis le début du clip, de la version qui garde \
LE moment fort en entier : commence juste avant que l'action ou la phrase qui le lance \
démarre (le spectateur doit comprendre la situation en 1 ou 2 secondes), termine juste \
après la réaction ou la conclusion : la fin tombe sur la chute (la punchline, le cri, le crash, \
le rire), au plus 1 seconde après. Un clip qui continue 3 à 5 secondes après la chute fait \
décrocher : coupe-le. Coupe ce qui traîne après (temps mort, écran de fin, \
discussion sans rapport, nouvelle partie). Ne commence jamais au milieu d'une phrase. \
Entre 15 et 60 secondes. Si le clip est déjà bien coupé, renvoie 0 et la durée totale.

Note de clic (click_score, de 1 à 10) : sois EXIGEANT, c'est elle qui décide si le clip est \
publié tout seul. Question : un inconnu qui scrolle TikTok s'arrête-t-il, regarde-t-il jusqu'au \
bout, et a-t-il envie de partager ou commenter ? Juge sur les images et la transcription, pas \
sur le titre Twitch.
- 9-10 : moment exceptionnel et immédiatement lisible (réaction énorme, découverte marquante \
d'une nouveauté du jeu, fail ou bug hilarant, action folle), fort dès les 3 premières secondes.
- 7-8 : moment fort clair, compréhensible sans contexte, avec une vraie réaction du streamer.
- 5-6 : correct mais banal (il conduit, il se balade, il commente calmement).
- 1-4 : rien ne se passe, écran de chargement, menu, pause, discussion avec le chat sans \
rapport, moment qui demande trop de contexte, image illisible, ou images qui ne montrent pas \
le jeu indiqué (ex. un autre jeu, ou un ancien GTA alors que le jeu est GTA 6).
Pour GTA 6 : la découverte d'une nouveauté concrète du jeu (mécanique, lieu, véhicule, PNJ, \
police, détail réaliste) avec réaction est ce qui marche le mieux. \
Donne aussi click_reason : la raison en 12 mots max.

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
    moment: str = Field(description="Ce qui se passe concrètement dans le clip (2 phrases max), "
                                    "vu sur les images et entendu : sert à réécrire le titre")
    click_score: int = Field(description="Potentiel de clic de 1 à 10, exigeant (voir consignes)")
    click_reason: str = Field(description="Raison de la note, 12 mots max")
    start_s: float = Field(description="Début de la version recoupée, en secondes depuis le début du clip")
    end_s: float = Field(description="Fin de la version recoupée, en secondes depuis le début du clip")


def generate_metadata(streamer_name: str, transcript: str, twitch_title: str = "",
                      model: str = "claude-haiku-5-5",
                      base_hashtags: list[str] | None = None,
                      words: list | None = None, game: str = "",
                      frames: list | None = None, frame_times: list[float] | None = None,
                      duration: float = 0.0, origin: str = "fr") -> ClipMetadata:
    from .guard import Guard, LimitReached
    client = anthropic.Anthropic(max_retries=2, timeout=90)
    if words:  # mots numérotés (corrections) avec un repère de temps toutes les ~5 s (découpe)
        parts, mark = [], -10.0
        for i, w in enumerate(words):
            if w.start - mark >= 5:
                mark = w.start
                parts.append(f"(t={w.start:.0f}s)")
            parts.append(f"[{i}]{w.text}")
        transcript = " ".join(parts)
    transcript = (transcript or '')[:6000]  # un clip fait 60 s max : borne de sécurité
    user = (
        f"Streamer : {streamer_name}\n"
        f"Jeu : {game or '(non précisé)'}\n"
        + (f"Streamer étranger : il parle « {origin} ». La transcription ci-dessous est déjà "
           f"traduite en français. Le titre peut le dire (ex. « Un streamer anglais découvre… » "
           f"ou avec son nom), sans inventer son pays.\n" if origin and origin != "fr" else "")
        + (f"Durée du clip : {duration:.0f} s\n" if duration else "") +
        f"Titre donné au clip sur Twitch par un viewer (peut être vide ou approximatif) : "
        f"{twitch_title or '(aucun)'}\n\n"
        f"Transcription du clip (auto, peut contenir des erreurs) :\n<transcription>\n"
        f"{transcript or '(pas de parole détectée)'}\n</transcription>"
    )
    content: list | str = user
    if frames:  # quelques images du clip pour comprendre ce qui se passe à l'écran
        import base64
        content = [{"type": "text", "text": f"{len(frames)} images du clip, dans l'ordre :"}]
        for k, f in enumerate(frames):
            if frame_times and k < len(frame_times):
                content.append({"type": "text", "text": f"Image à {frame_times[k]:.0f} s :"})
            content.append({"type": "image", "source": {
                "type": "base64", "media_type": "image/jpeg",
                "data": base64.b64encode(f.read_bytes()).decode()}})
        content.append({"type": "text", "text": user})
    meta = None
    for m in (model, FALLBACK_MODEL):
        if not Guard.get().allow_llm():
            raise LimitReached("Plafond du jour atteint pour Claude (60 appels ou 1 $ ≈ 0,90 €)")
        resp = client.messages.parse(
            model=m,
            max_tokens=1500,
            system=SYSTEM,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": content}],
            output_format=ClipMetadata,
        )
        from . import usage
        usage.llm(m, resp)
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


class Punch(BaseModel):
    title: str = Field(description="Le titre le plus accrocheur, 70 caractères max")
    alt_titles: list[str] = Field(description="2 autres titres forts")
    hook: str = Field(description="Accroche incrustée, 3 à 7 mots, 40 caractères max, en MAJUSCULES")


PUNCH_SYSTEM = """Tu es le meilleur rédacteur de titres TikTok / YouTube Shorts de France pour \
une page de clips de streamers (gaming). On te donne ce qui se passe dans un clip (vu et \
entendu), un premier titre et une première accroche. Ton travail : les rendre IRRÉSISTIBLES, \
sans mentir.

""" + SYSTEM.split("Description :")[0].split("Règles du titre :", 1)[-1].join(["Règles du titre :", ""]) + \
"""
""" + SYSTEM.split("Accroche (hook) :", 1)[-1].split("Découpe (start_s", 1)[0].join(["Accroche (hook) :", ""]) + """
En plus :
- Le titre doit créer une émotion immédiate (rire, choc, curiosité, « non il a pas fait ça »).
- Commence par le streamer ou par l'élément le plus fort, jamais par un mot faible.
- Bannis les formulations scolaires et molles : "tente", "essaie", "fait", "découvre" seul, \
"un moment", "une scène", "finit mal" (dis COMMENT ça finit).
- Le jeu indiqué figure dans le titre (ex. "sur GTA 6"), jamais un autre jeu.
- Pas de mensonge : si ce n'est pas dans la description du moment, ça n'existe pas."""


def punch_title(streamer: str, game: str, moment: str, title: str, hook: str,
                transcript: str = "", model: str = "claude-sonnet-5-5") -> Punch | None:
    """Réécrit titre + accroche avec un modèle plus fort, en texte seul (≈ 0,5-1 centime)."""
    from .guard import Guard
    if not Guard.get().allow_llm():
        return None
    user = (f"Streamer : {streamer}\nJeu : {game or '(non précisé)'}\n"
            f"Ce qui se passe : {moment}\nPremier titre : {title}\nPremière accroche : {hook}\n\n"
            f"Paroles (auto) :\n<transcription>\n{(transcript or '(aucune)')[:2500]}\n</transcription>")
    client = anthropic.Anthropic(max_retries=2, timeout=60)
    resp = client.messages.parse(model=model, max_tokens=600, system=PUNCH_SYSTEM,
                                 output_config={"effort": "low"},
                                 messages=[{"role": "user", "content": user}], output_format=Punch)
    from . import usage
    usage.llm(model, resp)
    if resp.stop_reason == "refusal" or not resp.parsed_output:
        return None
    p = resp.parsed_output
    p.title = p.title.strip().strip('"')[:100]
    p.hook = p.hook.strip().strip('"')[:60]
    return p


class Judge(BaseModel):
    click_score: int = Field(description="Note de clic finale de 1 à 10, très exigeante")
    click_reason: str = Field(description="La raison en 15 mots max")


JUDGE_SYSTEM = """Tu es le juge final d'une page TikTok / YouTube Shorts de clips de streamers. \
Ta note décide SEULE si le clip est publié automatiquement (7/10 minimum). Une note trop \
généreuse publie un clip faible sur le compte : dans le doute, note plus bas.

On te donne beaucoup d'images du clip dans l'ordre, la transcription, le titre Twitch et le \
nombre de vues du clip sur Twitch. Juge ce qu'on VOIT et ENTEND, pas ce que le titre promet : \
une histoire racontée (« il saute », « il finit dans le coma ») ne vaut rien si l'image ne \
montre pas clairement l'action ou la réaction.

""" + SYSTEM.split("Note de clic (click_score, de 1 à 10) :", 1)[-1].split("Donne aussi click_reason", 1)[0].join(
    ["Barème :", ""]) + """
En plus :
- Le nombre de vues Twitch est un signal des viewers : un clip très peu vu (moins de 100 vues) \
dépasse rarement 6, sauf si l'image montre un moment évidemment fort.
- 7 = je le posterais sans hésiter sur un compte qui vise des millions de vues. Sinon 6 ou moins."""


def judge_click(streamer: str, game: str, frames: list, frame_times: list[float] | None,
                transcript: str, twitch_title: str = "", views: int | None = None,
                duration: float = 0.0, model: str = "claude-sonnet-5-5") -> Judge | None:
    """Note de clic finale par un modèle plus fort, avec plus d'images (≈ 1,5-2 centimes)."""
    import base64
    from .guard import Guard
    if not Guard.get().allow_llm():
        return None
    content: list = [{"type": "text", "text": f"{len(frames)} images du clip, dans l'ordre :"}]
    for k, f in enumerate(frames):
        if frame_times and k < len(frame_times):
            content.append({"type": "text", "text": f"Image à {frame_times[k]:.0f} s :"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                    "data": base64.b64encode(f.read_bytes()).decode()}})
    content.append({"type": "text", "text": (
        f"Streamer : {streamer}\nJeu : {game or '(non précisé)'}\n"
        + (f"Durée : {duration:.0f} s\n" if duration else "")
        + (f"Vues du clip sur Twitch : {views}\n" if views is not None else "")
        + f"Titre Twitch : {twitch_title or '(aucun)'}\n\n"
        f"Transcription (auto) :\n<transcription>\n{(transcript or '(pas de parole)')[:3000]}\n</transcription>")})
    client = anthropic.Anthropic(max_retries=2, timeout=90)
    resp = client.messages.parse(model=model, max_tokens=400, system=JUDGE_SYSTEM,
                                 output_config={"effort": "low"},
                                 messages=[{"role": "user", "content": content}], output_format=Judge)
    from . import usage
    usage.llm(model, resp)
    if resp.stop_reason == "refusal" or not resp.parsed_output:
        return None
    j = resp.parsed_output
    j.click_score = max(1, min(10, int(j.click_score)))
    return j


class Translation(BaseModel):
    lines: list[str] = Field(description="Une traduction française par ligne, même nombre et même ordre")


TRANSLATE_SYSTEM = """Tu traduis en français les paroles d'un streamer pour des sous-titres \
de clip court. Chaque ligne numérotée est un bout de phrase prononcé d'un trait. Rends \
exactement une ligne française par ligne reçue, dans le même ordre, courte et naturelle \
(français parlé, tutoiement, pas de traduction mot à mot). Garde les noms propres et les \
termes de jeu (GTA, Vice City, Lucia, Jason…). Pas de censure, pas de commentaire. \
Si une ligne est un bruit ou intraduisible, renvoie-la telle quelle."""


def translate_words(words: list, src_lang: str, model: str = "claude-haiku-5-5") -> list:
    """Traduit des mots horodatés (Whisper) en français en gardant le rythme : les mots sont
    regroupés en bouts de phrase, chaque bout est traduit, puis ses mots français sont
    répartis sur la même durée (les sous-titres restent calés sur la voix)."""
    from .guard import Guard, LimitReached
    from .media import Word
    groups: list[list] = []
    for w in words:
        g = groups[-1] if groups else None
        if (g is None or w.start - g[-1].end > 0.7 or len(g) >= 10
                or g[-1].text.rstrip()[-1:] in ".?!"):
            groups.append([w])
        else:
            g.append(w)
    src = [" ".join(w.text for w in g) for g in groups]
    if not Guard.get().allow_llm():
        raise LimitReached("Plafond du jour atteint pour Claude (60 appels ou 1 $ ≈ 0,90 €)")
    client = anthropic.Anthropic(max_retries=2, timeout=90)
    resp = client.messages.parse(
        model=model, max_tokens=2000, system=TRANSLATE_SYSTEM,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": f"Langue d'origine : {src_lang}\n\n"
                   + "\n".join(f"{i + 1}. {t}" for i, t in enumerate(src))}],
        output_format=Translation,
    )
    from . import usage
    usage.llm(model, resp)
    lines = resp.parsed_output.lines if resp.parsed_output else []
    if len(lines) != len(groups):
        raise RuntimeError(f"traduction incomplète ({len(lines)} lignes pour {len(groups)})")
    out: list = []
    for g, fr in zip(groups, lines):
        toks = [t for t in (fr or "").split() if t]
        if not toks:
            continue
        t0, t1 = g[0].start, max(g[-1].end, g[0].start + 0.4)
        total = sum(len(t) + 1 for t in toks)
        cur = t0
        for t in toks:
            d = (t1 - t0) * (len(t) + 1) / total
            out.append(Word(start=round(cur, 3), end=round(cur + d, 3), text=t))
            cur += d
    return out

# GTA VI Clipper

Pipeline semi-automatique pour créer des clips verticaux (TikTok / Shorts / Reels) de streamers FR qui découvrent GTA VI.

```
Twitch (clips viewers + pics de chat VOD)
   → téléchargement (yt-dlp)
   → transcription FR mot à mot (faster-whisper)
   → recadrage 9:16 + sous-titres animés mot par mot (ffmpeg + libass)
   → titre / description / hashtags (Claude)
   → interface de validation humaine → dossier data/approved/ (vidéo + post.txt)
```

Rien n'est publié automatiquement : chaque clip passe par toi.

## Installation

Prérequis : Python 3.10+, ffmpeg (avec libass). Un GPU NVIDIA accélère beaucoup Whisper (sinon prends `whisper.model: medium` ou `small`).

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml     # puis édite la liste des streamers
```

Variables d'environnement :

| Variable | Où l'obtenir |
|---|---|
| `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET` | https://dev.twitch.tv/console/apps (créer une application, type "Confidential") |
| `ANTHROPIC_API_KEY` | https://console.anthropic.com |

Police des sous-titres : installe **Montserrat ExtraBold** (Google Fonts) pour le style "Shorts". Sinon libass utilise une police de secours.

## Utilisation

```bash
# 1. Récupérer les clips les plus vus des dernières 48 h et les préparer
python -m gta_clipper run

# 2. Valider dans le navigateur
python -m gta_clipper review          # → http://127.0.0.1:5000
```

Dans l'interface : tu regardes le clip, tu modifies le titre (ou tu cliques un titre alternatif), puis **Valider** ou **Rejeter**. Les clips validés vont dans `data/approved/<clip>/` avec `clip.mp4` et `post.txt` (titre + description + hashtags prêts à coller).

Traiter un clip précis à la main :

```bash
python -m gta_clipper local https://www.twitch.tv/squeezie/clip/XXXX --streamer Squeezie
python -m gta_clipper local https://www.twitch.tv/videos/123456 --start 3600 --end 3645 --streamer Squeezie
python -m gta_clipper local ma_video.mp4 --streamer Squeezie
```

## Site de suivi

Le dossier `site/` contient le tableau de bord privé (Vercel) : statut du bot en direct, clips scorés, validation, clips à poster et publiés, frise explicative. Voir `site/README.md` pour la mise en ligne. Une fois `BLOB_READ_WRITE_TOKEN` défini sur le PC du bot, chaque passage envoie ses clips et son statut au site ; la validation se fait alors sur le site (l'interface locale `review` reste disponible).

## Détection des moments forts

1. **Clips viewers Twitch** (activé par défaut) : les clips les plus vus du streamer sur la période, filtrés sur GTA VI, dédoublonnés quand plusieurs viewers ont clippé le même moment. C'est le signal le plus fiable.
2. **Pics de chat dans la VOD** (`vod.enabled: true`) : repère les moments où le chat s'emballe par rapport aux 10 minutes autour. Twitch ne fournit plus le chat des VODs dans son API officielle :
   - méthode fiable : exporter le chat avec [TwitchDownloaderCLI](https://github.com/lay295/TwitchDownloader) `chatdownload --id <VOD_ID> -o chats/<VOD_ID>.json`, puis `python -m gta_clipper run --chat-dir chats`
   - sinon le pipeline tente un endpoint non officiel, que Twitch bloque parfois.

## Mise en page verticale

- `layout: blur` : le jeu entier au centre, fond flouté (rien n'est coupé).
- `layout: crop` : zoom plein écran sur le centre.
- `facecam: {x, y, w, h}` : la webcam du streamer est placée en haut, le jeu en dessous. Les coordonnées dépendent de chaque streamer (à mesurer une fois sur une capture 1920×1080).

## Automatiser

Lancer `python -m gta_clipper run` toutes les heures (cron / Planificateur de tâches Windows). Les clips déjà traités ne sont jamais refaits.

## À savoir

- Les clips appartiennent aux streamers. Beaucoup de streamers FR tolèrent les pages de clips, mais certains réclament la monétisation ou demandent le retrait : vérifie leur position avant de publier en masse.
- Les titres sont générés à partir de la transcription ; quand elle est trop pauvre, l'IA met un indicateur "titre peu sûr" visible dans l'interface.

# Site privé GTA Clipper

Tableau de bord (sans mot de passe, adresse non indexée) : statut du bot, clips scorés, validation, clips à poster, clips publiés, et la frise explicative (`/frise.html`).

## Mise en ligne (une seule fois, environ 5 minutes)

1. Dans ce dossier : `npx vercel` (connecte-toi, accepte de créer le projet `gta-clipper`).
2. Crée un bucket Cloudflare R2 `gta-clipper` (accès public R2.dev activé) et une clé API « Object Read & Write ».
3. Sur vercel.com, ajoute au projet les variables `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_PUBLIC_URL` (et, facultatif, `CF_API_TOKEN` avec le droit « Account Analytics : Read » pour les compteurs exacts de Cloudflare).
4. `npx vercel --prod` pour déployer avec ces variables.

## Relier le bot

Sur le PC du bot (ou dans les secrets GitHub), définis les mêmes variables `R2_…`, puis :

```bash
python -m gta_clipper site-test
```

Recharge le site : le bot doit apparaître avec un signal « à l'instant », et le dernier clip local doit être dans « À valider ».

## Fonctionnement

- Le bot envoie chaque clip (vidéo, miniature, infos) et son statut (un seul fichier `status/live.json`, réécrit au plus toutes les 30 s).
- Le site écrit chaque action (valider, rejeter, publié) comme un nouveau fichier ; les réglages sont des fichiers à nom fixe lus sans listage.
- Chaque passage enregistre sa consommation exacte (opérations R2, appels et coût Claude) dans `usage/AAAA-MM.json` : page « Consommation & quotas ».
- Les vidéos sont sur un stockage R2 public à adresse aléatoire : introuvables sans le lien.

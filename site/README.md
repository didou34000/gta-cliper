# Site privé GTA Clipper

Tableau de bord accessible par mot de passe : statut du bot, clips scorés, validation, clips à poster, clips publiés, et la frise explicative (`/frise.html`).

## Mise en ligne (une seule fois, environ 5 minutes)

1. Dans ce dossier : `npx vercel` (connecte-toi, accepte de créer le projet `gta-clipper`).
2. Sur vercel.com, ouvre le projet > **Storage** > **Create** > **Blob** > connecte-le au projet. Cela ajoute `BLOB_READ_WRITE_TOKEN` tout seul.
3. Projet > **Settings** > **Environment Variables** : ajoute `SITE_PASSWORD` (le mot de passe du site).
4. `npx vercel --prod` pour déployer avec ces variables.

## Relier le bot

Sur le PC du bot, définis la même variable `BLOB_READ_WRITE_TOKEN` (visible dans Storage > ton store Blob > `.env.local`), puis :

```bash
python -m gta_clipper site-test
```

Recharge le site : le bot doit apparaître avec un signal « à l'instant », et le dernier clip local doit être dans « À valider ».

## Fonctionnement

- Le bot envoie chaque clip (vidéo, miniature, infos) et un signal de statut à chaque étape.
- Le site écrit chaque action (valider, rejeter, publié) comme un nouveau fichier ; rien n'est jamais écrasé.
- Les vidéos sont sur un stockage Blob public à adresse aléatoire : introuvables sans le lien, mais pas protégées par le mot de passe.

# Studio GTA 6 : boucle automatique toutes les 8 h

Compte : TikTok @gta6francenews (+ YouTube Shorts "GTA 6 FRANCE"), via Buffer.
Objectif : à chaque passage, analyser les vidéos déjà postées, comprendre ce qui a marché ou non,
et (si le budget le permet) produire et poster une vidéo meilleure que la précédente.
Tout ce que tu apprends va dans `/mnt/project-files/videos-gta6/studio/journal.md` (c'est la mémoire de la boucle).

## PLAN ACTUEL : lundi 16, mardi 17, mercredi 18 nov 2026 (validé par le propriétaire le 15 nov)
Chaque jour (heure de Paris), UN sujet niche, décliné en :
1. **1 carrousel** (style carte postale, voir §3bis) posté sur TikTok en mode **notification** ("Notify Me" :
   le propriétaire ajoute la musique dans l'app). Programmé à 12:30 (ou 30 min après la fin du passage s'il est plus tard).
2. **1 vidéo** sur le même sujet (format §3), postée en **automatique** (pas de notification) sur TikTok
   + Short vertical YouTube, programmée à 18:30 (ou 30 min après la fin du passage s'il est plus tard).
Idempotence : regarde la section "Production par jour" du journal. Si le carrousel / la vidéo du jour sont
déjà faits, ne refais rien : analyse seulement. Si un passage précédent a planté au milieu, termine ce qui manque.
Budget vidéo pour ces 3 jours : 1 vidéo/jour autorisée tant que crédits_restants − 300 ≥ 1 100 (remplace la formule §2).
S'il n'y a plus assez de crédits : carrousel seul, et dis-le dans le compte rendu.
Buffer gratuit : 10 posts programmés max en même temps, vérifie avant de programmer.

## 0. Règles du propriétaire (non négociables)
- Français, ton naturel, aucun gros mot, pas de "like / abonne-toi / commente" en fin de vidéo.
- Accroche forte dans les 2 premières secondes, 5 étapes numérotées (n/5), un "tac" (whoosh + hit) par étape.
- Sous-titres synchronisés mot à mot sur la voix ; titres en dégradé GTA 6 (Anton, jaune→rose→violet, contour noir).
- Éléments d'écran prononcés (jauges, traceur, cartes, tampons…) : c'est ce qui a fait la différence.
- Sujets NICHE et précis (mécaniques concrètes), jamais d'info générique connue de tous.
- Faits vérifiés sur des sources sérieuses (previews presse sept. 2026, Rockstar). Si une info n'est pas sourcée, on ne la dit pas.
  Pas de disclaimer à l'écran.
- Images : uniquement les trailers officiels Rockstar (pas de leaks : risque de retrait Take-Two).
- Ne JAMAIS cocher "contenu IA" sur Buffer. Ne jamais supprimer un post existant du compte.
- Ne JAMAIS dépasser un quota gratuit / crédits (voir §2). Aucun achat.
- Pas d'identifiant de modèle dans les commits.

## 1. Analyse (à chaque passage, même sans vidéo)
1. Buffer : `get_account` (org 6ae8721deaf44e2b4ec5d7f2), puis `list_posts` avec métriques sur la chaîne
   TikTok 6af4a00862b70b94b0f80baa (et YouTube 6af49c4762b70b94b0f7bdd3). Les posts "via network" sont des
   uploads manuels du propriétaire : à analyser aussi.
2. Métriques dispo : vues, likes, commentaires, partages, taux d'engagement, temps de visionnage moyen et total.
   Il n'y a PAS de courbe de rétention. Calcule : rétention moyenne = temps moyen / durée de la vidéo,
   likes/vues, partages/vues. Une vidéo de moins de 24 h n'est pas encore jugeable : note-la "en cours".
3. Compare avec le tableau du journal, mets-le à jour, et écris 2 à 4 hypothèses concrètes
   (ex. "accroche trop lente : les gens partent avant l'étape 1 → mettre le chiffre choc dès 0,5 s").
   Sois honnête : avec ~1 000-2 000 vues par vidéo, les écarts sont souvent du bruit. Ne change qu'1 ou 2 variables à la fois.

## 2. Budget : produire une vidéo ou pas ?
- ElevenLabs (plan Starter, 63 020 crédits/mois, reset vers le 25 de chaque mois) : `account_get_usage`.
  Une voix ≈ 900 crédits (eleven_v4), un bruitage ≈ 20-100. Une vidéo complète ≈ 1 100 crédits.
- Règle : garder toujours 300 crédits de réserve. Intervalle minimal entre deux vidéos =
  max(8 h, 24 h × jours_avant_reset × 1 100 / (crédits_restants − 300)).
  Si l'intervalle n'est pas écoulé depuis la dernière vidéo du journal, ou si crédits_restants − 300 < 1 100 :
  pas de vidéo, seulement l'analyse + idées dans le journal.
- Jamais plus de 3 vidéos par jour.

## 3. Production
### Mise en place (container neuf)
```bash
mkdir -p /home/user/vid/tr /home/user/vid/out /home/user/vid/img
cp -r /mnt/project-files/videos-gta6/studio/* /home/user/vid/
cp /home/user/vid/examples/plein_words.json /home/user/vid/words.json   # requis à l'import de make_plein2
curl -L -o /home/user/vid/img/119.jpg "https://www.gematsu.com/wp-content/uploads/2025/05/Grand-Theft-Auto-VI_2025_05-06-25_119.jpg"
cd /home/user/vid/tr
curl -L -o t1.mp4 "https://archive.org/download/gtavi-trailer-2/GTA%20VI%20Media/GTAVI_Videos/Trailer_1/GTAVI_Trailer_1.mp4"
curl -L -o t2.mp4 "https://archive.org/download/gtavi-trailer-2/GTA%20VI%20Media/GTAVI_Videos/Trailer_2/GTAVI_Trailer_2.mp4"
```
(t1 ≈ 0,7 Go, t2 ≈ 1,3 Go, 4K. t2 a des bandes noires : crop=3840:1728:0:216.)

### Étapes
1. Choisir le sujet (liste "Idées" du journal + hypothèses), vérifier les faits (WebSearch), écrire le script
   (~110-130 mots, 40-48 s, hook + 5 étapes + chute).
2. Voix : ElevenLabs flow 86N67aZ8DpAkUNUmSCLm, voix "Tom - Natural, Easy-Going" stYaAhI2xTaJ48ozXkGt, modèle eleven_v4
   (balises d'émotion [confident] etc. autorisées). Prends une prise, pas deux s'il n'y a pas le budget.
   Timings mot à mot : creative_transcribe_audio (Scribe) branché sur le nœud TTS → words.json.
3. Bruitages : réutilise d'abord `sfx/` et `car/sfx/` (gratuit). Nouveau son seulement si nécessaire
   (eleven_text_to_sound_v2, fixer duration_seconds). Les bips/ticks se synthétisent en numpy (gratuit).
   PAS de nappe d'ambiance (le "bruit de cigales" a été détesté).
4. Image : pars de `car/make_car.py` (le modèle le plus abouti : HUD, cartes, tampons, jauges, minimap…)
   et adapte la liste de plans + les widgets. Format paysage 1920×1080 pour TikTok, version verticale 1080×1920
   fond flou pour YouTube Shorts (Buffer YouTube refuse le paysage).
   MAJ 16 nov 16h54 (stats) : le paysage a fait 29 % de rétention contre 38-40 % en vertical. Mardi 17 : VERTICAL 1080×1920
   plein écran (HUD dans le tiers haut), même fichier pour TikTok et YouTube, ≤ 40 s. Voir journal "Analyse du 16 nov 16h54".
   MAJ 17 nov : modèle VERTICAL prêt à l'emploi = /mnt/project-files/videos-gta6/corps/make_corps.py (+ shots.json, mix_corps.py, check.py-like planche) : plans en JSON, stills gematsu ou extraits trailers recadrés 9:16, cartes HUD verre néon. Timings mot à mot via faster-whisper local (gratuit).
   VÉRIFIE CHAQUE PLAN : extrais une image par plan (ffmpeg -ss) et regarde-la (Read sur le .jpg) avant le rendu.
   Erreurs déjà faites : plan qui tombe sur un écran Weazel News, une boîte de nuit, un mugshot, un post réseau social.
   DÉTECTION DES COUPES OBLIGATOIRE : les trailers changent de plan toutes les 1-2 s. Avant de choisir un plan, détecte les coupes
   (`ffmpeg -ss A -t D -i tX.mp4 -an -vf "scale=320:-2,select='gt(scene,0.08)',showinfo" -f null -` ; seuil 0.08, pas 0.25 qui en rate)
   et garde chaque plan STRICTEMENT entre deux coupes. Puis fais une planche de vérif : 4 images par plan (3 %, 35 %, 65 %, 97 % de la
   plage source, déjà recadrées) et regarde-la. La vidéo « Voler une voiture » du 15 nov contient des bouts de boîte de nuit et un
   bandeau Weazel News à cause de ça (erreur de plage).
   Emojis interdits dans les polices (rendu en carré).
5. Mixage : sur le modèle de `car/mix_car.py` (amix normalize=0, loudnorm I=-14 TP=-1.5).
6. Contrôle final : regarde 6-8 images de la vidéo finale (accroche, chaque étape, fin), vérifie durée,
   niveau audio (ffmpeg volumedetect), pas de texte qui déborde. Tu ne peux pas écouter : ne prétends pas l'avoir fait.

## 3bis. Carrousel (style "carte postale Visit Leonida", validé le 13 nov)
- Générateur : `studio/carrousel/style2.py` + `lib.py` (polices anton.ttf / marker.ttf à côté ; Montserrat dans
  `/home/user/gta-cliper/assets/fonts/`). `exemple_make_station.py` et `legende.txt` = exemple complet.
  Copie le dossier ailleurs, réécris `cover()` et les appels `slide(...)` pour le nouveau sujet ; images dans `img/<nom>.jpg`.
- 1080×1350, **7 slides MAXIMUM** (couverture + 5 mécaniques + slide de fin), carte postale inclinée sur fond flouté
  violet, notes au feutre jaune, tampon de fiabilité sur chaque fait : CONFIRMÉ / CONFIRMÉ EN PREVIEW (vert),
  RAPPORTÉ EN PREVIEW (jaune), VU SUR IMAGE OFFICIELLE (rose), RUMEUR (gris). Badge haut "GTA 6 FRANCE NEWS".
- Images OFFICIELLES uniquement : gematsu.com, captures Rockstar
  `https://www.gematsu.com/wp-content/uploads/2026/06/Grand-Theft-Auto-VI_2026_06-24-26_NNN.jpg` (63 images)
  et `https://www.gematsu.com/wp-content/uploads/2025/05/Grand-Theft-Auto-VI_2025_05-06-25_NNN.jpg` (~92 images, 4K),
  ou des images extraites des trailers. Regarde chaque image avant de l'utiliser ; ne nomme jamais un personnage
  absent de l'image.
- Sujet = une ACTION concrète en jeu ("comment tu fais X dans GTA 6"), pas d'info générale (prix, date, musique…).
- Hébergement : `/home/user/gta-cliper/carrousels/<sujet>/slide-N.png` sur la branche claude/project-thread-uxcv0v
  (URL raw.githubusercontent.com), puis Buffer `create_post` TikTok avec les images, mode notification, légende +
  hashtags comme `legende.txt`. Case IA décochée.

## 4. Publication
1. Copie le mp4 dans `/home/user/gta-cliper/videos/`, commit puis push (commandes séparées) sur la branche
   `claude/project-thread-uxcv0v`. URL : https://raw.githubusercontent.com/didou34000/gta-cliper/claude/project-thread-uxcv0v/videos/<fichier>.mp4
2. Buffer `create_post` TikTok (shareNow, vidéo paysage) : légende courte style "GTA 6 : <fait choc> 🚨" + 3-5 hashtags
   (#gta6 #gta6france #gtavi …). Case IA décochée.
3. Buffer YouTube (vertical) : titre ≤ 100 caractères, catégorie 20, même règle IA.
4. Mets à jour le journal (tableau + "Dernière vidéo" avec date/heure), commit + push.

## 5. Compte rendu
Termine par un résumé court en français : ce qui a été analysé, ce qui a changé et pourquoi, vidéo postée (lien) ou
raison de ne pas en faire, crédits ElevenLabs restants.

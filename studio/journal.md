# Journal de la boucle TikTok (mis à jour à chaque passage)

## Tableau des vidéos (TikTok sauf mention)
| Date | Vidéo | Durée | Vues | Tps moyen | Rétention moy. | Likes | Partages | Notes |
|---|---|---|---|---|---|---|---|---|
| 13 nov | Carrousel "Justice" | – | 2 432 | 11,2 s | – | 65 | – | engagement 2,75 % |
| 13 nov | Carrousel Jason/Lucia | – | 1 020 | 9,8 s | – | – | – | engagement 2,55 % |
| 14 nov | Semer la police (upload manuel) | 40,5 s | 1 781 | 16,5 s | 41 % | 114 | 9 | meilleur partage |
| 14 nov | Semer la police (2e copie) | 45,6 s | 638 | 11,3 s | 25 % | – | – | doublon, faible |
| 15 nov 13h | Faire le plein v3 (upload manuel) | 44 s | 1 415 | 15,7 s | 36 % | 145 | 1 | engagement 10,3 %, meilleur ratio likes |
| 13 nov | Carrousel "Faire le plein" (station-essence) | – | 1 165 | 14,7 s | – | 24 | 1 | engagement 2,15 % ; meilleur temps moyen des carrousels niche |
| 15 nov 21h27 | Voler une voiture (paysage, HUD) | 47,6 s | en cours | | | | | stats Buffer encore à 0 le 16 nov 0h55 (rafraîchies 1×/jour) ; post 6afa154f60a910801c46dab6 ; Short YouTube 6afa15c68e87c256a38c94da (0 vue) |
| 16 nov 12h30 | Carrousel "Braquer un magasin" (notif) | – | en cours | | | | | post Buffer 6afa475c06e1675856b430ab |
| 16 nov 18h30 | Braquer un magasin (paysage, HUD, voix Chatterbox) | 38,9 s | en cours | | | | | 1re vidéo SANS ElevenLabs ; plus courte (38,9 s vs 44-47 s) ; TikTok 6afac46a60a910801c7f0923, Short 6afac46b06e1675856db9b02 |

## Ce qui marche (constaté)
- Format 5 étapes + "tac" + sous-titres mot à mot + titres dégradé GTA : "Faire le plein" a fait le meilleur taux de likes.
- Les vidéos voix-off battent les carrousels en temps de visionnage.

## Problèmes constatés
- Rétention moyenne ~35-40 % : la majorité décroche avant la moitié (≈ étape 2). Piste : accroche plus rapide, étape 1 plus courte.
- Le propriétaire a détesté : bruit de fond type cigales (nappe d'ambiance), sous-titres seuls sans voix.

## Analyse du 16 nov 0h55
- Rien de neuf côté chiffres : Buffer n'a pas rafraîchi depuis le 15 nov 13h (TikTok) ; "Voler une voiture" affiche encore 0 partout. Jugeable au passage de 8h54 ou 16h54.
- Constat stable : les vidéos voix-off niche font 15,7-16,5 s de temps moyen (36-41 % de rétention) contre 9-14 s pour les carrousels. Les carrousels niche (station-essence 14,7 s) tiennent mieux que les carrousels génériques (9,4-11,2 s) : la règle "mécanique précise" se confirme.
- Le YouTube Short reste à ~0 vue (3 vues pour "7 nouveautés") : YouTube ne pousse pas encore la chaîne, ne pas en tirer de conclusion.
- Partages : "Semer la police" (9) loin devant ; "Faire le plein" 1 seul partage malgré 145 likes → sujet qui plaît mais qu'on n'envoie pas à un pote. Piste : sujets "astuce qui change ta façon de jouer" (police, braquage) > sujets "info".

## Analyse du 16 nov 8h54
- Toujours aucune stat neuve : la dernière mise à jour Buffer des métriques TikTok date du 15 nov 14h10 (Paris). "Voler une voiture" (TikTok + Short) affiche encore 0 car ses métriques n'ont été lues qu'à la publication. Buffer rafraîchit environ 1 fois par 24 h : jugeable au passage de 16h54.
- Aucune copie "via network" de "Voler une voiture" n'est encore remontée dans Buffer.
- Conclusions inchangées (voir analyse de 0h55). Pas de nouvelle hypothèse sans nouvelles données.

## Hypothèses à tester (une ou deux à la fois)
1. Vidéo plus courte (30-35 s) → rétention plus haute ?
2. Chiffre ou image choc dès 0,5 s, et annoncer la meilleure étape ("la 5e est la pire").
3. Paysage (voler voiture) vs vertical : comparer quand les chiffres seront là.

## Idées de sujets (niche, sourcées previews sept. 2026)
- 4 armes max + le reste dans le coffre de la voiture.
- Argent perdu quand on meurt / retrait au distributeur.
- (déjà faits : semer la police, faire le plein, voler une voiture, braquer un magasin [carrousel 16 nov])
- Cash perdu à la mort / arrêté → dépôt au distributeur ; 3 niveaux d'argent (banque, cash, valeur du sac).
- Échapper aux caméras / profil criminel (visage, vêtements, véhicule mémorisés).

## Décision voix (16 nov 8h38)
- Le propriétaire a choisi : PAS d'ElevenLabs pour la voix, voix gratuite Chatterbox (open source, licence MIT) générée en local. Les bruitages existants restent utilisables.

## Note du fil principal (16 nov ~9h)
- Le propriétaire a aussi demandé dans le fil principal une vidéo PORTRAIT « 5 choses qu'on ne pourra plus faire dans GTA 6 »
  (style de sa vidéo de référence, STYLE-REFERENCE.md), montrée d'abord SANS voix ; il confirmera la voix ensuite.
  C'est le fil principal qui la gère et elle ne sera postée qu'après son accord : ne la refais pas et ne la poste pas.
  Fichiers : /mnt/project-files/videos-gta6/5-choses/. Sujets déjà couverts dedans : 4 armes max + coffre, essence, traceur, caméras/masque, cash perdu.

## Voix Chatterbox : mode d'emploi (validé 16 nov)
- Fichiers : /mnt/project-files/videos-gta6/braquage/ (tts.py, gen.py = génération + contrôle Whisper + coupe auto, script2.txt, make_braq.py, mix_braq.py).
- Installation : python3 -m venv /home/user/cb ; pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu ; pip install chatterbox-tts faster-whisper (~5 min). ChatterboxMultilingualTTS, language_id="fr", voix par défaut (pas de clonage), exaggeration 0.55, temperature 0.65.
- 1 phrase par ligne ; écrire "G.T.A. six" (sinon prononcé "JT A 6") ; "Étape un :" au lieu de "Un." ; éviter "t'enfuir" (mal prononcé).
- gen.py fait jusqu'à 6 prises par phrase et garde celle que Whisper comprend le mieux (sinon : hallucinations en fin de phrase). ~2 min par phrase sur CPU.
- Voix finale : concat + atempo 1.08 + compresseur + loudnorm. Timings mot à mot : faster-whisper, réalignés sur le texte du script.
- Limites honnêtes : voix plus neutre/moins "créateur" qu'ElevenLabs, quelques mots moins nets ("Tire" compris "tu es" par Whisper). Le propriétaire n'a pas pu comparer avant publication.

## Budget
- ElevenLabs : 4 178 crédits restants le 16 nov 8h54 (58 842 / 63 020 utilisés, inchangé depuis 0h55), reset 25 nov. Voix désormais Chatterbox (gratuite) : les crédits ne servent plus qu'aux bruitages éventuels.

## Dernière vidéo
- 2026-11-15 21:27 (Paris) : Voler une voiture.

## Production par jour (plan 16-18 nov : 1 carrousel notif + 1 vidéo auto par jour)
| Jour | Sujet | Carrousel (post Buffer) | Vidéo TikTok | Short YouTube |
|---|---|---|---|---|
| lun 16 | Braquer un magasin (masque, tir d'intimidation, coffre à code, sac → receleur, cash perdu) | FAIT : 6afa475c06e1675856b430ab, notif 12:30 ; images branche claude/project-thread-xla67j carrousels/braquage/ ; fichiers /mnt/project-files/carrousel-gta6/braquage/ | FAIT : 6afac46a60a910801c7f0923, auto 18:30 (paysage, 38,9 s, voix Chatterbox) | FAIT : 6afac46b06e1675856db9b02, auto 18:30 (vertical) |
| mar 17 | | | | |
| mer 18 | | | | |

## Historique des passages
- 2026-11-15 : boucle créée.
- 2026-11-16 8h40-9h55 : vidéo braquage faite avec Chatterbox (0 crédit) et programmée 18h30. Sujets retirés pour éviter le doublon avec la vidéo portrait "5 choses qu'on ne pourra plus faire" (autre fil) : masque/caméras et cash perdu à la mort.
- 2026-11-16 0h55 : analyse (pas de nouvelles stats), carrousel du jour programmé. Vidéo reportée : le propriétaire a écrit le 15 nov à 22h49 "la voix pas de leven labs hein" (sens ambigu), question posée par carte de décision dans le fil du passage de 0h55 (lire ce fil avant de produire). Si pas de réponse au passage de 16h54 : vidéo avec la voix ElevenLabs Tom (plan validé), en gardant le format paysage HUD. NB : hébergement sur la branche claude/project-thread-xla67j (branche de ce passage), pas uxcv0v.
- 2026-11-16 8h54 : analyse seulement (pas de stats neuves). Carrousel du jour déjà programmé (12:30), vidéo du jour en cours dans le fil du passage de 0h55 (voix Chatterbox) : rien refait.

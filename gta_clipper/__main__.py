"""CLI : python -m gta_clipper {run,local,review}"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .pipeline import load_config, process_clip, run


def load_dotenv(path: str = ".env") -> None:
    """Charge un fichier .env simple (CLE=valeur) sans écraser les variables déjà définies."""
    import os
    f = Path(path)
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if v.strip():
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main() -> None:
    load_dotenv()
    p = argparse.ArgumentParser(prog="gta_clipper")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="Récupère les clips/VODs Twitch et prépare les clips à valider")
    r.add_argument("--no-llm", action="store_true", help="Sans génération de titre par IA")
    r.add_argument("--chat-dir", help="Dossier d'exports chat TwitchDownloader (<vod_id>.json)")

    lp = sub.add_parser("loop", help="Tourne en continu : un passage toutes les N minutes")
    lp.add_argument("--every", type=int, default=60, help="Minutes entre deux passages (60)")
    lp.add_argument("--no-llm", action="store_true")
    lp.add_argument("--chat-dir")

    lo = sub.add_parser("local", help="Traite une vidéo locale ou une URL (clip/VOD Twitch)")
    lo.add_argument("source", help="Fichier .mp4 ou URL")
    lo.add_argument("--streamer", required=True, help='Nom affiché, ex: "Squeezie"')
    lo.add_argument("--start", type=float, help="Début (s) si URL de VOD")
    lo.add_argument("--end", type=float, help="Fin (s) si URL de VOD")
    lo.add_argument("--no-llm", action="store_true")
    lo.add_argument("--words", help="Transcription déjà faite (JSON) au lieu de Whisper")

    sub.add_parser("site-test", help="Envoie un statut + le dernier clip local au site, pour tester la liaison")

    rv = sub.add_parser("review", help="Lance l'interface de validation")
    rv.add_argument("--port", type=int, default=5000)
    rv.add_argument("--host", default="127.0.0.1")

    a = p.parse_args()
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config(a.config)

    if a.cmd == "run":
        out = run(cfg, skip_llm=a.no_llm, chat_dir=a.chat_dir)
        print(f"{len(out)} clip(s) en attente de validation. Lance : python -m gta_clipper review")
    elif a.cmd == "loop":
        import time
        from .guard import Guard
        while True:
            if Guard.stopped():
                print("Fichier STOP présent : pas de passage. Supprime-le pour relancer.")
                time.sleep(60)
                continue
            try:
                out = run(cfg, skip_llm=a.no_llm, chat_dir=a.chat_dir)
                print(f"{len(out)} nouveau(x) clip(s). Prochain passage dans {a.every} min.")
            except KeyboardInterrupt:
                raise
            except Exception as e:  # on ne s'arrête pas pour une erreur passagère
                print(f"Passage en erreur ({e}). Nouvel essai dans {a.every} min.")
            time.sleep(a.every * 60)
    elif a.cmd == "local":
        from . import media
        src = a.source
        if src.startswith("http"):
            video = media.download(src, Path(cfg["paths"]["work"]) / "local" / "source.mp4",
                                   a.start, a.end)
        else:
            video = Path(src)
        words = media.load_words(Path(a.words)) if a.words else None
        d = process_clip(cfg, source_id=f"local-{video.stem}", streamer_name=a.streamer,
                         video=video, source_url=src if src.startswith("http") else "",
                         skip_llm=a.no_llm, words=words)
        from .remote import enabled, upload_clip
        if enabled():
            upload_clip(d)
            print(f"Prêt à valider (en local et sur le site) : {d}")
        else:
            print(f"Prêt à valider (en local uniquement, BLOB_READ_WRITE_TOKEN absent) : {d}")
    elif a.cmd == "site-test":
        from .remote import Reporter, enabled, upload_clip
        if not enabled():
            raise SystemExit("BLOB_READ_WRITE_TOKEN absent : récupère-le dans Vercel > Storage.")
        rep = Reporter()
        rep.beat("idle", "Test de liaison", "Le bot arrive à parler au site")
        items = sorted(Path(cfg["paths"]["review"]).glob("*/meta.json"))
        if items:
            upload_clip(items[-1].parent)
            print(f"Statut et clip envoyés ({items[-1].parent.name}). Recharge le site.")
        else:
            print("Statut envoyé. Aucun clip local à envoyer (lance d'abord la commande local).")
    elif a.cmd == "review":
        from .review import create_app
        print(f"Interface de validation : http://{a.host}:{a.port}")
        create_app(cfg).run(host=a.host, port=a.port)


if __name__ == "__main__":
    main()

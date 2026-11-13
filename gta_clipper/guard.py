"""Garde-fous : plafonds quotidiens (IA, clips, envois vers le site), arrêt d'urgence,
coupe-circuit après trop d'échecs d'affilée.

Les compteurs du jour sont gardés dans data/usage.json et remis à zéro chaque jour.
Arrêt d'urgence : créer un fichier STOP à la racine du projet (ou STOP=1 dans .env).
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

DEFAULTS = {
    "max_new_clips_per_run": 10,    # clips fabriqués par passage
    "max_new_clips_per_day": 40,    # clips fabriqués par jour
    "max_llm_calls_per_day": 60,    # appels à Claude par jour (titres)
    "max_site_uploads_per_day": 600,  # envois vers le stockage R2 par jour (statuts + vidéos)
    "max_consecutive_errors": 5,    # échecs d'affilée avant d'arrêter le passage
    "max_download_mb": 400,         # taille max d'une vidéo téléchargée
}


class LimitReached(Exception):
    pass


class Guard:
    _instance: "Guard | None" = None

    def __init__(self, cfg: dict | None = None, path: str | Path = "data/usage.json"):
        self.limits = {**DEFAULTS, **((cfg or {}).get("limits") or {})}
        if os.environ.get("MAX_CLIPS", "").isdigit():  # réglage ponctuel (passage de test)
            self.limits["max_new_clips_per_run"] = min(int(os.environ["MAX_CLIPS"]),
                                                       self.limits["max_new_clips_per_run"])
        self.path = Path(path)
        self.run_clips = 0
        self.consecutive_errors = 0
        self._load()
        Guard._instance = self

    @classmethod
    def get(cls) -> "Guard":
        return cls._instance or cls()

    # --- persistance ------------------------------------------------------
    def _load(self):
        today = date.today().isoformat()
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            d = {}
        self.day = d if d.get("date") == today else {"date": today, "clips": 0, "llm": 0,
                                                      "uploads": 0}

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.day), encoding="utf-8")
        except Exception:
            pass

    def _bump(self, key: str):
        self._load_if_new_day()
        self.day[key] = self.day.get(key, 0) + 1
        self._save()

    def _load_if_new_day(self):
        if self.day.get("date") != date.today().isoformat():
            self._load()

    # --- contrôles --------------------------------------------------------
    @staticmethod
    def stopped() -> bool:
        return Path("STOP").exists() or os.environ.get("STOP", "") in ("1", "true", "oui")

    def check_clip(self):
        """À appeler avant de fabriquer un clip."""
        self._load_if_new_day()
        if self.stopped():
            raise LimitReached("Arrêt d'urgence (fichier STOP présent)")
        if self.run_clips >= self.limits["max_new_clips_per_run"]:
            raise LimitReached(f"Plafond atteint : {self.limits['max_new_clips_per_run']} "
                               f"clips par passage")
        if self.day["clips"] >= self.limits["max_new_clips_per_day"]:
            raise LimitReached(f"Plafond atteint : {self.limits['max_new_clips_per_day']} "
                               f"clips aujourd'hui")
        if self.consecutive_errors >= self.limits["max_consecutive_errors"]:
            raise LimitReached(f"{self.consecutive_errors} échecs d'affilée : passage arrêté "
                               f"par sécurité")

    def clip_done(self):
        self.run_clips += 1
        self.consecutive_errors = 0
        self._bump("clips")

    def clip_failed(self):
        self.consecutive_errors += 1

    def allow_llm(self) -> bool:
        self._load_if_new_day()
        if self.day["llm"] >= self.limits["max_llm_calls_per_day"]:
            return False
        self._bump("llm")
        return True

    def allow_upload(self, important: bool = False) -> bool:
        """Les envois importants (vidéo, fin de passage, erreur) gardent une marge de 10 %."""
        self._load_if_new_day()
        cap = self.limits["max_site_uploads_per_day"]
        if self.day["uploads"] >= (cap if important else cap * 0.9):
            return False
        self._bump("uploads")
        return True

    def summary(self) -> str:
        L = self.limits
        return (f"aujourd'hui : {self.day['clips']}/{L['max_new_clips_per_day']} clips, "
                f"{self.day['llm']}/{L['max_llm_calls_per_day']} appels IA, "
                f"{self.day['uploads']}/{L['max_site_uploads_per_day']} envois site")

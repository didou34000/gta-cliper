"""Accès Twitch : API officielle Helix (clips, VODs) + replay du chat des VODs."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

HELIX = "https://api.twitch.tv/helix"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"


@dataclass
class Clip:
    id: str
    url: str
    broadcaster_login: str
    broadcaster_name: str
    title: str
    view_count: int
    duration: float
    created_at: str
    game_id: str
    video_id: str | None
    vod_offset: int | None


@dataclass
class Vod:
    id: str
    url: str
    user_login: str
    title: str
    duration_s: int
    created_at: str


class TwitchClient:
    def __init__(self, client_id: str | None = None, client_secret: str | None = None):
        self.client_id = client_id or os.environ.get("TWITCH_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("TWITCH_CLIENT_SECRET")
        if not self.client_id or not self.client_secret:
            raise RuntimeError(
                "TWITCH_CLIENT_ID et TWITCH_CLIENT_SECRET sont requis "
                "(crée une app sur https://dev.twitch.tv/console/apps)."
            )
        self._token: str | None = None
        self._token_exp = 0.0
        self.s = requests.Session()

    # --- auth -------------------------------------------------------------
    def _auth(self) -> dict:
        if not self._token or time.time() > self._token_exp - 60:
            r = self.s.post(TOKEN_URL, data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            }, timeout=20)
            r.raise_for_status()
            d = r.json()
            self._token = d["access_token"]
            self._token_exp = time.time() + d.get("expires_in", 3600)
        return {"Client-Id": self.client_id, "Authorization": f"Bearer {self._token}"}

    def _get(self, path: str, params: dict) -> dict:
        for attempt in range(4):
            r = self.s.get(f"{HELIX}{path}", params=params, headers=self._auth(), timeout=20)
            if r.status_code == 429:
                reset = float(r.headers.get("Ratelimit-Reset", time.time() + 2))
                time.sleep(max(1.0, reset - time.time()))
                continue
            r.raise_for_status()
            return r.json()
        r.raise_for_status()
        return {}

    # --- lookups ----------------------------------------------------------
    def user_id(self, login: str) -> str | None:
        data = self._get("/users", {"login": login}).get("data", [])
        return data[0]["id"] if data else None

    def game_id(self, name: str) -> str | None:
        data = self._get("/games", {"name": name}).get("data", [])
        return data[0]["id"] if data else None

    def top_streamers(self, game_id: str | None, n: int = 8, language: str = "fr",
                      hours: int = 48) -> list[dict]:
        """Les N plus gros streamers d'une langue sur un jeu.

        1) ceux en live en ce moment, triés par nombre de viewers ;
        2) si ça ne suffit pas, ceux dont les clips du jeu ont fait le plus de vues
           sur les dernières heures (utile quand peu de monde est en live).
        Renvoie [{"login", "name", "why"}].
        """
        out: dict[str, dict] = {}
        params = {"language": language, "first": 100}
        if game_id:
            params["game_id"] = game_id
        for s in self._get("/streams", params).get("data", []):  # déjà triés par viewers
            login = s["user_login"].lower()
            if login not in out:
                out[login] = {"login": login, "name": s["user_name"],
                              "why": f"en live, {_n(s.get('viewer_count', 0))} viewers"}
            if len(out) >= n:
                return list(out.values())
        if game_id:
            now = datetime.now(timezone.utc)
            views: dict[str, list] = {}
            cp = {"game_id": game_id, "first": 100,
                  "started_at": (now - timedelta(hours=hours)).isoformat().replace("+00:00", "Z"),
                  "ended_at": now.isoformat().replace("+00:00", "Z")}
            cursor = None
            for _ in range(5):
                if cursor:
                    cp["after"] = cursor
                d = self._get("/clips", cp)
                for c in d.get("data", []):
                    if (c.get("language") or "").lower() != language:
                        continue
                    name = c["broadcaster_name"]
                    v = views.setdefault(name.lower(), [name, 0])
                    v[1] += c.get("view_count", 0)
                cursor = d.get("pagination", {}).get("cursor")
                if not cursor:
                    break
            for login, (name, total) in sorted(views.items(), key=lambda kv: -kv[1][1]):
                if len(out) >= n:
                    break
                if login not in out:
                    out[login] = {"login": login, "name": name,
                                  "why": f"clips du jeu : {_n(total)} vues en {hours} h"}
        return list(out.values())

    def top_clips(self, broadcaster_id: str, hours: int, game_id: str | None = None,
                  min_views: int = 0, limit: int = 20) -> list[Clip]:
        """Clips créés par les viewers sur les N dernières heures, triés par vues.

        Les clips viewers sont le meilleur signal de "moment fort" : quelqu'un a jugé
        que ça valait la peine d'être coupé.
        """
        now = datetime.now(timezone.utc)
        params = {
            "broadcaster_id": broadcaster_id,
            "started_at": (now - timedelta(hours=hours)).isoformat().replace("+00:00", "Z"),
            "ended_at": now.isoformat().replace("+00:00", "Z"),
            "first": 100,
        }
        clips: list[Clip] = []
        st = {"total": 0, "hors_jeu": 0, "sous_seuil": 0, "doublons": 0, "retenus": 0,
              "max_vues": 0}
        cursor = None
        for _ in range(5):  # 500 clips max
            if cursor:
                params["after"] = cursor
            d = self._get("/clips", params)
            for c in d.get("data", []):
                st["total"] += 1
                if game_id and c.get("game_id") != game_id:
                    st["hors_jeu"] += 1
                    continue
                st["max_vues"] = max(st["max_vues"], c.get("view_count", 0))
                if c.get("view_count", 0) < min_views:
                    st["sous_seuil"] += 1
                    continue
                clips.append(Clip(
                    id=c["id"], url=c["url"],
                    broadcaster_login=c["broadcaster_name"].lower(),
                    broadcaster_name=c["broadcaster_name"], title=c.get("title", ""),
                    view_count=c.get("view_count", 0), duration=float(c.get("duration", 0)),
                    created_at=c.get("created_at", ""), game_id=c.get("game_id", ""),
                    video_id=c.get("video_id") or None, vod_offset=c.get("vod_offset"),
                ))
            cursor = d.get("pagination", {}).get("cursor")
            if not cursor:
                break
        clips.sort(key=lambda c: c.view_count, reverse=True)
        unique = dedupe_overlapping(clips)
        st["doublons"] = len(clips) - len(unique)
        out = unique[:limit]
        st["retenus"] = len(out)
        st["hors_quota"] = len(unique) - len(out)
        self.last_clip_stats = st
        return out

    def recent_vods(self, user_id: str, limit: int = 1) -> list[Vod]:
        d = self._get("/videos", {"user_id": user_id, "type": "archive", "first": limit})
        return [Vod(id=v["id"], url=v["url"], user_login=v["user_login"], title=v["title"],
                    duration_s=parse_twitch_duration(v["duration"]), created_at=v["created_at"])
                for v in d.get("data", [])]


def _n(x: int) -> str:
    return f"{x:,}".replace(",", " ")


def dedupe_overlapping(clips: list[Clip], tolerance: int = 20) -> list[Clip]:
    """Plusieurs viewers clippent souvent le même moment : on garde le plus vu."""
    kept: list[Clip] = []
    for c in clips:  # déjà triés par vues décroissantes
        dup = any(
            k.video_id and k.video_id == c.video_id and k.vod_offset is not None
            and c.vod_offset is not None and abs(k.vod_offset - c.vod_offset) < tolerance
            for k in kept
        )
        if not dup:
            kept.append(c)
    return kept


def parse_twitch_duration(s: str) -> int:
    """'1h2m3s' -> 3723"""
    total, num = 0, ""
    for ch in s:
        if ch.isdigit():
            num += ch
        else:
            total += int(num or 0) * {"h": 3600, "m": 60, "s": 1}.get(ch, 0)
            num = ""
    return total


# --- Chat des VODs ---------------------------------------------------------
# Twitch n'expose plus le chat des VODs dans l'API officielle. Deux options :
#  1. (fiable) Exporter le chat avec TwitchDownloaderCLI :
#       TwitchDownloaderCLI chatdownload --id <VOD_ID> -o chat.json
#     puis passer ce fichier au pipeline.
#  2. (best effort) L'endpoint GQL non officiel ci-dessous. Twitch le restreint
#     régulièrement ; s'il échoue, utilise l'option 1.

GQL_URL = "https://gql.twitch.tv/gql"
GQL_PUBLIC_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"
GQL_COMMENTS_HASH = "b70a3591ff0f4e0313d126c6a1502d79a1c02baebb288227c582044aa76adf6a"


def load_chat_offsets(path: str | Path) -> list[float]:
    """Lit un export TwitchDownloader (JSON) et renvoie les offsets (s) des messages."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    comments = data.get("comments", data if isinstance(data, list) else [])
    return sorted(float(c["content_offset_seconds"]) for c in comments
                  if "content_offset_seconds" in c)


def fetch_chat_offsets_gql(vod_id: str, max_pages: int = 5000) -> list[float]:
    s = requests.Session()
    s.headers.update({"Client-Id": GQL_PUBLIC_CLIENT_ID})
    offsets: list[float] = []
    cursor = None
    for _ in range(max_pages):
        variables = {"videoID": vod_id}
        if cursor:
            variables["cursor"] = cursor
        else:
            variables["contentOffsetSeconds"] = 0
        body = [{
            "operationName": "VideoCommentsByOffsetOrCursor",
            "variables": variables,
            "extensions": {"persistedQuery": {"version": 1, "sha256Hash": GQL_COMMENTS_HASH}},
        }]
        r = s.post(GQL_URL, json=body, timeout=20)
        r.raise_for_status()
        payload = r.json()[0]
        if "errors" in payload:
            raise RuntimeError(f"GQL chat refusé par Twitch : {payload['errors']}. "
                               "Utilise TwitchDownloaderCLI (voir README).")
        comments = (payload.get("data", {}).get("video") or {}).get("comments") or {}
        edges = comments.get("edges", [])
        for e in edges:
            offsets.append(float(e["node"]["contentOffsetSeconds"]))
        if not comments.get("pageInfo", {}).get("hasNextPage") or not edges:
            break
        cursor = edges[-1].get("cursor")
        time.sleep(0.1)
    return sorted(offsets)

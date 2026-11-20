"""Chat Twitch d'un live, lu en direct pendant l'enregistrement (connexion anonyme, sans
compte ni clé : l'IRC public de Twitch accepte un pseudo « justinfanNNNN » en lecture seule).

Pourquoi : la transcription seule ne voit pas l'image, et les moments drôles de GTA sont
souvent visuels. Le chat, lui, réagit à ce qu'il voit : un pic de « MDR / KEKW / 😂 » est la
meilleure preuve qu'un moment a fait rire des milliers de viewers (règle du 20/11 : « comment
ça se fait qu'il n'y en ait aucun à 7/10 »)."""
from __future__ import annotations

import logging
import random
import re
import socket
import ssl
import threading
import time
from dataclasses import dataclass

log = logging.getLogger("gta_clipper")

# Rires et stupeur dans un chat Twitch FR (emotes comprises).
LAUGH = re.compile(
    r"(m+d+r+|x?p+t+d+r+|j+p+p+|kekw|kekl|omegalul|\blulw?\b|icant|pepelaugh|\blo+l+\b|"
    r"\blmao|😂|🤣|💀|\b(a?ha){2,}h*\b|\b(hi){2,}\b|\bxd+\b|je pleure|mort de rire|chokbar|"
    r"\bwtf\b|\?{3,}|\bomg\b|choqu)", re.I)


@dataclass
class Spike:
    t: float          # début de la fenêtre (secondes depuis le début de l'enregistrement)
    end: float
    count: int        # messages de rire / stupeur dans la fenêtre
    ratio: float      # par rapport à la normale du chat
    examples: list[str]


class ChatLog(threading.Thread):
    """Écoute le chat de `login` en tâche de fond. messages = [(t, texte)], t relatif à t0."""

    def __init__(self, login: str, t0: float):
        super().__init__(daemon=True)
        self.login = login.lower()
        self.t0 = t0
        self.messages: list[tuple[float, str]] = []
        self.error = ""
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def _connect(self) -> socket.socket:
        try:
            s = socket.create_connection(("irc.chat.twitch.tv", 6667), timeout=20)
        except OSError:
            raw = socket.create_connection(("irc.chat.twitch.tv", 6697), timeout=20)
            s = ssl.create_default_context().wrap_socket(raw, server_hostname="irc.chat.twitch.tv")
        s.settimeout(5)
        nick = f"justinfan{random.randint(10000, 99999)}"
        s.sendall(f"NICK {nick}\r\nJOIN #{self.login}\r\n".encode())
        return s

    def run(self) -> None:
        delay = 2.0
        while not self._stop.is_set():
            try:
                s = self._connect()
                buf = b""
                while not self._stop.is_set():
                    try:
                        data = s.recv(65536)
                    except socket.timeout:
                        continue
                    if not data:
                        raise ConnectionError("chat fermé par Twitch")
                    buf += data
                    *lines, buf = buf.split(b"\r\n")
                    for raw in lines:
                        line = raw.decode("utf-8", errors="ignore")
                        if line.startswith("PING"):
                            s.sendall(("PONG" + line[4:] + "\r\n").encode())
                            continue
                        msg = parse_privmsg(line)
                        if msg is not None:
                            self.messages.append((time.time() - self.t0, msg))
                delay = 2.0
                s.close()
            except Exception as e:
                self.error = str(e)[:150]
                self._stop.wait(delay)
                delay = min(delay * 2, 60)


def parse_privmsg(line: str) -> str | None:
    """« :pseudo!pseudo@pseudo.tmi.twitch.tv PRIVMSG #chaine :message » → message."""
    if " PRIVMSG #" not in line:
        return None
    if line.startswith("@"):  # tags IRCv3 éventuels
        line = line.split(" ", 1)[-1]
    _, _, rest = line.partition(" PRIVMSG #")
    _, sep, msg = rest.partition(" :")
    return msg.strip()[:200] if sep else None


def spikes(messages: list[tuple[float, str]], duration: float, *, lag: float = 7.0,
           win: float = 20.0, top: int = 8) -> list[Spike]:
    """Les plus gros pics de rires du chat. `lag` : le chat réagit quelques secondes après
    l'image (et l'enregistrement démarre un peu après t0), on recule d'autant."""
    if not messages or duration <= 0:
        return []
    step = 5.0
    n = int(duration // step) + 1
    laugh = [0] * n
    for t, m in messages:
        k = int((t - lag) // step)
        if 0 <= k < n and LAUGH.search(m):
            laugh[k] += 1
    per = int(win // step)
    sums = [sum(laugh[k:k + per]) for k in range(n)]
    base = sorted(sums)[len(sums) // 2] if sums else 0
    base = max(base, 1)
    cand = sorted(range(n), key=lambda k: -sums[k])
    out: list[Spike] = []
    for k in cand:
        c = sums[k]
        if c < max(6, 3 * base) or len(out) >= top:
            break
        a = k * step
        if any(abs(a - s.t) < win * 1.5 for s in out):
            continue
        ex = [m for t, m in messages if a <= t - lag < a + win and LAUGH.search(m)]
        uniq: list[str] = []
        for m in ex:
            if m.lower() not in (u.lower() for u in uniq):
                uniq.append(m[:40])
            if len(uniq) >= 5:
                break
        out.append(Spike(a, a + win, c, round(c / base, 1), uniq))
    return sorted(out, key=lambda s: s.t)


def describe(spk: list[Spike], ts) -> str:
    """Bloc de texte pour Claude (ts : fonction secondes → « m:ss »)."""
    if not spk:
        return "Pics de rires du chat : aucun pic net."
    return "Pics de rires du chat Twitch (messages MDR/KEKW/😂… en 20 s, normale du chat = ×1) :\n" + "\n".join(
        f"- {ts(s.t)}-{ts(s.end)} : {s.count} messages de rire (×{s.ratio})"
        + (f" ex. « {' » « '.join(s.examples)} »" if s.examples else "") for s in spk)


def best_overlap(spk: list[Spike], a: float, b: float) -> Spike | None:
    """Le plus gros pic qui tombe dans le moment [a, b] (ou juste après : la réaction)."""
    hits = [s for s in spk if s.t < b + 10 and s.end > a]
    return max(hits, key=lambda s: s.count) if hits else None

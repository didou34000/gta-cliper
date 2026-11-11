"""Détection des moments forts dans une VOD à partir de la densité du chat."""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev


@dataclass
class Highlight:
    start: float
    end: float
    peak: float
    score: float  # z-score du pic


def chat_spikes(offsets: list[float], vod_duration: float, window: int = 30,
                min_z: float = 3.0, before: int = 20, after: int = 25,
                max_n: int = 8) -> list[Highlight]:
    """Repère les fenêtres où le chat s'emballe par rapport au reste du live.

    Compare chaque fenêtre à la moyenne des 10 minutes autour (pas du live entier),
    pour qu'un début de live calme ou une fin très active ne faussent pas tout.
    """
    if not offsets or vod_duration <= 0:
        return []
    step = 5
    n = int(vod_duration // step) + 1
    buckets = [0] * n
    for o in offsets:
        i = int(o // step)
        if 0 <= i < n:
            buckets[i] += 1
    w = max(1, window // step)
    counts = [sum(buckets[i:i + w]) for i in range(n)]

    ctx = 600 // step  # 10 minutes de contexte local
    scored: list[tuple[float, int]] = []
    for i, c in enumerate(counts):
        lo, hi = max(0, i - ctx), min(n, i + ctx)
        neigh = counts[lo:hi]
        mu, sd = mean(neigh), pstdev(neigh) or 1.0
        z = (c - mu) / sd
        if z >= min_z and c >= 10:
            scored.append((z, i))

    scored.sort(reverse=True)
    picked: list[Highlight] = []
    for z, i in scored:
        # Le chat réagit 5-15 s après l'action : le pic de chat est APRÈS le moment.
        peak = i * step + window / 2
        start = max(0.0, peak - before - 8)
        end = min(vod_duration, peak + after - 8)
        if any(not (end <= h.start or start >= h.end) for h in picked):
            continue
        picked.append(Highlight(start=start, end=end, peak=peak, score=round(z, 2)))
        if len(picked) >= max_n:
            break
    return sorted(picked, key=lambda h: h.start)

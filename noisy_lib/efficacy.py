# efficacy.py - Compteurs d'efficacite par feature stealth
# IN: bump(feature, n) appelle depuis workers/crawler | OUT: snapshot dict
# APPELE PAR: workers, crawler, page_consent, quic_probe, ech_client | APPELLE: rien

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict

# Module-level singleton: thread-safe counters per feature.
# Format: { feature_key: {"count": N, "last_ts": float, "extra": {...}} }
# Using threading.Lock + simple int ops (no asyncio dependency).

_LOCK = threading.Lock()
_COUNTERS: Dict[str, Dict[str, float]] = defaultdict(lambda: {"count": 0, "last_ts": 0.0})

# DNS prefetch:
#   - cumulatifs (counters Prometheus)
#   - sliding window (deque True/False bornee) pour hit_rate reactif
PREFETCH_WINDOW_SIZE = 1000
_PREFETCH_HITS = 0
_PREFETCH_MISSES = 0
_PREFETCH_WINDOW: Deque[bool] = deque(maxlen=PREFETCH_WINDOW_SIZE)


def bump(feature: str, n: int = 1):
    """Incremente le compteur d'une feature."""
    with _LOCK:
        rec = _COUNTERS[feature]
        rec["count"] += n
        rec["last_ts"] = time.time()


def bump_prefetch(hit: bool):
    """Incremente hits ou misses du DNS prefetch + push dans window."""
    global _PREFETCH_HITS, _PREFETCH_MISSES
    with _LOCK:
        if hit:
            _PREFETCH_HITS += 1
        else:
            _PREFETCH_MISSES += 1
        _PREFETCH_WINDOW.append(hit)
        rec = _COUNTERS["dns_prefetch"]
        rec["count"] += 1
        rec["last_ts"] = time.time()


def snapshot() -> dict:
    """Retourne l'etat courant: {feature: {count, last_ts, hit_rate?}}.

    `hit_rate` reflete les `PREFETCH_WINDOW_SIZE` dernieres observations
    (insensibilite au passe lointain en process longue duree).
    """
    with _LOCK:
        out = {}
        now = time.time()
        for k, v in _COUNTERS.items():
            age = now - v["last_ts"] if v["last_ts"] > 0 else None
            out[k] = {
                "count": int(v["count"]),
                "last_age_s": round(age, 1) if age is not None else None,
            }
        total = _PREFETCH_HITS + _PREFETCH_MISSES
        if total > 0:
            out.setdefault("dns_prefetch", {"count": total, "last_age_s": None})
            window_total = len(_PREFETCH_WINDOW)
            window_hits = sum(1 for h in _PREFETCH_WINDOW if h)
            out["dns_prefetch"]["hit_rate"] = round(window_hits / window_total, 2) if window_total else 0.0
            out["dns_prefetch"]["hits"] = _PREFETCH_HITS
            out["dns_prefetch"]["misses"] = _PREFETCH_MISSES
            out["dns_prefetch"]["window_size"] = window_total
        return out


def reset():
    """Reset (utilise par tests)."""
    global _PREFETCH_HITS, _PREFETCH_MISSES
    with _LOCK:
        _COUNTERS.clear()
        _PREFETCH_HITS = 0
        _PREFETCH_MISSES = 0
        _PREFETCH_WINDOW.clear()

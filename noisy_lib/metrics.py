# metrics.py - Métriques partagées cross-crawler
# IN: user_id, url, domain, status, bytes | OUT: stats agrégées | MODIFIE: état interne
# APPELÉ PAR: crawler.py, dashboard.py, noisy.py | APPELLE: config (categorize_domain)

import asyncio
import collections
import time
from typing import Dict, List

from .config import categorize_domain

log = __import__("logging").getLogger(__name__)

RequestLogEntry = collections.namedtuple(
    "RequestLogEntry", ["ts", "user_id", "url", "domain", "status", "bytes", "error"],
)


class SharedMetrics:
    """Métriques partagées entre tous les crawlers (accès thread-safe via asyncio)."""

    def __init__(self, max_log: int = 200):
        self.request_log: collections.deque = collections.deque(maxlen=max_log)
        self.domain_stats: Dict[str, Dict[str, int]] = {}
        self.tld_counts: Dict[str, int] = {}
        self.total_bytes: int = 0
        self.category_counts: Dict[str, int] = {}
        self.timing_heatmap: Dict[str, int] = {}
        self.recent_errors: collections.deque = collections.deque(maxlen=50)
        self.pause_event: asyncio.Event = asyncio.Event()
        self.pause_event.set()
        self._start_time: float = time.monotonic()

    def log_request(self, user_id: int, url: str, domain: str, status: int, nbytes: int, error: str):
        self.request_log.append(RequestLogEntry(
            ts=time.time(), user_id=user_id, url=url, domain=domain,
            status=status, bytes=nbytes, error=error,
        ))
        if domain not in self.domain_stats:
            self.domain_stats[domain] = {"ok": 0, "fail": 0, "bytes": 0}
        ds = self.domain_stats[domain]
        if 200 <= status < 400:
            ds["ok"] += 1
        else:
            ds["fail"] += 1
        ds["bytes"] += nbytes
        tld = domain.rsplit(".", 1)[-1] if domain and "." in domain else "local"
        self.tld_counts[tld] = self.tld_counts.get(tld, 0) + 1
        cat = categorize_domain(domain)
        self.category_counts[cat] = self.category_counts.get(cat, 0) + 1
        lt = time.localtime()
        hm_key = f"{lt.tm_wday}_{lt.tm_hour}"
        self.timing_heatmap[hm_key] = self.timing_heatmap.get(hm_key, 0) + 1
        self.total_bytes += nbytes
        if error:
            self.recent_errors.append({
                "ts": time.time(), "user_id": user_id,
                "url": url[:120], "domain": domain,
                "status": status, "error": error,
            })

    def domain_health(self, domain: str) -> float:
        ds = self.domain_stats.get(domain)
        if not ds:
            return 1.0
        total = ds["ok"] + ds["fail"]
        if total < 10:
            return 1.0
        return ds["ok"] / total

    def top_domains(self, n: int = 20) -> List[dict]:
        items = sorted(self.domain_stats.items(), key=lambda x: x[1]["ok"] + x[1]["fail"], reverse=True)
        result = []
        for domain, ds in items[:n]:
            total = ds["ok"] + ds["fail"]
            result.append({
                "domain": domain, "ok": ds["ok"], "fail": ds["fail"],
                "total": total,
                "health": round(ds["ok"] / total, 2) if total > 0 else 1.0,
                "bytes": ds["bytes"],
            })
        return result

    def tld_distribution(self) -> List[dict]:
        items = sorted(self.tld_counts.items(), key=lambda x: x[1], reverse=True)
        return [{"tld": f".{tld}", "count": c} for tld, c in items[:15]]

    def category_distribution(self) -> List[dict]:
        items = sorted(self.category_counts.items(), key=lambda x: x[1], reverse=True)
        return [{"category": cat, "count": c} for cat, c in items]

    def fingerprint_score(self) -> dict:
        scores = {}
        n_domains = len(self.domain_stats)
        scores["domain_diversity"] = min(1.0, n_domains / 100) if n_domains > 0 else 0
        n_tlds = len(self.tld_counts)
        scores["tld_diversity"] = min(1.0, n_tlds / 20)
        if len(self.request_log) >= 10:
            logs = list(self.request_log)
            intervals = [logs[i].ts - logs[i - 1].ts for i in range(1, min(50, len(logs)))]
            if intervals:
                mean_i = sum(intervals) / len(intervals)
                variance = sum((x - mean_i) ** 2 for x in intervals) / len(intervals)
                cv = (variance ** 0.5) / mean_i if mean_i > 0 else 0
                scores["timing_variance"] = min(1.0, cv / 1.5)
            else:
                scores["timing_variance"] = 0
        else:
            scores["timing_variance"] = 0
        weights = {"domain_diversity": 0.4, "tld_diversity": 0.3, "timing_variance": 0.3}
        overall = sum(scores[k] * weights[k] for k in weights)
        return {
            "overall": round(overall, 2),
            "domain_diversity": round(scores["domain_diversity"], 2),
            "tld_diversity": round(scores["tld_diversity"], 2),
            "timing_variance": round(scores["timing_variance"], 2),
        }

    @property
    def is_paused(self) -> bool:
        return not self.pause_event.is_set()

    def pause(self):
        self.pause_event.clear()

    def resume(self):
        self.pause_event.set()

# dashboard_collector.py - Collecte et gestion des metriques crawlers
# IN: crawlers, shared_visited, rate_limiter, ua_pool, shared_metrics | OUT: MetricsCollector, helpers
# MODIFIE: .noisy_settings.json | APPELE PAR: dashboard.py, noisy.py | APPELLE: config, profiles

import asyncio
import json
import logging
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

from .config import (
    ALERT_FAIL_THRESHOLD, AUTO_PAUSE_FAIL_THRESHOLD, AUTO_PAUSE_MIN_REQUESTS,
    DEFAULT_URL_BLACKLIST,
    GEO_PROFILES, GENERIC_TLDS, MOBILE_UA_POOL, REGION_PRESETS,
)
from .profiles import UserProfile, _diurnal_weight

if TYPE_CHECKING:
    from .crawler import UserCrawler
    from .metrics import SharedMetrics
    from .profiles import UAPool
    from .rate_limiter import DomainRateLimiter
    from .structures import LRUSet

log = logging.getLogger(__name__)

from . import efficacy as _eff

def _efficacy_snapshot():
    return _eff.snapshot()

STATIC_DIR = Path(__file__).parent / "static"
SETTINGS_FILE = Path(__file__).parent.parent / ".noisy_settings.json"

# Features that spawn background workers; managed by MetricsCollector lifecycle.
STEALTH_WORKER_KEYS = (
    "dns_prefetch", "thirdparty_burst", "background_noise",
    "nxdomain_probes", "stream_noise", "ech", "quic_probe",
)


def _save_settings(data: dict):
    """Sauvegarde les settings dans .noisy_settings.json."""
    try:
        existing = _load_settings()
        existing.update(data)
        SETTINGS_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        log.debug(f"[SETTINGS] sauvegarde: {list(data.keys())}")
    except Exception as e:
        log.warning(f"[SETTINGS] erreur sauvegarde: {e}")


def _load_settings() -> dict:
    """Charge les settings persistes."""
    try:
        if SETTINGS_FILE.exists():
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"[SETTINGS] erreur lecture: {e}")
    return {}


def _get_system_dns() -> List[str]:
    """Detecte les serveurs DNS systeme."""
    try:
        import subprocess
        import platform
        if platform.system() == "Windows":
            out = subprocess.check_output(
                ["powershell", "-Command",
                 "Get-DnsClientServerAddress -AddressFamily IPv4 | Select-Object -ExpandProperty ServerAddresses | Sort-Object -Unique"],
                timeout=5, text=True, stderr=subprocess.DEVNULL,
            )
            return [l.strip() for l in out.strip().splitlines() if l.strip()]
        else:
            with open("/etc/resolv.conf") as f:
                return [l.split()[1] for l in f if l.strip().startswith("nameserver")]
    except Exception:
        return ["unknown"]


def _extract_tld_from_url(url: str) -> str:
    from . import extract_tld
    return extract_tld(url)


class MetricsCollector:
    """Collecte les metriques depuis les crawlers et l'etat partage."""

    def __init__(
        self,
        crawlers: List["UserCrawler"],
        shared_visited: "LRUSet",
        rate_limiter: "DomainRateLimiter",
        ua_pool: "UAPool",
        shared_metrics: "SharedMetrics",
        webhook_url: Optional[str] = None,
        tld_filter: Optional[set] = None,
        regions: Optional[List[str]] = None,
        all_top_sites: Optional[List[str]] = None,
    ):
        self.crawlers = crawlers
        self.shared_visited = shared_visited
        self.rate_limiter = rate_limiter
        self.ua_pool = ua_pool
        self.shared_metrics = shared_metrics
        self.webhook_url = webhook_url
        self.tld_filter = tld_filter or set()
        self.regions = regions or []
        self.all_top_sites = all_top_sites or []
        self._search_workers = 0
        self._crawler_tasks: dict = {}  # user_id -> asyncio.Task
        self._crawler_params: dict = {}  # stored from first crawler
        self._next_user_id = max((c.profile.user_id for c in crawlers), default=-1) + 1
        self._start_time = time.monotonic()
        self._prev_visited = 0
        self._prev_time = time.monotonic()
        self._alert_fired = False
        self.auto_pause_enabled = True
        self._auto_paused = False
        self._stealth_workers: dict = {k: [] for k in STEALTH_WORKER_KEYS}
        self._stealth_ctx: dict = {}  # dns_hosts, dns_cache
        self._drain_tasks: set = set()  # refs to cancellation-drain tasks (prevent GC)

    def collect(self) -> dict:
        now = time.monotonic()
        total_v = sum(c.stats["visited"] for c in self.crawlers)
        total_f = sum(c.stats["failed"] for c in self.crawlers)
        total_q = sum(c.stats["queued"] for c in self.crawlers)
        total_4xx = sum(c.stats["client_errors"] for c in self.crawlers)
        total_5xx = sum(c.stats["server_errors"] for c in self.crawlers)
        total_net = sum(c.stats["network_errors"] for c in self.crawlers)
        total_bytes = sum(c.stats["bytes"] for c in self.crawlers)
        elapsed = now - self._prev_time
        rps = (total_v - self._prev_visited) / elapsed if elapsed > 0 else 0.0
        fail_pct = total_f / (total_v + total_f) * 100 if (total_v + total_f) > 0 else 0.0
        self._prev_visited, self._prev_time = total_v, now

        # Alert check
        alert_active = fail_pct > ALERT_FAIL_THRESHOLD and (total_v + total_f) > 20

        users = []
        for c in self.crawlers:
            users.append({
                "id": c.profile.user_id,
                "visited": c.stats["visited"],
                "failed": c.stats["failed"],
                "client_errors": c.stats["client_errors"],
                "server_errors": c.stats["server_errors"],
                "network_errors": c.stats["network_errors"],
                "queued": c.stats["queued"],
                "bytes": c.stats["bytes"],
                "ua": c.profile.ua[:80],
                "diurnal_weight": round(c.profile.diurnal_weight(), 2),
                "is_mobile": getattr(c.profile, "is_mobile", False),
                "geo": getattr(c.profile, "geo", None),
                "active": getattr(c.profile, "is_active_hour", lambda: True)(),
            })

        # Diurnal curve (24 points)
        lt = time.localtime()
        hour_now = lt.tm_hour + lt.tm_min / 60
        diurnal_curve = []
        for h in range(24):
            diurnal_curve.append({"hour": h, "weight": round(_diurnal_weight(h), 2)})

        # Bandwidth
        uptime_s = now - self._start_time
        bw_kbps = (total_bytes / 1024) / uptime_s if uptime_s > 0 else 0

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime_seconds": round(uptime_s),
            "aggregate": {
                "visited": total_v,
                "failed": total_f,
                "client_errors": total_4xx,
                "server_errors": total_5xx,
                "network_errors": total_net,
                "queued": total_q,
                "rps": round(rps, 2),
                "fail_pct": round(fail_pct, 2),
                "unique_urls": len(self.shared_visited),
                "active_domains": self.rate_limiter.active_domains_count(),
                "total_bytes": total_bytes,
                "bandwidth_kbps": round(bw_kbps, 1),
                "alert_active": alert_active,
            },
            "users": users,
            "diurnal_curve": diurnal_curve,
            "current_hour": round(hour_now, 1),
            "top_domains": self.shared_metrics.top_domains(20),
            "tld_distribution": self.shared_metrics.tld_distribution(),
            "category_distribution": self.shared_metrics.category_distribution(),
            "timing_heatmap": self.shared_metrics.timing_heatmap,
            "recent_errors": list(self.shared_metrics.recent_errors),
            "request_log": [
                {"ts": e.ts, "user_id": e.user_id, "url": e.url[:100],
                 "domain": e.domain, "status": e.status, "bytes": e.bytes}
                for e in list(self.shared_metrics.request_log)[-50:]
            ],
            "fingerprint": self.shared_metrics.fingerprint_score(),
            "nsfw_blocklist_size": len(self._crawler_params.get("domain_blocklist", set())) if self._crawler_params else 0,
            "dns_servers": _get_system_dns(),
            "paused": self.shared_metrics.is_paused,
            "features": {
                "schedule": self.crawlers[0].profile.schedule if self.crawlers and hasattr(self.crawlers[0].profile, "schedule") else None,
                "search_workers": self._search_workers,
                "mobile_count": sum(1 for c in self.crawlers if getattr(c.profile, "is_mobile", False)),
                "geo_profiles": sorted(set(getattr(c.profile, "geo", None) for c in self.crawlers if getattr(c.profile, "geo", None))),
                "diurnal": self.crawlers[0].profile.diurnal_enabled if self.crawlers and hasattr(self.crawlers[0].profile, "diurnal_enabled") else True,
                "auto_pause": self.auto_pause_enabled,
                "tls_rotation": self.crawlers[0].features.get("tls_rotation", True) if self.crawlers else True,
                "realistic_depth": self.crawlers[0].features.get("realistic_depth", True) if self.crawlers else True,
                "referer_chains": self.crawlers[0].features.get("referer_chains", True) if self.crawlers else True,
                "asset_fetching": self.crawlers[0].features.get("asset_fetching", True) if self.crawlers else True,
                "bandwidth_throttle": self.crawlers[0].features.get("bandwidth_throttle", False) if self.crawlers else False,
                "dns_optimized": self.crawlers[0].features.get("dns_optimized", False) if self.crawlers else False,
                "dns_prefetch": self.crawlers[0].features.get("dns_prefetch", False) if self.crawlers else False,
                "thirdparty_burst": self.crawlers[0].features.get("thirdparty_burst", False) if self.crawlers else False,
                "background_noise": self.crawlers[0].features.get("background_noise", False) if self.crawlers else False,
                "nxdomain_probes": self.crawlers[0].features.get("nxdomain_probes", False) if self.crawlers else False,
                "ech": self.crawlers[0].features.get("ech", False) if self.crawlers else False,
                "stream_noise": self.crawlers[0].features.get("stream_noise", False) if self.crawlers else False,
                "cookie_consent": self.crawlers[0].features.get("cookie_consent", True) if self.crawlers else True,
                "quic_probe": self.crawlers[0].features.get("quic_probe", False) if self.crawlers else False,
            },
            "feature_status": self.stealth_worker_status(),
            "efficacy": _efficacy_snapshot(),
        }

    def get_runtime_config(self) -> dict:
        if not self.crawlers:
            return {}
        c = self.crawlers[0]
        cfg = {
            "num_users": len(self.crawlers),
            "min_sleep": c.min_sleep,
            "max_sleep": c.max_sleep,
            "max_depth": c.max_depth,
            "concurrency": c.concurrency,
            "max_links_per_page": c.max_links_per_page,
            "domain_delay": self.rate_limiter._domain_delay,
        }
        if self.tld_filter:
            cfg["tld_filter"] = sorted(self.tld_filter)
        if self.regions:
            cfg["regions"] = sorted(self.regions)
        return cfg

    def apply_config(self, data: dict) -> list:
        errors = []
        safe = {}
        for key, cast, lo, hi in [
            ("min_sleep", float, 0.1, 300),
            ("max_sleep", float, 0.1, 600),
            ("max_depth", int, 1, 50),
            ("max_links_per_page", int, 1, 500),
            ("domain_delay", float, 0, 120),
        ]:
            if key in data:
                try:
                    v = cast(data[key])
                    if not (lo <= v <= hi):
                        errors.append(f"{key}: doit etre entre {lo} et {hi}")
                    else:
                        safe[key] = v
                except (ValueError, TypeError):
                    errors.append(f"{key}: valeur invalide")
        if errors:
            return errors
        for c in self.crawlers:
            if "min_sleep" in safe:
                c.min_sleep = safe["min_sleep"]
            if "max_sleep" in safe:
                c.max_sleep = safe["max_sleep"]
            if "max_depth" in safe:
                c.max_depth = safe["max_depth"]
            if "max_links_per_page" in safe:
                c.max_links_per_page = safe["max_links_per_page"]
        if "domain_delay" in safe:
            self.rate_limiter.domain_delay = safe["domain_delay"]
        _save_settings({"config": safe})
        return []

    def restore_saved_settings(self):
        """Restaure les settings persistes depuis .noisy_settings.json."""
        saved = _load_settings()
        if not saved:
            return
        restored = []
        if "features" in saved:
            try:
                self.apply_features(saved["features"])
                restored.append("features")
            except Exception as e:
                log.warning(f"[SETTINGS] erreur restore features: {e}")
        if "config" in saved:
            try:
                self.apply_config(saved["config"])
                restored.append("config")
            except Exception as e:
                log.warning(f"[SETTINGS] erreur restore config: {e}")
        if "tld_filter" in saved:
            try:
                tf = saved["tld_filter"]
                self.apply_tld_filter(tf.get("regions", []), tf.get("custom_tlds", []))
                restored.append("tld_filter")
            except Exception as e:
                log.warning(f"[SETTINGS] erreur restore tld_filter: {e}")
        if restored:
            log.info(f"[SETTINGS] restaure: {', '.join(restored)}")

    def set_crawler_params(self, stop_event, top_sites, params: dict):
        """Stocke les parametres necessaires pour creer de nouveaux crawlers."""
        self._stop_event = stop_event
        self._filtered_sites = top_sites
        self._crawler_params = params

    def setup_stealth_context(self, dns_hosts, dns_cache):
        """Context requis pour spawn/cancel des workers stealth via toggles."""
        self._stealth_ctx = {"dns_hosts": dns_hosts, "dns_cache": dns_cache}

    def _start_stealth_worker(self, key: str):
        """Spawn le(s) worker(s) pour une feature stealth. Idempotent."""
        if not self._stealth_ctx:
            log.warning(f"[FEATURES] {key}: context non init, skip spawn")
            return
        # Already running?
        live = [t for t in self._stealth_workers.get(key, []) if not t.done()]
        if live:
            return
        stop = self._stop_event
        dns_hosts = self._stealth_ctx["dns_hosts"]
        dns_cache = self._stealth_ctx["dns_cache"]
        bl = self._crawler_params.get("domain_blocklist", set()) if self._crawler_params else set()
        tasks = []
        if key == "dns_prefetch":
            from .dns_prefetch import dns_prefetch_worker
            tasks.append(asyncio.create_task(
                dns_prefetch_worker(dns_hosts, stop, dns_cache, domain_blocklist=bl, worker_id=0)))
        elif key == "thirdparty_burst":
            from .dns_stealth import thirdparty_burst_worker, microburst_worker
            tasks.append(asyncio.create_task(thirdparty_burst_worker(dns_hosts, stop, dns_cache)))
            tasks.append(asyncio.create_task(microburst_worker(dns_hosts, stop, dns_cache)))
        elif key == "background_noise":
            from .dns_stealth import background_noise_worker
            tasks.append(asyncio.create_task(background_noise_worker(stop, dns_cache)))
        elif key == "nxdomain_probes":
            from .dns_stealth import nxdomain_probe_worker
            tasks.append(asyncio.create_task(nxdomain_probe_worker(stop, dns_cache)))
        elif key == "stream_noise":
            from .stream_noise import stream_noise_worker
            tasks.append(asyncio.create_task(stream_noise_worker(stop, dns_cache)))
        elif key == "ech":
            from .ech_client import ech_worker
            tasks.append(asyncio.create_task(ech_worker(dns_hosts, stop)))
        elif key == "quic_probe":
            from .quic_probe import quic_worker
            import random as _r
            tasks.append(asyncio.create_task(quic_worker(stop, _r.Random(), dns_cache)))
        if tasks:
            self._stealth_workers[key] = tasks
            log.info(f"[FEATURES] {key}: {len(tasks)} worker(s) demarre(s)")

    def _stop_stealth_worker(self, key: str):
        """Cancel tous les workers d'une feature + drain en arriere-plan."""
        tasks = self._stealth_workers.get(key, [])
        alive = [t for t in tasks if not t.done()]
        for t in alive:
            t.cancel()
        self._stealth_workers[key] = []
        if alive:
            drain = asyncio.create_task(self._drain_cancelled(alive, key))
            self._drain_tasks.add(drain)
            drain.add_done_callback(self._drain_tasks.discard)
            log.info(f"[FEATURES] {key}: {len(alive)} worker(s) arrete(s)")

    async def _drain_cancelled(self, tasks, key: str):
        """Attend la terminaison propre de tasks cancelled (evite RuntimeWarning)."""
        await asyncio.gather(*tasks, return_exceptions=True)

    def stealth_worker_status(self) -> dict:
        """Pour chaque feature worker: running (int), expected (on/off)."""
        status = {}
        features = self.crawlers[0].features if self.crawlers else {}
        for key in STEALTH_WORKER_KEYS:
            tasks = self._stealth_workers.get(key, [])
            running = sum(1 for t in tasks if not t.done())
            enabled = bool(features.get(key, False))
            if enabled and running > 0:
                state = "running"
            elif enabled and running == 0:
                state = "error"  # toggle ON mais worker mort
            else:
                state = "off"
            status[key] = {"state": state, "running": running}
        return status

    def sync_stealth_workers(self):
        """Au demarrage: spawn les workers pour toutes les features deja ON."""
        features = self.crawlers[0].features if self.crawlers else {}
        for key in STEALTH_WORKER_KEYS:
            if features.get(key, False):
                self._start_stealth_worker(key)

    def add_user(self) -> dict:
        """Cree un nouveau crawler virtuel et le lance."""
        if not self._crawler_params:
            return {"error": "parametres crawler non initialises"}

        from .crawler import UserCrawler
        from .profiles import is_mobile_ua
        p = self._crawler_params
        uid = self._next_user_id
        self._next_user_id += 1

        # Inherit profile state from existing crawlers (geo, schedule, diurnal, mobile_ratio)
        ref = self.crawlers[0].profile if self.crawlers else None
        inherited_geo = ref.geo if ref else None
        inherited_schedule = ref.schedule if ref else None
        inherited_diurnal = ref.diurnal_enabled if ref else True

        # Decide if new user should be mobile to maintain current ratio
        n_mobile_now = sum(1 for c in self.crawlers if c.profile.is_mobile)
        mobile_ratio = n_mobile_now / len(self.crawlers) if self.crawlers else 0
        force_mobile = self.crawlers and (n_mobile_now / (len(self.crawlers) + 1)) < mobile_ratio

        if force_mobile:
            from .config import MOBILE_UA_POOL
            ua = random.choice(MOBILE_UA_POOL)
        else:
            ua = self.ua_pool.sample(1, rng=random.Random())[0]

        profile = UserProfile(
            user_id=uid, ua=ua, rng=random.Random(),
            geo=inherited_geo,
            is_mobile=force_mobile or is_mobile_ua(ua),
            schedule=inherited_schedule,
        )
        profile.diurnal_enabled = inherited_diurnal
        sites = list(self._filtered_sites)
        profile.rng.shuffle(sites)

        crawler = UserCrawler(
            profile=profile, shared_root_urls=sites[:500],
            shared_visited=self.shared_visited, rate_limiter=self.rate_limiter,
            max_depth=p["max_depth"], concurrency=p["concurrency"],
            min_sleep=p["min_sleep"], max_sleep=p["max_sleep"],
            max_queue_size=p["max_queue_size"], max_links_per_page=p["max_links_per_page"],
            url_blacklist=DEFAULT_URL_BLACKLIST, stop_event=self._stop_event,
            total_connections=p["total_connections"],
            connections_per_host=p["connections_per_host"],
            keepalive_timeout=p["keepalive_timeout"],
            shared_metrics=self.shared_metrics,
            domain_blocklist=p.get("domain_blocklist", set()),
            cookie_persist=p.get("cookie_persist", False),
            features=p.get("features", {}),
        )
        self.crawlers.append(crawler)
        task = asyncio.create_task(crawler.run())
        self._crawler_tasks[uid] = task
        log.info(f"[DASHBOARD] user {uid} ajoute (total: {len(self.crawlers)})")
        return {"status": "ok", "user_id": uid, "total_users": len(self.crawlers)}

    async def remove_user(self, user_id: Optional[int] = None) -> dict:
        """Arrete et supprime un crawler. Si user_id=None, supprime le dernier."""
        if len(self.crawlers) <= 1:
            return {"error": "impossible de supprimer le dernier user"}

        target = None
        if user_id is not None:
            target = next((c for c in self.crawlers if c.profile.user_id == user_id), None)
            if not target:
                return {"error": f"user {user_id} non trouve"}
        else:
            target = self.crawlers[-1]

        uid = target.profile.user_id
        self.crawlers.remove(target)
        if uid in self._crawler_tasks:
            self._crawler_tasks[uid].cancel()
            del self._crawler_tasks[uid]
        await target.close()
        log.info(f"[DASHBOARD] user {uid} supprime (total: {len(self.crawlers)})")
        return {"status": "ok", "removed_user_id": uid, "total_users": len(self.crawlers)}

    def _get_all_features_state(self) -> dict:
        """Retourne l'etat complet de toutes les features pour persistence."""
        state = {}
        if self.crawlers:
            c0 = self.crawlers[0]
            # Schedule
            state["schedule"] = f"{c0.profile.schedule[0]}-{c0.profile.schedule[1]}" if c0.profile.schedule else None
            # Geo
            state["geo"] = c0.profile.geo
            # Mobile ratio
            n_mobile = sum(1 for c in self.crawlers if c.profile.is_mobile)
            state["mobile_ratio"] = n_mobile / len(self.crawlers) if self.crawlers else 0
            # Search workers
            state["search_workers"] = self._search_workers
            # Auto-pause
            state["auto_pause"] = self.auto_pause_enabled
            # Diurnal
            state["diurnal"] = c0.profile.diurnal_enabled
            # Boolean stealth features from crawler.features dict
            for key in ("tls_rotation", "realistic_depth", "referer_chains",
                        "asset_fetching", "bandwidth_throttle",
                        "dns_optimized", "dns_prefetch",
                        "thirdparty_burst", "background_noise", "nxdomain_probes",
                        "ech", "stream_noise"):
                state[key] = c0.features.get(key, False)
        return state

    def apply_features(self, data: dict) -> dict:
        """Applique les features stealth live."""
        changes = []

        # Schedule
        if "schedule" in data:
            sched = data["schedule"]
            if sched is None or sched == "":
                for c in self.crawlers:
                    c.profile.schedule = None
                changes.append("schedule=off")
            else:
                try:
                    parts = str(sched).split("-")
                    s, e = int(parts[0]), int(parts[1])
                    if 0 <= s <= 23 and 0 <= e <= 23:
                        for c in self.crawlers:
                            c.profile.schedule = (s, e)
                        changes.append(f"schedule={s}h-{e}h")
                except (ValueError, IndexError):
                    return {"error": f"schedule invalide: {sched}"}

        # Geo
        if "geo" in data:
            geo = data["geo"] if data["geo"] else None
            if geo and geo not in GEO_PROFILES:
                return {"error": f"geo inconnu: {geo}"}
            for c in self.crawlers:
                c.profile.geo = geo
                if geo:
                    gd = GEO_PROFILES[geo]
                    c.profile._accept_lang = gd["lang"]
                    c.profile._tz_offset = gd["tz_offset"]
                else:
                    c.profile._accept_lang = "en-US,en;q=0.9"
                    c.profile._tz_offset = 0
            changes.append(f"geo={geo or 'off'}")

        # Mobile ratio
        if "mobile_ratio" in data:
            from .profiles import is_mobile_ua
            ratio = float(data["mobile_ratio"])
            if not (0 <= ratio <= 1):
                return {"error": "mobile_ratio doit etre 0-1"}
            n_mobile = int(len(self.crawlers) * ratio)
            for i, c in enumerate(self.crawlers):
                should_mobile = i >= (len(self.crawlers) - n_mobile)
                c.profile.is_mobile = should_mobile
                rng = getattr(c.profile, "rng", None) or random.Random()
                if should_mobile and not is_mobile_ua(c.profile.ua):
                    c.profile.ua = rng.choice(MOBILE_UA_POOL)
                elif not should_mobile and is_mobile_ua(c.profile.ua):
                    c.profile.ua = self.ua_pool.sample(1, rng=rng)[0]
                    # If pool returned mobile, keep cycling up to 5 times
                    for _ in range(5):
                        if not is_mobile_ua(c.profile.ua):
                            break
                        c.profile.ua = self.ua_pool.sample(1, rng=rng)[0]
            changes.append(f"mobile={n_mobile}/{len(self.crawlers)}")

        # Search workers
        if "search_workers" in data:
            target = int(data["search_workers"])
            current = self._search_workers
            if target > current:
                from .workers import search_noise_worker
                bl = self._crawler_params.get("domain_blocklist", set()) if self._crawler_params else set()
                for i in range(current, target):
                    task = asyncio.create_task(search_noise_worker(self._stop_event, worker_id=i, domain_blocklist=bl))
                    self._crawler_tasks[f"search_{i}"] = task
                changes.append(f"search_workers={current}->{target}")
            elif target < current:
                for i in range(target, current):
                    key = f"search_{i}"
                    if key in self._crawler_tasks:
                        self._crawler_tasks[key].cancel()
                        del self._crawler_tasks[key]
                changes.append(f"search_workers={current}->{target}")
            self._search_workers = target

        # Auto-pause
        if "auto_pause" in data:
            self.auto_pause_enabled = bool(data["auto_pause"])
            changes.append(f"auto_pause={'on' if self.auto_pause_enabled else 'off'}")

        # Diurnal
        if "diurnal" in data:
            enabled = bool(data["diurnal"])
            for c in self.crawlers:
                c.profile.diurnal_enabled = enabled
            changes.append(f"diurnal={'on' if enabled else 'off'}")

        # New stealth features — propagate to crawler.features dict
        for key in ("tls_rotation", "realistic_depth", "referer_chains",
                    "asset_fetching", "bandwidth_throttle",
                    "dns_optimized", "dns_prefetch",
                    "thirdparty_burst", "background_noise", "nxdomain_probes",
                    "ech", "stream_noise"):
            if key in data:
                val = bool(data[key])
                for c in self.crawlers:
                    c.features[key] = val
                # Worker-backed features: spawn/cancel on toggle
                if key in STEALTH_WORKER_KEYS:
                    if val:
                        self._start_stealth_worker(key)
                    else:
                        self._stop_stealth_worker(key)
                changes.append(f"{key}={'on' if val else 'off'}")

        log.info(f"[FEATURES] {', '.join(changes)}")
        # Save FULL features state (not just the partial data from this click)
        full_features = self._get_all_features_state()
        _save_settings({"features": full_features})
        return {"status": "ok", "changes": changes}

    def apply_tld_filter(self, regions: List[str], custom_tlds: List[str]) -> dict:
        """Applique un nouveau filtre TLD live sur les crawlers."""
        allowed = set()
        for r in regions:
            allowed |= REGION_PRESETS.get(r, set())
        allowed |= {t.strip().lower() for t in custom_tlds if t.strip()}
        self.regions = regions
        self.tld_filter = allowed

        if not self.all_top_sites:
            return {"status": "ok", "filtered": 0, "message": "pas de sites CRUX charges"}

        if allowed:
            filtered = [s for s in self.all_top_sites
                        if _extract_tld_from_url(s) in GENERIC_TLDS or _extract_tld_from_url(s) in allowed]
        else:
            filtered = list(self.all_top_sites)

        for c in self.crawlers:
            shuffled = list(filtered)
            c.rng.shuffle(shuffled)
            c.root_urls = set(shuffled[:500])
            # Drain queue and refill with filtered sites
            while not c.queue.empty():
                try:
                    c.queue.get_nowait()
                    c.queue.task_done()
                except Exception:
                    break
            for url in shuffled[:200]:
                try:
                    c.queue.put_nowait((url, 0, None, c.max_depth))
                except Exception:
                    break
        log.info(f"[TLD] Filtre live applique: {len(filtered)} sites (ccTLD: {sorted(allowed) if allowed else 'aucun'})")
        _save_settings({"tld_filter": {"regions": regions, "custom_tlds": custom_tlds}})
        return {"status": "ok", "filtered": len(filtered), "tld_filter": sorted(allowed)}

    def prometheus_metrics(self) -> str:
        lines = []
        total_v = sum(c.stats["visited"] for c in self.crawlers)
        total_f = sum(c.stats["failed"] for c in self.crawlers)
        total_4xx = sum(c.stats["client_errors"] for c in self.crawlers)
        total_5xx = sum(c.stats["server_errors"] for c in self.crawlers)
        total_net = sum(c.stats["network_errors"] for c in self.crawlers)
        total_bytes = sum(c.stats["bytes"] for c in self.crawlers)
        lines.append(f"# HELP noisy_requests_total Total HTTP requests")
        lines.append(f"# TYPE noisy_requests_total counter")
        lines.append(f'noisy_requests_total{{status="ok"}} {total_v}')
        lines.append(f'noisy_requests_total{{status="client_error"}} {total_4xx}')
        lines.append(f'noisy_requests_total{{status="server_error"}} {total_5xx}')
        lines.append(f'noisy_requests_total{{status="network_error"}} {total_net}')
        lines.append(f"# HELP noisy_bytes_total Total bytes received")
        lines.append(f"# TYPE noisy_bytes_total counter")
        lines.append(f"noisy_bytes_total {total_bytes}")
        lines.append(f"# HELP noisy_unique_urls Unique URLs visited")
        lines.append(f"# TYPE noisy_unique_urls gauge")
        lines.append(f"noisy_unique_urls {len(self.shared_visited)}")
        lines.append(f"# HELP noisy_active_domains Active domains in rate limiter")
        lines.append(f"# TYPE noisy_active_domains gauge")
        lines.append(f"noisy_active_domains {self.rate_limiter.active_domains_count()}")
        for c in self.crawlers:
            uid = c.profile.user_id
            lines.append(f'noisy_user_visited{{user="{uid}"}} {c.stats["visited"]}')
            lines.append(f'noisy_user_failed{{user="{uid}"}} {c.stats["failed"]}')
        return "\n".join(lines) + "\n"

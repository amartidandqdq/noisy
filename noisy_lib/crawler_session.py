# crawler_session.py - Lifecycle session HTTP pour UserCrawler
# IN: profile, connector config | OUT: aiohttp session | MODIFIE: cookie jar
# APPELE PAR: crawler.py | APPELLE: config, cookie_store, throttle

import asyncio
import logging
from typing import Dict, List, Optional

import aiohttp

from .config import DNS_CACHE_TTL, MAX_HEADER_SIZE
from .cookie_store import load_cookies, save_cookies
from .metrics import SharedMetrics
from .profiles import UserProfile
from .rate_limiter import DomainRateLimiter
from .structures import BoundedDict, LRUSet
from .throttle import assign_throttle

log = logging.getLogger(__name__)


class CrawlerBase:
    """Base: gestion session, connecteur, cookies, domaines."""

    def __init__(
        self, profile: UserProfile, shared_root_urls: List[str],
        shared_visited: LRUSet, rate_limiter: DomainRateLimiter,
        max_depth: int, concurrency: int, min_sleep: float, max_sleep: float,
        max_queue_size: int, max_links_per_page: int, url_blacklist: List[str],
        stop_event: asyncio.Event, total_connections: int,
        connections_per_host: int, keepalive_timeout: int,
        shared_metrics: Optional[SharedMetrics] = None,
        domain_blocklist: Optional[set] = None,
        cookie_persist: bool = False,
        features: Optional[dict] = None,
    ):
        self.profile = profile
        self.rng = profile.rng
        self.root_urls = set(shared_root_urls)
        self.shared_visited = shared_visited
        self.rate_limiter = rate_limiter
        self.stop_event = stop_event
        self.max_depth = max_depth
        self.concurrency = concurrency
        self.min_sleep = min_sleep
        self.max_sleep = max_sleep
        self.max_links_per_page = max_links_per_page
        self.url_blacklist = url_blacklist
        self.domain_blocklist = domain_blocklist or set()
        self.cookie_persist = cookie_persist
        self.features = features or {}
        self.failed_counts: BoundedDict = BoundedDict(maxsize=10_000)
        self.max_failures = 3
        self.stats: Dict[str, int] = {
            "visited": 0, "failed": 0, "client_errors": 0,
            "server_errors": 0, "network_errors": 0, "queued": 0,
            "bytes": 0,
        }
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        for url in shared_root_urls:
            try:
                self.queue.put_nowait((url, 0, None, max_depth))
            except asyncio.QueueFull:
                break
        self.semaphore = asyncio.Semaphore(concurrency)
        self._connector = aiohttp.TCPConnector(
            limit=total_connections, limit_per_host=connections_per_host,
            ttl_dns_cache=DNS_CACHE_TTL, keepalive_timeout=keepalive_timeout,
        )
        self._session: Optional[aiohttp.ClientSession] = None
        self._cookie_jar: Optional[aiohttp.CookieJar] = None
        self.shared_metrics = shared_metrics
        self._throttle = assign_throttle(profile.is_mobile, self.rng) if self.features.get("bandwidth_throttle") else None

    async def _session_get(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._cookie_jar = aiohttp.CookieJar(unsafe=True)
            if self.cookie_persist:
                saved = load_cookies(self.profile.user_id)
                for domain, cookies in saved.items():
                    for name, value in cookies.items():
                        self._cookie_jar.update_cookies({name: value})
            self._session = aiohttp.ClientSession(
                connector=self._connector, cookie_jar=self._cookie_jar,
                max_line_size=MAX_HEADER_SIZE, max_field_size=MAX_HEADER_SIZE,
            )
        return self._session

    async def close(self):
        if self.cookie_persist and self._session and self._cookie_jar:
            try:
                domain_cookies = {}
                for cookie in self._cookie_jar:
                    domain = cookie.get("domain", "unknown")
                    if domain not in domain_cookies:
                        domain_cookies[domain] = {}
                    domain_cookies[domain][cookie.key] = cookie.value
                save_cookies({}, self.profile.user_id, domain_cookies)
            except Exception:
                pass
        if self._session:
            await self._session.close()
            self._session = None
        await self._connector.close()

    def _domain_blocked(self, host: str) -> bool:
        parts = host.split(".")
        return any(".".join(parts[i:]) in self.domain_blocklist for i in range(len(parts)))

    def _record_failure(self, url: str):
        count = (self.failed_counts.get(url, 0) or 0) + 1
        if count >= self.max_failures:
            self.failed_counts.pop(url, None)
            self.root_urls.discard(url)
        else:
            self.failed_counts.set(url, count)

    def _enqueue(self, url: str, depth: int, referrer: Optional[str], session_max: int = None):
        try:
            self.queue.put_nowait((url, depth, referrer, session_max or self.max_depth))
            self.stats["queued"] += 1
        except asyncio.QueueFull:
            pass

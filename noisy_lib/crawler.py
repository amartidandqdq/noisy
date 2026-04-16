# crawler.py - Orchestration crawl par utilisateur virtuel
# IN: UserProfile, shared state | OUT: none | MODIFIE: LRUSet visited, stats dict
# APPELÉ PAR: noisy.py | APPELLE: metrics, rate_limiter, fetch_client, extractor, profiles

import asyncio
import logging
import ssl
import time
from typing import Dict, List, Optional
from urllib.parse import urlsplit

import aiohttp

from .config import DNS_CACHE_TTL, MAX_HEADER_SIZE
from .extractor import extract_links
from .fetch_client import fetch_with_retry
from .metrics import SharedMetrics
from .profiles import UserProfile, _activity_pause_seconds
from .rate_limiter import DomainRateLimiter
from .structures import BoundedDict, LRUSet

log = logging.getLogger(__name__)


class UserCrawler:
    def __init__(
        self, profile: UserProfile, shared_root_urls: List[str],
        shared_visited: LRUSet, rate_limiter: DomainRateLimiter,
        max_depth: int, concurrency: int, min_sleep: float, max_sleep: float,
        max_queue_size: int, max_links_per_page: int, url_blacklist: List[str],
        stop_event: asyncio.Event, total_connections: int,
        connections_per_host: int, keepalive_timeout: int,
        shared_metrics: Optional["SharedMetrics"] = None,
        domain_blocklist: Optional[set] = None,
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
                self.queue.put_nowait((url, 0, None))
            except asyncio.QueueFull:
                break
        self.semaphore = asyncio.Semaphore(concurrency)
        self._connector = aiohttp.TCPConnector(
            limit=total_connections, limit_per_host=connections_per_host,
            ttl_dns_cache=DNS_CACHE_TTL, keepalive_timeout=keepalive_timeout,
        )
        self._session: Optional[aiohttp.ClientSession] = None
        self.shared_metrics = shared_metrics

    async def _session_get(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._cookie_jar = aiohttp.CookieJar(unsafe=True)
            self._session = aiohttp.ClientSession(
                connector=self._connector, cookie_jar=self._cookie_jar,
                max_line_size=MAX_HEADER_SIZE, max_field_size=MAX_HEADER_SIZE,
            )
        return self._session

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None
        await self._connector.close()

    def _domain_blocked(self, host: str) -> bool:
        """Vérifie si le hostname ou un domaine parent est dans la blocklist (O(1))."""
        parts = host.split(".")
        return any(".".join(parts[i:]) in self.domain_blocklist for i in range(len(parts)))

    async def fetch(self, url: str, depth: int, referrer: Optional[str]) -> Optional[List]:
        async with self.semaphore:
            domain = urlsplit(url).hostname
            if not domain or any(b in url for b in self.url_blacklist):
                return None
            if self.domain_blocklist and self._domain_blocked(domain):
                return None
            if url in self.shared_visited:
                return None
            # Pause support
            if self.shared_metrics and self.shared_metrics.is_paused:
                await self.shared_metrics.pause_event.wait()
            # Domain health: skip domains with < 20% success rate
            if self.shared_metrics and self.shared_metrics.domain_health(domain) < 0.2:
                return None
            self.shared_visited.add(url)
            log.debug(f"[FETCH] u={self.profile.user_id} depth={depth} url={url}")
            session = await self._session_get()
            try:
                await self.rate_limiter.wait(domain, self.rng)
                result = await fetch_with_retry(session, url, self.profile.get_headers(referrer))
                if not result.ok:
                    self.stats["failed"] += 1
                    if result.is_client_error:
                        self.stats["client_errors"] += 1
                    elif result.is_server_error:
                        self.stats["server_errors"] += 1
                        self.shared_visited.discard(url)
                    if self.shared_metrics:
                        self.shared_metrics.log_request(
                            self.profile.user_id, url, domain,
                            result.status, 0, result.error_msg,
                        )
                    return None
                html = result.html
                self.stats["visited"] += 1
                self.stats["bytes"] += result.bytes_received
                if self.shared_metrics:
                    self.shared_metrics.log_request(
                        self.profile.user_id, url, domain,
                        result.status, result.bytes_received, "",
                    )
                links = extract_links(html, url, blacklist=self.url_blacklist, domain_blocklist=self.domain_blocklist)
                del html
                if links:
                    links = self.rng.sample(links, min(len(links), self.max_links_per_page))
                if self.rng.random() < 0.05:
                    for root in self.root_urls:
                        self._enqueue(root, 0, None)
                pause = _activity_pause_seconds(self.rng)
                if pause:
                    await asyncio.sleep(pause)
                else:
                    weight = max(0.05, self.profile.diurnal_weight())
                    await asyncio.sleep(
                        self.rng.uniform(self.min_sleep, self.max_sleep)
                        * (1 + depth * 0.3) * self.rng.uniform(0.8, 1.5) / weight
                    )
                self.failed_counts.pop(url, None)
                return [(lnk, url) for lnk in links] if links else []
            except (aiohttp.ClientError, asyncio.TimeoutError, ssl.SSLError) as e:
                self.shared_visited.discard(url)
                self.stats["failed"] += 1
                self.stats["network_errors"] += 1
                self._record_failure(url)
                if self.shared_metrics:
                    self.shared_metrics.log_request(
                        self.profile.user_id, url, domain, 0, 0, str(e)[:100],
                    )
                return None
            except Exception as e:
                self.shared_visited.discard(url)
                self.stats["failed"] += 1
                self.stats["network_errors"] += 1
                log.error(f"[ERREUR] fetch | u={self.profile.user_id} url={url} {e}")
                self._record_failure(url)
                if self.shared_metrics:
                    self.shared_metrics.log_request(
                        self.profile.user_id, url, domain, 0, 0, str(e)[:100],
                    )
                return None

    def _record_failure(self, url: str):
        count = (self.failed_counts.get(url, 0) or 0) + 1
        if count >= self.max_failures:
            self.failed_counts.pop(url, None)
            self.root_urls.discard(url)
        else:
            self.failed_counts.set(url, count)

    def _enqueue(self, url: str, depth: int, referrer: Optional[str]):
        try:
            self.queue.put_nowait((url, depth, referrer))
            self.stats["queued"] += 1
        except asyncio.QueueFull:
            pass

    async def crawl_worker(self):
        while not self.stop_event.is_set():
            # Schedule check: sleep until active hour
            if not self.profile.is_active_hour():
                await asyncio.sleep(60)
                continue
            try:
                url, depth, referrer = await asyncio.wait_for(self.queue.get(), timeout=2.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            skip = depth > self.max_depth
            result = None if skip else await self.fetch(url, depth, referrer)
            self.queue.task_done()
            if result is not None and depth < self.max_depth:
                for child_url, child_ref in result:
                    self._enqueue(child_url, depth + 1, child_ref)

    async def run(self):
        log.info(f"[DEBUT] crawler | u={self.profile.user_id}")
        workers = [asyncio.create_task(self.crawl_worker()) for _ in range(self.concurrency)]
        await self.stop_event.wait()
        for w in workers: w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        await self.close()
        log.info(f"[FIN] crawler | u={self.profile.user_id} visited={self.stats['visited']}")

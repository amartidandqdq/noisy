# crawler.py - Orchestration crawl par utilisateur virtuel
# IN: UserProfile, shared state | OUT: none | MODIFIE: LRUSet visited, stats dict
# APPELÉ PAR: noisy.py | APPELLE: crawler_session, depth_model, referer_chain,
#             asset_fetcher, extractor, fetch_client, profiles

import asyncio
import logging
import ssl
from typing import List, Optional
from urllib.parse import urlsplit

import aiohttp

from .asset_fetcher import fetch_assets
from .crawler_session import CrawlerBase
from .depth_model import pick_session_depth
from .extractor import extract_assets, extract_links
from .fetch_client import fetch_with_retry
from .profiles import _activity_pause_seconds
from .referer_chain import pick_origin_referer

log = logging.getLogger(__name__)


class UserCrawler(CrawlerBase):

    async def fetch(self, url: str, depth: int, referrer: Optional[str], session_max: int) -> Optional[List]:
        async with self.semaphore:
            domain = urlsplit(url).hostname
            if not domain or any(b in url for b in self.url_blacklist):
                return None
            if self.domain_blocklist and self._domain_blocked(domain):
                return None
            if url in self.shared_visited:
                return None
            if self.shared_metrics and self.shared_metrics.is_paused:
                await self.shared_metrics.pause_event.wait()
            if self.shared_metrics and self.shared_metrics.domain_health(domain) < 0.2:
                return None
            self.shared_visited.add(url)
            session = await self._session_get()
            ssl_ctx = self.profile.ssl_context if self.features.get("tls_rotation", True) else None
            try:
                await self.rate_limiter.wait(domain, self.rng)
                dns_opt = self.features.get("dns_optimized", False)
                result = await fetch_with_retry(
                    session, url, self.profile.get_headers(referrer),
                    ssl_context=ssl_ctx, throttle=self._throttle,
                    lightweight=dns_opt,
                )
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
                # Fetch static assets (images, CSS, JS) if enabled (skip in dns_optimized mode)
                if self.features.get("asset_fetching", True) and not dns_opt and html:
                    assets = extract_assets(html, url, blacklist=self.url_blacklist)
                    if assets:
                        asset_bytes = await fetch_assets(
                            session, assets, self.rng,
                            self.profile.get_headers(url), ssl_context=ssl_ctx,
                        )
                        self.stats["bytes"] += asset_bytes
                del html
                if links:
                    links = self.rng.sample(links, min(len(links), self.max_links_per_page))
                if self.rng.random() < 0.05:
                    for root in self.root_urls:
                        self._enqueue(root, 0, None, self.max_depth)
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

    async def crawl_worker(self):
        while not self.stop_event.is_set():
            if not self.profile.is_active_hour():
                await asyncio.sleep(60)
                continue
            try:
                url, depth, referrer, session_max = await asyncio.wait_for(self.queue.get(), timeout=2.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            # Realistic depth for root URLs
            if depth == 0 and self.features.get("realistic_depth", True):
                session_max = pick_session_depth(self.rng, self.profile.is_mobile, self.max_depth)
            # Referer chain origin for root URLs
            if depth == 0 and referrer is None and self.features.get("referer_chains", True):
                referrer = pick_origin_referer(self.rng, url)
            skip = depth > session_max
            result = None if skip else await self.fetch(url, depth, referrer, session_max)
            self.queue.task_done()
            if result is not None and depth < session_max:
                for child_url, child_ref in result:
                    self._enqueue(child_url, depth + 1, child_ref, session_max)

    async def run(self):
        log.info(f"[DEBUT] crawler | u={self.profile.user_id}")
        workers = [asyncio.create_task(self.crawl_worker()) for _ in range(self.concurrency)]
        await self.stop_event.wait()
        for w in workers: w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        await self.close()
        log.info(f"[FIN] crawler | u={self.profile.user_id} visited={self.stats['visited']}")

# workers.py - Tâches fond : DNS bruit, stats, refresh UA
# IN: domains, crawlers, stop_event | OUT: none | MODIFIE: UAPool, profiles.ua
# APPELÉ PAR: noisy.py | APPELLE: fetchers, profiles, config, dns_resolver, tls_profiles

import asyncio
import logging
import random
import re
import socket
import ssl
import time
from typing import List, Optional, TYPE_CHECKING

import aiohttp

from . import host_in_blocklist
from .config import DEFAULT_DNS_MAX_SLEEP, DEFAULT_DNS_MIN_SLEEP, SEARCH_ENGINES, SEARCH_WORDS, UA_FALLBACK
from .fetchers import fetch_user_agents
from .profiles import _diurnal_weight
from .tls_profiles import DEFAULT_SSL_CONTEXT as SSL_CONTEXT, get_rotated_ssl_context

if TYPE_CHECKING:
    from .crawler import UserCrawler
    from .profiles import UAPool

log = logging.getLogger(__name__)


async def dns_noise_worker(
    domains: List[str],
    stop_event: asyncio.Event,
    dns_cache=None,
    min_sleep: float = DEFAULT_DNS_MIN_SLEEP,
    max_sleep: float = DEFAULT_DNS_MAX_SLEEP,
    worker_id: int = 0,
) -> None:
    """Bruit DNS avec correlation TCP+TLS+HEAD (SNI correct)."""
    log.info(f"[DEBUT] dns_noise_worker | id={worker_id} domains={len(domains)} correlated={dns_cache is not None}")
    rng = random.Random()
    loop = asyncio.get_running_loop()
    while not stop_event.is_set():
        host = rng.choice(domains)
        # Skip si TTL encore valide — pas de requete DNS = pas de bruit reseau
        if dns_cache and dns_cache.is_cached(host):
            lt = time.localtime()
            hour = lt.tm_hour + lt.tm_min / 60
            scale = 1.0 / max(0.1, _diurnal_weight(hour))
            await asyncio.sleep(rng.uniform(min_sleep / 3, max_sleep / 3) * scale)
            continue
        # DNS resolve (avec TTL cache si disponible)
        ip = None
        if dns_cache:
            ip = await dns_cache.resolve(host)
        else:
            try:
                result = await loop.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
                if result:
                    ip = result[0][4][0]
            except Exception as e:
                log.debug(f"[DNS] failed={host} {e}")
        if ip is None:
            lt = time.localtime()
            hour = lt.tm_hour + lt.tm_min / 60
            scale = 1.0 / max(0.1, _diurnal_weight(hour))
            await asyncio.sleep(rng.uniform(min_sleep, max_sleep) * scale)
            continue
        # TCP + TLS handshake + HEAD (correlation DNS→TCP→SNI)
        writer = None
        try:
            ssl_ctx = get_rotated_ssl_context(rng, include_h2=True)
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, 443, ssl=ssl_ctx, server_hostname=host),
                timeout=10,
            )
            # HEAD minimal avec Host correct
            writer.write(f"HEAD / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode())
            await writer.drain()
            await asyncio.wait_for(reader.read(4096), timeout=5)
            log.debug(f"[DNS] correlated host={host} ip={ip}")
        except Exception:
            pass
        finally:
            if writer is not None:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass
        lt = time.localtime()
        hour = lt.tm_hour + lt.tm_min / 60
        scale = 1.0 / max(0.1, _diurnal_weight(hour))
        await asyncio.sleep(rng.uniform(min_sleep, max_sleep) * scale)


async def stats_reporter(crawlers: List["UserCrawler"], stop_event: asyncio.Event) -> None:
    """Rapporte les stats toutes les 60s : visités, échecs %, req/s."""
    prev_visited = 0
    prev_time = time.monotonic()
    while not stop_event.is_set():
        await asyncio.sleep(60)
        now = time.monotonic()
        total_v = sum(c.stats["visited"] for c in crawlers)
        total_f = sum(c.stats["failed"] for c in crawlers)
        total_q = sum(c.stats["queued"] for c in crawlers)
        rps = (total_v - prev_visited) / (now - prev_time)
        fail_pct = total_f / (total_v + total_f) * 100 if (total_v + total_f) > 0 else 0.0
        per_user = " | ".join(f"u{c.profile.user_id}:{c.stats['visited']}v" for c in crawlers)
        log.info(
            f"[STATS] visited={total_v} failed={total_f} ({fail_pct:.1f}%) "
            f"queued={total_q} rps={rps:.2f} | {per_user}"
        )
        prev_visited, prev_time = total_v, now


async def refresh_user_agents_loop(
    stop_event: asyncio.Event,
    ua_refresh_seconds: int,
    crawlers: List["UserCrawler"],
    ua_pool: "UAPool",
) -> None:
    """Rafraîchit le pool UA et tourne les agents par utilisateur."""
    log.info(f"[DEBUT] refresh_user_agents_loop | interval={ua_refresh_seconds}s")
    await asyncio.sleep(ua_refresh_seconds)
    async with aiohttp.ClientSession() as session:
        while not stop_event.is_set():
            agents = await fetch_user_agents(session)
            if agents:
                await ua_pool.replace(agents)
                for crawler, ua in zip(crawlers, ua_pool.sample(len(crawlers))):
                    crawler.profile.ua = ua
            await asyncio.sleep(ua_refresh_seconds)


async def search_noise_worker(
    stop_event: asyncio.Event,
    worker_id: int = 0,
    min_sleep: float = 30,
    max_sleep: float = 120,
    domain_blocklist: set = None,
) -> None:
    """Simule des recherches web avec des mots aléatoires."""
    log.info(f"[DEBUT] search_noise_worker | id={worker_id}")
    rng = random.Random()
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession() as session:
        while not stop_event.is_set():
            # Build random query (2-4 words)
            n_words = rng.randint(2, 4)
            query = " ".join(rng.sample(SEARCH_WORDS, min(n_words, len(SEARCH_WORDS))))
            engine = rng.choice(SEARCH_ENGINES)
            url = engine.format(query=query.replace(" ", "+"))
            ua = rng.choice(UA_FALLBACK)
            headers = {
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
            try:
                async with session.get(
                    url, headers=headers, timeout=timeout,
                    ssl=SSL_CONTEXT, allow_redirects=True,
                ) as resp:
                    if resp.status < 400:
                        raw = await resp.content.read(256 * 1024)
                        text = raw.decode(resp.charset or "utf-8", errors="replace")
                        # Extract result links and visit 1-3
                        links = re.findall(r'https?://[^\s"<>]+', text)
                        links = [l for l in links if not any(
                            s in l for s in ("google.", "bing.", "duckduckgo.", "yahoo.", "microsoft.")
                        )]
                        if domain_blocklist:
                            links = [l for l in links if not host_in_blocklist(l, domain_blocklist)]
                        if links:
                            to_visit = rng.sample(links, min(rng.randint(1, 3), len(links)))
                            for link in to_visit:
                                try:
                                    async with session.get(
                                        link, headers={"User-Agent": ua, "Referer": url},
                                        timeout=timeout, ssl=SSL_CONTEXT, allow_redirects=True,
                                    ) as _:
                                        pass
                                except Exception:
                                    pass
                                await asyncio.sleep(rng.uniform(2, 8))
                    log.debug(f"[SEARCH] q='{query}' engine={engine.split('/')[2]} status={resp.status}")
            except Exception:
                pass
            lt = time.localtime()
            hour = lt.tm_hour + lt.tm_min / 60
            scale = 1.0 / max(0.1, _diurnal_weight(hour))
            await asyncio.sleep(rng.uniform(min_sleep, max_sleep) * scale)


async def http_noise_worker(
    domains: List[str],
    stop_event: asyncio.Event,
    worker_id: int = 0,
    min_sleep: float = 10,
    max_sleep: float = 60,
    domain_blocklist: set = None,
) -> None:
    """Envoie des HEAD HTTP aléatoires pour diversifier le mix de méthodes (read-only)."""
    log.info(f"[DEBUT] http_noise_worker | id={worker_id}")
    rng = random.Random()
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession() as session:
        while not stop_event.is_set():
            host = rng.choice(domains)
            if domain_blocklist and host_in_blocklist(f"https://{host}/", domain_blocklist):
                continue
            url = f"https://{host}/"
            ua = rng.choice(UA_FALLBACK)
            headers = {"User-Agent": ua}
            try:
                async with session.head(
                    url, headers=headers,
                    timeout=timeout, ssl=SSL_CONTEXT, allow_redirects=False,
                ) as resp:
                    log.debug(f"[HEAD] host={host} status={resp.status}")
            except Exception:
                pass
            lt = time.localtime()
            hour = lt.tm_hour + lt.tm_min / 60
            scale = 1.0 / max(0.1, _diurnal_weight(hour))
            await asyncio.sleep(rng.uniform(min_sleep, max_sleep) * scale)

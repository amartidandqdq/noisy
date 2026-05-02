# dns_prefetch.py - Simulation prefetch DNS navigateur (Chrome/Firefox)
# IN: domains, stop_event, dns_cache | OUT: none | MODIFIE: dns_cache
# APPELE PAR: noisy.py | APPELLE: dns_resolver, extractor, tls_profiles, config

import asyncio
import logging
import random
import re
from typing import List, Optional, Set
from urllib.parse import urlsplit

from . import host_in_blocklist
from .config import (
    PREFETCH_MAX_BODY, PREFETCH_MAX_DOMAINS,
    PREFETCH_MIN_SLEEP, PREFETCH_MAX_SLEEP,
    UA_FALLBACK,
)
from .extractor import extract_links
from .profiles import diurnal_sleep
from .tcp_tls_probe import tcp_tls_probe
from .tls_profiles import get_rotated_ssl_context
from . import efficacy

log = logging.getLogger(__name__)


async def _fetch_page_lightweight(ip: str, host: str, rng: random.Random) -> Optional[str]:
    """GET avec Connection: close, lit max 64KB pour extraction liens."""
    writer = None
    try:
        ssl_ctx = get_rotated_ssl_context(rng, include_h2=True)
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, 443, ssl=ssl_ctx, server_hostname=host),
            timeout=10,
        )
        ua = rng.choice(UA_FALLBACK)
        req = (
            f"GET / HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"User-Agent: {ua}\r\n"
            f"Accept: text/html\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )
        writer.write(req.encode())
        await writer.drain()
        data = await asyncio.wait_for(reader.read(PREFETCH_MAX_BODY), timeout=15)
        # Skip HTTP headers, find body
        text = data.decode("utf-8", errors="replace")
        sep = text.find("\r\n\r\n")
        if sep > 0:
            return text[sep + 4:]
        return text
    except Exception:
        return None
    finally:
        if writer is not None:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass


def _extract_domains(links: List[str]) -> Set[str]:
    """Extrait les domaines uniques d'une liste d'URLs."""
    domains = set()
    for url in links:
        try:
            host = urlsplit(url).hostname
            if host and "." in host and not host.replace(".", "").isdigit():
                domains.add(host)
        except Exception:
            pass
    return domains


async def dns_prefetch_worker(
    domains: List[str],
    stop_event: asyncio.Event,
    dns_cache,
    domain_blocklist: Optional[set] = None,
    worker_id: int = 0,
    min_sleep: float = PREFETCH_MIN_SLEEP,
    max_sleep: float = PREFETCH_MAX_SLEEP,
) -> None:
    """Simule le DNS prefetch navigateur : charge une page, resout tous les domaines des liens."""
    log.info(f"[DEBUT] dns_prefetch_worker | id={worker_id} sources={len(domains)}")
    rng = random.Random()

    while not stop_event.is_set():
        host = rng.choice(domains)

        # Skip si TTL encore valide
        if dns_cache.is_cached(host):
            await asyncio.sleep(rng.uniform(min_sleep / 5, max_sleep / 5))
            continue

        # 1. DNS resolve la page source
        ip = await dns_cache.resolve(host)
        efficacy.bump("dns_prefetch_resolves")
        if ip is None:
            await asyncio.sleep(rng.uniform(5, 15))
            continue

        # 2. GET lightweight — extraction liens
        html = await _fetch_page_lightweight(ip, host, rng)
        if not html:
            await asyncio.sleep(rng.uniform(5, 15))
            continue

        # 3. Extraire domaines uniques des liens
        base_url = f"https://{host}/"
        links = extract_links(html, base_url, domain_blocklist=domain_blocklist)
        link_domains = _extract_domains(links)

        # Filtrer : pas le domaine source, pas en blocklist, max N
        prefetch_domains = set()
        for d in link_domains:
            if d == host:
                continue
            if domain_blocklist and host_in_blocklist(f"https://{d}/", domain_blocklist):
                continue
            prefetch_domains.add(d)
            if len(prefetch_domains) >= PREFETCH_MAX_DOMAINS:
                break

        if prefetch_domains:
            log.debug(f"[DNS-PREFETCH] host={host} found={len(prefetch_domains)} domains to prefetch")

        # 4. Burst DNS+TCP+TLS pour chaque domaine (simule prefetch navigateur)
        for d in prefetch_domains:
            if stop_event.is_set():
                break
            # Skip si deja en cache TTL
            if dns_cache.is_cached(d):
                continue
            d_ip = await dns_cache.resolve(d)
            if d_ip:
                await tcp_tls_probe(d_ip, d, rng)
            # Delai inter-prefetch (0.05-0.3s — navigateurs sont rapides)
            await asyncio.sleep(rng.uniform(0.05, 0.3))

        # Sleep avant prochain burst
        await diurnal_sleep(rng, min_sleep, max_sleep)

    log.info(f"[FIN] dns_prefetch_worker | id={worker_id}")

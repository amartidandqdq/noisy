# traffic_mirror.py - Observation cache DNS systeme + bruit proportionnel
# IN: stop_event, crawlers | OUT: none | MODIFIE: rien
# APPELE PAR: noisy.py | APPELLE: subprocess, config, aiohttp

import asyncio
import logging
import platform
import random
import re
from typing import List, Optional, Set
from urllib.parse import urlsplit

import aiohttp

from . import host_in_blocklist
from .config import UA_FALLBACK
from .profiles import diurnal_scale
from .tls_profiles import DEFAULT_SSL_CONTEXT

log = logging.getLogger(__name__)

MIRROR_POLL_INTERVAL = 60  # seconds between DNS cache reads
MIRROR_NOISE_RATIO = 4    # noise requests per real domain observed
MIRROR_REQUEST_DELAY = (2, 10)  # min/max delay between noise requests


async def _read_dns_cache_windows() -> Set[str]:
    """Parse ipconfig /displaydns sur Windows."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ipconfig", "/displaydns",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        text = stdout.decode("utf-8", errors="replace")
        # Extract domain names from "Record Name" lines
        domains = set()
        for match in re.finditer(r"Record Name\s*[.:]+\s*(\S+)", text, re.IGNORECASE):
            domain = match.group(1).strip().rstrip(".")
            if "." in domain and not domain.startswith("_"):
                domains.add(domain)
        return domains
    except Exception as e:
        log.debug(f"[MIRROR] Windows DNS read failed: {e}")
        return set()


async def _read_dns_cache_linux() -> Set[str]:
    """Parse systemd-resolve --statistics ou journalctl sur Linux."""
    domains = set()
    # Try systemd-resolved cache dump
    try:
        proc = await asyncio.create_subprocess_exec(
            "resolvectl", "query", "--cache",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        for line in stdout.decode("utf-8", errors="replace").splitlines():
            parts = line.strip().split()
            if parts and "." in parts[0] and not parts[0].startswith("_"):
                domains.add(parts[0].rstrip("."))
    except Exception:
        pass
    # Fallback: recent syslog DNS queries
    if not domains:
        try:
            proc = await asyncio.create_subprocess_exec(
                "journalctl", "-u", "systemd-resolved", "-n", "200", "--no-pager",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            for match in re.finditer(r"query\[A+\]\s+(\S+)", stdout.decode("utf-8", errors="replace")):
                domain = match.group(1).rstrip(".")
                if "." in domain:
                    domains.add(domain)
        except Exception:
            pass
    return domains


async def _read_dns_cache() -> Set[str]:
    """Lit le cache DNS du systeme (multi-plateforme)."""
    system = platform.system()
    if system == "Windows":
        return await _read_dns_cache_windows()
    elif system == "Linux":
        return await _read_dns_cache_linux()
    else:
        log.info(f"[MIRROR] Platform {system} not supported, skipping DNS mirror")
        return set()


async def _generate_noise_for_domain(
    session: aiohttp.ClientSession,
    domain: str,
    rng: random.Random,
    domain_blocklist: Optional[set],
    n_requests: int,
) -> None:
    """Genere N requetes HEAD vers un domaine pour masquer le trafic reel."""
    if domain_blocklist and host_in_blocklist(f"https://{domain}/", domain_blocklist):
        return
    ua = rng.choice(UA_FALLBACK)
    timeout = aiohttp.ClientTimeout(total=10)
    for _ in range(n_requests):
        url = f"https://{domain}/"
        try:
            async with session.head(
                url, headers={"User-Agent": ua},
                timeout=timeout, ssl=DEFAULT_SSL_CONTEXT,
                allow_redirects=False,
            ) as resp:
                log.debug(f"[MIRROR] HEAD {domain} -> {resp.status}")
        except Exception:
            pass
        await asyncio.sleep(rng.uniform(*MIRROR_REQUEST_DELAY))


async def mirror_worker(
    stop_event: asyncio.Event,
    domain_blocklist: Optional[set] = None,
) -> None:
    """Observe le cache DNS et genere du bruit proportionnel."""
    system = platform.system()
    if system not in ("Windows", "Linux"):
        log.warning(f"[MIRROR] Platform {system} non supportee — mirror desactive")
        return

    log.info(f"[DEBUT] mirror_worker | platform={system} poll={MIRROR_POLL_INTERVAL}s ratio={MIRROR_NOISE_RATIO}")
    rng = random.Random()
    seen_domains: Set[str] = set()

    async with aiohttp.ClientSession() as session:
        while not stop_event.is_set():
            # Read current DNS cache
            current = await _read_dns_cache()
            new_domains = current - seen_domains
            seen_domains.update(current)

            if new_domains:
                log.debug(f"[MIRROR] {len(new_domains)} new domains detected")
                # Generate noise for each new domain
                for domain in new_domains:
                    if stop_event.is_set():
                        break
                    n = rng.randint(1, MIRROR_NOISE_RATIO)
                    await _generate_noise_for_domain(
                        session, domain, rng, domain_blocklist, n,
                    )

            # Sleep with diurnal scaling
            await asyncio.sleep(MIRROR_POLL_INTERVAL * diurnal_scale())

    log.info("[FIN] mirror_worker")

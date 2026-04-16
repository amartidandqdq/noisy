# dns_resolver.py - Cache DNS avec respect strict des TTL + sonde NXDOMAIN
# IN: domain:str | OUT: ip:str, cached:bool | MODIFIE: cache interne
# APPELE PAR: workers.py, dns_prefetch.py, dns_stealth.py | APPELLE: dnspython, config

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple

import dns.resolver

from .config import DNS_TTL_MAX, DNS_TTL_MIN

log = logging.getLogger(__name__)

# Cleanup interval (seconds)
_CLEANUP_INTERVAL = 300

# Dedicated DNS thread pool — burst workers fire 30-60 parallel resolves;
# default executor (32 threads) is shared with all blocking I/O. Avoid starvation.
_DNS_EXECUTOR = ThreadPoolExecutor(max_workers=64, thread_name_prefix="dns-resolver")


class DnsCache:
    """Cache DNS TTL-aware. resolve() ne fait une requete que si TTL expire."""

    def __init__(self):
        # {domain: (primary_ip, all_ips, expiry_monotonic)}
        # IP persistence : retourne toujours primary_ip pendant le TTL
        self._cache: Dict[str, Tuple[str, List[str], float]] = {}
        self._last_cleanup = time.monotonic()
        self._resolver = dns.resolver.Resolver()
        self._resolver.lifetime = 5.0  # timeout 5s par requete

    def is_cached(self, domain: str) -> bool:
        """True si domaine en cache et TTL non expire."""
        entry = self._cache.get(domain)
        if entry is None:
            return False
        return time.monotonic() < entry[2]

    async def resolve(self, domain: str) -> Optional[str]:
        """Resout A record. Retourne IP depuis cache si TTL valide, sinon requete DNS."""
        now = time.monotonic()

        # Periodic cleanup
        if now - self._last_cleanup > _CLEANUP_INTERVAL:
            self._cleanup()
            self._last_cleanup = now

        # Cache hit — TTL still valid, return persistent IP
        entry = self._cache.get(domain)
        if entry and now < entry[2]:
            return entry[0]

        # Cache miss or expired — actual DNS query
        try:
            loop = asyncio.get_running_loop()
            answer = await loop.run_in_executor(
                _DNS_EXECUTOR, self._do_resolve, domain
            )
            if answer is None:
                return None
            primary_ip, all_ips, ttl = answer
            # Clamp TTL to [DNS_TTL_MIN, DNS_TTL_MAX]
            ttl = max(DNS_TTL_MIN, min(DNS_TTL_MAX, ttl))
            self._cache[domain] = (primary_ip, all_ips, now + ttl)
            log.debug(f"[DNS-CACHE] resolved {domain} -> {primary_ip} ({len(all_ips)} IPs) ttl={ttl}s")
            return primary_ip
        except Exception as e:
            log.debug(f"[DNS-CACHE] failed {domain}: {e}")
            return None

    def _do_resolve(self, domain: str) -> Optional[Tuple[str, List[str], int]]:
        """Synchrone — execute dans un thread via run_in_executor.
        Retourne (primary_ip, all_ips, ttl). IP persistence : primary_ip fixe pendant le TTL."""
        try:
            answer = self._resolver.resolve(domain, "A")
            all_ips = [str(rr) for rr in answer]
            primary_ip = all_ips[0]  # Toujours le meme pendant le TTL
            ttl = answer.rrset.ttl
            return primary_ip, all_ips, ttl
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer,
                dns.resolver.NoNameservers, dns.exception.Timeout):
            return None

    def _cleanup(self):
        """Purge entrees expirees."""
        now = time.monotonic()
        expired = [d for d, (_, _, exp) in self._cache.items() if now >= exp]
        for d in expired:
            del self._cache[d]
        if expired:
            log.debug(f"[DNS-CACHE] cleanup: {len(expired)} expired, {len(self._cache)} remaining")

    async def probe_nxdomain(self, domain: str) -> bool:
        """Resout un domaine qui DOIT retourner NXDOMAIN. True = NXDOMAIN recu (normal).
        Pas de cache — le but est de generer la requete DNS."""
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(_DNS_EXECUTOR, self._do_nxdomain_probe, domain)
        except Exception:
            return False

    def _do_nxdomain_probe(self, domain: str) -> bool:
        """Synchrone — True si NXDOMAIN, False si reponse (resolver menteur/portail captif)."""
        try:
            self._resolver.resolve(domain, "A")
            return False  # Got answer = resolver is lying
        except dns.resolver.NXDOMAIN:
            return True   # Expected — domain doesn't exist
        except Exception:
            return False

    @property
    def size(self) -> int:
        return len(self._cache)

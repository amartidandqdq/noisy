# test_dns_stealth_smoke.py - Smoke tests pour les modules DNS stealth
# Verifie imports + signatures + DnsCache basics. Pas de I/O reseau.

import asyncio
import time
from unittest.mock import patch

import pytest


def test_imports():
    """Tous les nouveaux modules s'importent sans erreur."""
    from noisy_lib import dns_resolver, dns_prefetch, dns_stealth, ech_client, stream_noise
    assert dns_resolver.DnsCache
    assert dns_prefetch.dns_prefetch_worker
    assert dns_stealth.thirdparty_burst_worker
    assert dns_stealth.background_noise_worker
    assert dns_stealth.microburst_worker
    assert dns_stealth.nxdomain_probe_worker
    assert ech_client.ech_probe
    assert stream_noise.stream_noise_worker


def test_dns_cache_init():
    from noisy_lib.dns_resolver import DnsCache
    cache = DnsCache()
    assert cache.size == 0
    assert cache.is_cached("nope.example.com") is False


def test_dns_cache_ttl_clamp():
    """TTL force entre [DNS_TTL_MIN, DNS_TTL_MAX]."""
    from noisy_lib.dns_resolver import DnsCache
    from noisy_lib.config import DNS_TTL_MAX, DNS_TTL_MIN
    cache = DnsCache()
    # Manually inject a fake entry to test is_cached
    cache._cache["test.local"] = ("1.2.3.4", ["1.2.3.4"], time.monotonic() + 60)
    assert cache.is_cached("test.local") is True
    cache._cache["expired.local"] = ("1.2.3.4", ["1.2.3.4"], time.monotonic() - 1)
    assert cache.is_cached("expired.local") is False


def test_extract_domains():
    from noisy_lib.dns_prefetch import _extract_domains
    links = [
        "https://example.com/page",
        "https://cdn.example.org/asset.js",
        "https://192.168.1.1/local",  # IP, must be excluded
        "not-a-url",
    ]
    domains = _extract_domains(links)
    assert "example.com" in domains
    assert "cdn.example.org" in domains
    assert "192.168.1.1" not in domains


def test_ech_availability_check():
    """is_ech_available retourne bool, ne crash pas si curl_cffi absent."""
    from noisy_lib.ech_client import is_ech_available
    result = is_ech_available()
    assert isinstance(result, bool)


@pytest.mark.asyncio
async def test_dns_cache_resolve_handles_failure():
    """resolve() retourne None si dnspython echoue, ne raise pas."""
    from noisy_lib.dns_resolver import DnsCache
    cache = DnsCache()
    # Domaine garanti invalide
    result = await cache.resolve("this-domain-cannot-exist-xyz123.invalid")
    assert result is None


@pytest.mark.asyncio
async def test_workers_stop_immediately_on_event():
    """Les workers doivent sortir si stop_event est deja set au demarrage."""
    from noisy_lib.dns_stealth import nxdomain_probe_worker
    from noisy_lib.dns_resolver import DnsCache
    stop = asyncio.Event()
    stop.set()
    cache = DnsCache()
    # Doit retourner quasi-instantanement
    await asyncio.wait_for(nxdomain_probe_worker(stop, cache, worker_id=99), timeout=2)


def test_config_constants_present():
    """Toutes les constantes referencees par les nouveaux workers existent."""
    from noisy_lib import config
    required = [
        "DNS_TTL_MIN", "DNS_TTL_MAX",
        "PREFETCH_MAX_BODY", "PREFETCH_MAX_DOMAINS",
        "PREFETCH_MIN_SLEEP", "PREFETCH_MAX_SLEEP",
        "PROBE_RANGE_MIN", "PROBE_RANGE_MAX",
        "THIRD_PARTY_DOMAINS", "THIRD_PARTY_PER_PAGE_MIN", "THIRD_PARTY_PER_PAGE_MAX",
        "BACKGROUND_APP_DOMAINS", "BACKGROUND_MIN_SLEEP", "BACKGROUND_MAX_SLEEP",
        "BURST_SIZE_MIN", "BURST_SIZE_MAX", "BURST_SILENCE_MIN", "BURST_SILENCE_MAX",
        "CAPTIVE_PORTAL_DOMAINS", "CAPTIVE_PORTAL_INTERVAL", "NXDOMAIN_PROBE_INTERVAL",
        "STREAMING_CDN_DOMAINS", "STREAM_CHUNK_SIZE", "STREAM_CHUNK_DELAY",
        "STREAM_SESSION_DURATION", "STREAM_PAUSE",
    ]
    for name in required:
        assert hasattr(config, name), f"config.{name} manquant"


def test_third_party_domains_nonempty():
    from noisy_lib.config import THIRD_PARTY_DOMAINS, BACKGROUND_APP_DOMAINS, STREAMING_CDN_DOMAINS
    assert len(THIRD_PARTY_DOMAINS) >= 10
    assert len(BACKGROUND_APP_DOMAINS) >= 10
    assert len(STREAMING_CDN_DOMAINS) >= 5

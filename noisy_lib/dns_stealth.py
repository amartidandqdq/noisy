# dns_stealth.py - Workers DNS stealth avances (tiers, background, burst, NXDOMAIN)
# IN: domains, stop_event, dns_cache | OUT: none | MODIFIE: dns_cache
# APPELE PAR: noisy.py | APPELLE: dns_resolver, tcp_tls_probe, profiles, config

import asyncio
import logging
import random
import string
import time
from typing import List

from .config import (
    BACKGROUND_APP_DOMAINS, BACKGROUND_MAX_SLEEP, BACKGROUND_MIN_SLEEP,
    BURST_SILENCE_MAX, BURST_SILENCE_MIN,
    BURST_SIZE_MAX, BURST_SIZE_MIN,
    CAPTIVE_PORTAL_DOMAINS, CAPTIVE_PORTAL_INTERVAL,
    NXDOMAIN_PROBE_INTERVAL,
    THIRD_PARTY_DOMAINS, THIRD_PARTY_PER_PAGE_MAX, THIRD_PARTY_PER_PAGE_MIN,
)
from .tcp_tls_probe import tcp_tls_probe
from .profiles import diurnal_sleep

log = logging.getLogger(__name__)


# ---- Worker 1 : Third-Party Burst (Effet Iceberg) ----

async def thirdparty_burst_worker(
    domains: List[str],
    stop_event: asyncio.Event,
    dns_cache,
    worker_id: int = 0,
) -> None:
    """Simule l'effet iceberg : resout N domaines tiers en parallele avec le domaine principal."""
    log.info(f"[DEBUT] thirdparty_burst | id={worker_id} third_party_pool={len(THIRD_PARTY_DOMAINS)}")
    rng = random.Random()

    while not stop_event.is_set():
        # 1. Domaine principal (CrUX)
        host = rng.choice(domains)
        main_ip = await dns_cache.resolve(host)

        # 2. Selectionner 8-25 domaines tiers
        n_third = rng.randint(THIRD_PARTY_PER_PAGE_MIN, THIRD_PARTY_PER_PAGE_MAX)
        third_party = rng.sample(THIRD_PARTY_DOMAINS, min(n_third, len(THIRD_PARTY_DOMAINS)))

        # 3. Resoudre tous en parallele (simule chargement page)
        resolve_tasks = [dns_cache.resolve(d) for d in third_party]
        results = await asyncio.gather(*resolve_tasks, return_exceptions=True)

        # 4. TCP+TLS+HEAD pour chaque IP obtenue (parallele)
        head_tasks = []
        for domain, result in zip(third_party, results):
            if isinstance(result, str) and result:
                head_tasks.append(tcp_tls_probe(result, domain, rng))
        if main_ip:
            head_tasks.append(tcp_tls_probe(main_ip, host, rng))
        if head_tasks:
            await asyncio.gather(*head_tasks, return_exceptions=True)
            log.debug(f"[3RD-PARTY] host={host} burst={len(head_tasks)} connections")

        # 5. Sleep 15-60s x diurnal
        await diurnal_sleep(rng, 15, 60)

    log.info(f"[FIN] thirdparty_burst | id={worker_id}")


# ---- Worker 2 : Background App Noise ----

async def background_noise_worker(
    stop_event: asyncio.Event,
    dns_cache,
    worker_id: int = 0,
) -> None:
    """Simule le bavardage DNS d'apps en arriere-plan (NTP, Spotify, WhatsApp, Steam...)."""
    log.info(f"[DEBUT] background_noise | id={worker_id} app_domains={len(BACKGROUND_APP_DOMAINS)}")
    rng = random.Random()

    while not stop_event.is_set():
        domain = rng.choice(BACKGROUND_APP_DOMAINS)

        # Respecter TTL — apps ne re-resolvent pas avant expiry
        if dns_cache.is_cached(domain):
            await asyncio.sleep(rng.uniform(BACKGROUND_MIN_SLEEP / 3, BACKGROUND_MAX_SLEEP / 3))
            continue

        ip = await dns_cache.resolve(domain)
        if ip:
            await tcp_tls_probe(ip, domain, rng)
            log.debug(f"[BG-NOISE] domain={domain}")

        # Sleep 30-180s x diurnal (apps bavardent lentement)
        await diurnal_sleep(rng, BACKGROUND_MIN_SLEEP, BACKGROUND_MAX_SLEEP)

    log.info(f"[FIN] background_noise | id={worker_id}")


# ---- Worker 3 : Micro-Burst ----

async def microburst_worker(
    domains: List[str],
    stop_event: asyncio.Event,
    dns_cache,
    worker_id: int = 0,
) -> None:
    """Rafale massive de 30-60 requetes DNS puis silence total (pattern humain)."""
    log.info(f"[DEBUT] microburst | id={worker_id}")
    rng = random.Random()

    while not stop_event.is_set():
        # 1. Construire le burst : mix CrUX + tiers + background
        burst_size = rng.randint(BURST_SIZE_MIN, BURST_SIZE_MAX)
        burst_domains = []
        # ~60% CrUX, ~30% tiers, ~10% background
        n_crux = int(burst_size * 0.6)
        n_third = int(burst_size * 0.3)
        n_bg = burst_size - n_crux - n_third
        burst_domains += rng.sample(domains, min(n_crux, len(domains)))
        burst_domains += rng.sample(THIRD_PARTY_DOMAINS, min(n_third, len(THIRD_PARTY_DOMAINS)))
        burst_domains += rng.sample(BACKGROUND_APP_DOMAINS, min(n_bg, len(BACKGROUND_APP_DOMAINS)))
        rng.shuffle(burst_domains)

        # 2. Resoudre tous en parallele
        resolve_tasks = [dns_cache.resolve(d) for d in burst_domains]
        results = await asyncio.gather(*resolve_tasks, return_exceptions=True)

        # 3. TCP+TLS+HEAD en parallele pour ceux resolus
        head_tasks = []
        for domain, result in zip(burst_domains, results):
            if isinstance(result, str) and result:
                head_tasks.append(tcp_tls_probe(result, domain, rng))
        if head_tasks:
            await asyncio.gather(*head_tasks, return_exceptions=True)
        log.debug(f"[BURST] size={len(burst_domains)} connected={len(head_tasks)}")

        # 4. SILENCE total — simule lecture/video
        await diurnal_sleep(rng, BURST_SILENCE_MIN, BURST_SILENCE_MAX)

    log.info(f"[FIN] microburst | id={worker_id}")


# ---- Worker 4 : NXDOMAIN Probes + Captive Portal ----

async def nxdomain_probe_worker(
    stop_event: asyncio.Event,
    dns_cache,
    worker_id: int = 0,
) -> None:
    """Sondes Chrome intranet redirect detector + captive portal checks."""
    log.info(f"[DEBUT] nxdomain_probe | id={worker_id}")
    rng = random.Random()
    next_nxdomain = time.monotonic() + rng.uniform(10, 30)  # premiere sonde rapide
    next_captive = time.monotonic() + rng.uniform(5, 15)

    while not stop_event.is_set():
        now = time.monotonic()

        # Chrome Intranet Redirect Detector — 3 noms aleatoires
        if now >= next_nxdomain:
            for _ in range(3):
                length = rng.randint(10, 15)
                fake_domain = "".join(rng.choices(string.ascii_lowercase, k=length))
                is_nx = await dns_cache.probe_nxdomain(fake_domain)
                log.debug(f"[NXDOMAIN] probe={fake_domain} nxdomain={is_nx}")
            next_nxdomain = now + rng.uniform(*NXDOMAIN_PROBE_INTERVAL)

        # Captive Portal Check
        if now >= next_captive:
            portal = rng.choice(CAPTIVE_PORTAL_DOMAINS)
            ip = await dns_cache.resolve(portal)
            if ip:
                await tcp_tls_probe(ip, portal, rng)
                log.debug(f"[CAPTIVE] check={portal}")
            next_captive = now + rng.uniform(*CAPTIVE_PORTAL_INTERVAL)

        # Sleep court — pas de diurnal (ces sondes tournent 24/7)
        await asyncio.sleep(rng.uniform(30, 60))

    log.info(f"[FIN] nxdomain_probe | id={worker_id}")

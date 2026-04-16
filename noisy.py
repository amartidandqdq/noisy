# noisy.py - Point d'entrée et orchestration principale
# IN: CLI args | OUT: none | MODIFIE: arrête le processus via stop_event
# APPELÉ PAR: __main__ | APPELLE: tous modules noisy_lib

import asyncio
import logging
import random
import sys
from typing import List, Optional
from urllib.parse import urlsplit

import aiohttp

from noisy_lib import extract_tld, host_in_blocklist
from noisy_lib.config import (
    DEFAULT_URL_BLACKLIST, DEFAULT_VISITED_MAX, GEO_PROFILES,
    GENERIC_TLDS, MOBILE_UA_POOL, REGION_PRESETS, SECONDS_PER_DAY, UA_FALLBACK,
)
from noisy_lib.config_loader import build_parser, load_config_file, validate_args
from noisy_lib.crawler import UserCrawler
from noisy_lib.fetchers import fetch_crux_top_sites, fetch_nsfw_blocklist, fetch_phishing_blocklist, fetch_user_agents, load_browser_history
from noisy_lib.metrics import SharedMetrics
from noisy_lib.profiles import UAPool, UserProfile
from noisy_lib.rate_limiter import DomainRateLimiter
from noisy_lib.structures import LRUSet
from noisy_lib.workers import dns_noise_worker, http_noise_worker, refresh_user_agents_loop, search_noise_worker, stats_reporter
from noisy_lib.ws_noise import ws_noise_worker
from noisy_lib.traffic_mirror import mirror_worker
from noisy_lib.dns_resolver import DnsCache
from noisy_lib.dns_prefetch import dns_prefetch_worker
from noisy_lib.dns_stealth import (
    thirdparty_burst_worker, background_noise_worker,
    microburst_worker, nxdomain_probe_worker,
)
from noisy_lib.stream_noise import stream_noise_worker

log = logging.getLogger(__name__)

# Backward compat aliases
_host_in_blocklist = host_in_blocklist
_extract_tld = extract_tld


def _build_tld_filter(args) -> set:
    allowed = set()
    for r in (args.regions or []):
        allowed |= REGION_PRESETS.get(r, set())
    if args.tld:
        allowed |= {t.strip().lower() for t in args.tld.split(",")}
    return allowed


def setup_logging(level_str: str, logfile: Optional[str] = None):
    level = getattr(logging, level_str.upper(), logging.INFO)
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    fmt = logging.Formatter("%(levelname)s - %(message)s")
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)
    if logfile:
        fh = logging.FileHandler(logfile)
        fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        root.addHandler(fh)
    logging.getLogger("aiohttp").setLevel(logging.DEBUG if level == logging.DEBUG else logging.ERROR)


async def _check_internet():
    """Vérifie la connexion internet."""
    try:
        async with aiohttp.ClientSession() as hc:
            async with hc.get("https://www.google.com", timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status < 400:
                    log.info("[HEALTH] Connexion internet OK")
                else:
                    log.warning(f"[HEALTH] HTTP {r.status} — connexion instable")
    except Exception as e:
        log.error(f"[HEALTH] Pas de connexion internet: {e}")


async def _fetch_initial_data(args, ua_pool):
    """Charge CRUX, UAs, blocklists en parallèle. Retourne (top_sites, blocklist_set)."""
    async with aiohttp.ClientSession() as session:
        top_sites, initial_uas, nsfw_domains, phishing_domains = await asyncio.gather(
            fetch_crux_top_sites(session, count=args.crux_count),
            fetch_user_agents(session),
            fetch_nsfw_blocklist(session),
            fetch_phishing_blocklist(session),
        )
        if initial_uas:
            await ua_pool.replace(initial_uas)

    blocklist_set = set()
    for name, domains in [("NSFW", nsfw_domains), ("Phishing/malware", phishing_domains)]:
        if domains:
            blocklist_set.update(domains)
            log.info(f"[BLOCKLIST] {name}: {len(domains)} domaines")
    if blocklist_set:
        before = len(top_sites)
        top_sites = [s for s in top_sites if not host_in_blocklist(s, blocklist_set)]
        log.info(f"[BLOCKLIST] Total: {len(blocklist_set)} domaines, {before - len(top_sites)} sites CRUX bloqués")
    return top_sites, blocklist_set


def _build_crawlers(args, top_sites, history_urls, schedule, geo_list,
                    ua_pool, shared_visited, rate_limiter, shared_metrics,
                    stop_event, blocklist_set, features: dict = None) -> List[UserCrawler]:
    """Construit les UserCrawler avec profils desktop/mobile."""
    _rng = random.Random()
    per_user_queue = max(10, args.max_queue_size // args.num_users)
    n_mobile = int(args.num_users * args.mobile_ratio)
    n_desktop = args.num_users - n_mobile
    desktop_uas = ua_pool.sample(n_desktop, rng=_rng)
    mobile_uas = [_rng.choice(MOBILE_UA_POOL) for _ in range(n_mobile)]

    crawlers: List[UserCrawler] = []
    for i in range(args.num_users):
        is_mobile = i >= n_desktop
        ua = mobile_uas[i - n_desktop] if is_mobile else desktop_uas[i]
        geo = _rng.choice(geo_list) if geo_list else None
        profile = UserProfile(
            user_id=i, ua=ua, rng=random.Random(_rng.random()),
            geo=geo, is_mobile=is_mobile, schedule=schedule,
        )
        sites = (history_urls + list(top_sites)) if history_urls else list(top_sites)
        profile.rng.shuffle(sites)
        crawlers.append(UserCrawler(
            profile=profile, shared_root_urls=sites[:500],
            shared_visited=shared_visited, rate_limiter=rate_limiter,
            max_depth=min(3, args.max_depth) if is_mobile else args.max_depth,
            concurrency=args.threads, min_sleep=args.min_sleep, max_sleep=args.max_sleep,
            max_queue_size=per_user_queue, max_links_per_page=args.max_links_per_page,
            url_blacklist=DEFAULT_URL_BLACKLIST, stop_event=stop_event,
            total_connections=args.total_connections,
            connections_per_host=args.connections_per_host,
            keepalive_timeout=args.keepalive_timeout,
            shared_metrics=shared_metrics, domain_blocklist=blocklist_set,
            cookie_persist=getattr(args, "cookie_persist", False),
            features=features or {},
        ))
    log.info(f"[USERS] {n_desktop} desktop + {n_mobile} mobile | geo={geo_list or 'auto'} | schedule={schedule or 'always'}")
    return crawlers


def _parse_schedule(raw: Optional[str]):
    if not raw:
        return None
    parts = raw.split("-")
    schedule = (int(parts[0]), int(parts[1]))
    log.info(f"[SCHEDULE] Actif {schedule[0]}h–{schedule[1]}h")
    return schedule


def _resolve_geo(args) -> list:
    if args.geo:
        return [args.geo]
    if args.regions:
        available = [g for g in GEO_PROFILES if any(g.startswith(r) for r in args.regions)]
        return available if available else []
    return []


async def main_async(args):
    setup_logging(args.log, args.logfile)

    errors = validate_args(args)
    if errors:
        for e in errors:
            log.error(f"[CONFIG] {e}")
        sys.exit(1)

    if args.dry_run:
        pq = max(10, args.max_queue_size // args.num_users)
        tld_filter = _build_tld_filter(args)
        tld_info = f" tld_filter={sorted(tld_filter)}" if tld_filter else ""
        log.info(f"[DRY-RUN] threads={args.threads} users={args.num_users} depth={args.max_depth} | sleep=[{args.min_sleep},{args.max_sleep}]s delay={args.domain_delay}s")
        log.info(f"[DRY-RUN] crux={args.crux_count} dns_workers={args.dns_workers} timeout={args.timeout} | per_user_queue={pq}{tld_info}")
        return

    ua_pool = UAPool(UA_FALLBACK)
    await _check_internet()
    top_sites, blocklist_set = await _fetch_initial_data(args, ua_pool)

    # TLD filter
    all_top_sites = list(top_sites)
    allowed_tlds = _build_tld_filter(args)
    if allowed_tlds:
        before = len(top_sites)
        top_sites = [s for s in top_sites if extract_tld(s) in GENERIC_TLDS or extract_tld(s) in allowed_tlds]
        log.info(f"[TLD] Filtre appliqué: {len(top_sites)}/{before} sites restants")

    if not top_sites:
        log.error("[FATAL] Aucun site CRUX chargé — arrêt.")
        return

    history_urls = load_browser_history(args.history_file) if args.history_file else []
    schedule = _parse_schedule(args.schedule)
    geo_list = _resolve_geo(args)

    stop_event = asyncio.Event()
    shared_visited = LRUSet(maxsize=DEFAULT_VISITED_MAX)
    rate_limiter = DomainRateLimiter(domain_delay=args.domain_delay)
    shared_metrics = SharedMetrics()

    # Default feature flags
    features = {
        "tls_rotation": True, "realistic_depth": True, "referer_chains": True,
        "asset_fetching": True, "cookie_persist": getattr(args, "cookie_persist", False),
        "bandwidth_throttle": False, "ws_noise": getattr(args, "ws_workers", 0) > 0,
        "traffic_mirror": getattr(args, "mirror", False),
        "dns_optimized": getattr(args, "dns_optimized", False),
        "dns_prefetch": getattr(args, "prefetch_workers", 0) > 0,
        "thirdparty_burst": getattr(args, "thirdparty_burst", False),
        "background_noise": getattr(args, "background_noise", False),
        "nxdomain_probes": getattr(args, "nxdomain_probes", False),
        "ech": getattr(args, "ech", False),
        "stream_noise": getattr(args, "stream_noise", False),
    }

    # Shared DNS TTL cache
    dns_cache = DnsCache()

    crawlers = _build_crawlers(
        args, top_sites, history_urls, schedule, geo_list,
        ua_pool, shared_visited, rate_limiter, shared_metrics,
        stop_event, blocklist_set, features=features,
    )

    dns_hosts = [h for h in (urlsplit(s).hostname for s in top_sites) if h]
    ua_refresh_s = int(args.ua_refresh_days * SECONDS_PER_DAY)
    per_user_queue = max(10, args.max_queue_size // args.num_users)

    tasks = (
        [asyncio.create_task(c.run()) for c in crawlers]
        + [asyncio.create_task(dns_noise_worker(dns_hosts, stop_event, dns_cache=dns_cache, worker_id=i))
           for i in range(args.dns_workers)]
        + [asyncio.create_task(stats_reporter(crawlers, stop_event)),
           asyncio.create_task(refresh_user_agents_loop(stop_event, ua_refresh_s, crawlers, ua_pool))]
        + [asyncio.create_task(http_noise_worker(dns_hosts, stop_event, worker_id=i, domain_blocklist=blocklist_set))
           for i in range(args.post_noise_workers)]
        + [asyncio.create_task(search_noise_worker(stop_event, worker_id=i, domain_blocklist=blocklist_set))
           for i in range(args.search_workers)]
        + [asyncio.create_task(ws_noise_worker(stop_event, worker_id=i))
           for i in range(getattr(args, "ws_workers", 0))]
        + [asyncio.create_task(dns_prefetch_worker(dns_hosts, stop_event, dns_cache, domain_blocklist=blocklist_set, worker_id=i))
           for i in range(getattr(args, "prefetch_workers", 0))]
    )

    if getattr(args, "mirror", False):
        tasks.append(asyncio.create_task(mirror_worker(stop_event, domain_blocklist=blocklist_set)))

    if getattr(args, "thirdparty_burst", False):
        tasks.append(asyncio.create_task(thirdparty_burst_worker(dns_hosts, stop_event, dns_cache)))
        # Micro-burst activé automatiquement avec thirdparty-burst
        tasks.append(asyncio.create_task(microburst_worker(dns_hosts, stop_event, dns_cache)))
    if getattr(args, "background_noise", False):
        tasks.append(asyncio.create_task(background_noise_worker(stop_event, dns_cache)))
    if getattr(args, "nxdomain_probes", False):
        tasks.append(asyncio.create_task(nxdomain_probe_worker(stop_event, dns_cache)))
    if getattr(args, "stream_noise", False):
        tasks.append(asyncio.create_task(stream_noise_worker(stop_event, dns_cache)))

    if args.dashboard:
        from noisy_lib.dashboard import MetricsCollector, start_dashboard
        collector = MetricsCollector(
            crawlers, shared_visited, rate_limiter, ua_pool,
            shared_metrics, webhook_url=args.webhook_url,
            tld_filter=allowed_tlds or None, regions=args.regions,
            all_top_sites=all_top_sites,
        )
        collector._search_workers = args.search_workers
        collector.set_crawler_params(stop_event, top_sites, {
            "max_depth": args.max_depth, "concurrency": args.threads,
            "min_sleep": args.min_sleep, "max_sleep": args.max_sleep,
            "max_queue_size": per_user_queue, "max_links_per_page": args.max_links_per_page,
            "total_connections": args.total_connections,
            "connections_per_host": args.connections_per_host,
            "keepalive_timeout": args.keepalive_timeout,
            "domain_blocklist": blocklist_set,
            "cookie_persist": getattr(args, "cookie_persist", False),
            "features": features,
        })
        collector.restore_saved_settings()
        tasks.append(asyncio.create_task(start_dashboard(collector, args.dashboard_port, args.dashboard_host)))

    if args.timeout:
        async def _stopper():
            await asyncio.sleep(args.timeout)
            stop_event.set()
        tasks.append(asyncio.create_task(_stopper()))

    await stop_event.wait()
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await asyncio.gather(*[asyncio.create_task(c.close()) for c in crawlers], return_exceptions=True)
    log.info("[FIN] main_async | arrêt propre")


def main():
    pre = __import__("argparse").ArgumentParser(add_help=False)
    pre.add_argument("--config")
    pre_args, _ = pre.parse_known_args()

    parser = build_parser()
    if pre_args.config:
        overrides = load_config_file(pre_args.config)
        if overrides:
            parser.set_defaults(**overrides)

    args = parser.parse_args()

    if args.validate_config:
        setup_logging(args.log)
        errors = validate_args(args)
        if errors:
            for e in errors:
                logging.error(f"[CONFIG] {e}")
            sys.exit(1)
        logging.info("[CONFIG] valide")
        sys.exit(0)

    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        logging.info("[STOP] interruption clavier")


if __name__ == "__main__":
    main()

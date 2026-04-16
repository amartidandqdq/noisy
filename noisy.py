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

from noisy_lib import host_in_blocklist
from noisy_lib.config import DEFAULT_URL_BLACKLIST, DEFAULT_VISITED_MAX, GENERIC_TLDS, REGION_PRESETS, SECONDS_PER_DAY
from noisy_lib.config_loader import build_parser, load_config_file, validate_args
from noisy_lib.crawler import SharedMetrics, UserCrawler
from noisy_lib.fetchers import fetch_crux_top_sites, fetch_nsfw_blocklist, fetch_phishing_blocklist, fetch_user_agents, load_browser_history
from noisy_lib.profiles import GEO_PROFILES, MOBILE_UA_POOL, UAPool, UserProfile, _UA_FALLBACK
from noisy_lib.rate_limiter import DomainRateLimiter
from noisy_lib.structures import LRUSet
from noisy_lib.workers import dns_noise_worker, http_noise_worker, refresh_user_agents_loop, search_noise_worker, stats_reporter

log = logging.getLogger(__name__)


_host_in_blocklist = host_in_blocklist  # backward compat alias


def _extract_tld(url: str) -> str:
    host = urlsplit(url).hostname or ""
    return host.rsplit(".", 1)[-1] if "." in host else ""


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
        extras = []
        if args.schedule: extras.append(f"schedule={args.schedule}")
        if args.geo: extras.append(f"geo={args.geo}")
        extras.append(f"mobile={args.mobile_ratio:.0%}")
        if args.search_workers: extras.append(f"search_workers={args.search_workers}")
        if args.history_file: extras.append(f"history={args.history_file}")
        extra_str = " | " + " ".join(extras) if extras else ""
        log.info(f"[DRY-RUN] threads={args.threads} users={args.num_users} depth={args.max_depth} | sleep=[{args.min_sleep},{args.max_sleep}]s delay={args.domain_delay}s")
        log.info(f"[DRY-RUN] crux={args.crux_count} dns_workers={args.dns_workers} timeout={args.timeout} | per_user_queue={pq} max_links={args.max_links_per_page}{tld_info}{extra_str}")
        return

    # ---- Health check connexion ----
    ua_pool = UAPool(_UA_FALLBACK)
    try:
        async with aiohttp.ClientSession() as hc:
            async with hc.get("https://www.google.com", timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status < 400:
                    log.info("[HEALTH] Connexion internet OK")
                else:
                    log.warning(f"[HEALTH] HTTP {r.status} — connexion instable")
    except Exception as e:
        log.error(f"[HEALTH] Pas de connexion internet: {e}")
        log.error("[HEALTH] Vérifier réseau/VPN/proxy avant de continuer")

    async with aiohttp.ClientSession() as session:
        top_sites, initial_uas, nsfw_domains, phishing_domains = await asyncio.gather(
            fetch_crux_top_sites(session, count=args.crux_count),
            fetch_user_agents(session),
            fetch_nsfw_blocklist(session),
            fetch_phishing_blocklist(session),
        )
        if initial_uas:
            await ua_pool.replace(initial_uas)

    # Blocklists OISD (set rapide pour lookup O(1))
    blocklist_set = set()
    if nsfw_domains:
        blocklist_set.update(nsfw_domains)
        log.info(f"[BLOCKLIST] NSFW: {len(nsfw_domains)} domaines")
    if phishing_domains:
        blocklist_set.update(phishing_domains)
        log.info(f"[BLOCKLIST] Phishing/malware: {len(phishing_domains)} domaines")
    if blocklist_set:
        before = len(top_sites)
        top_sites = [s for s in top_sites if not _host_in_blocklist(s, blocklist_set)]
        removed = before - len(top_sites)
        log.info(f"[BLOCKLIST] Total: {len(blocklist_set)} domaines, {removed} sites CRUX bloqués")

    # ---- Filtre TLD/région ----
    all_top_sites = list(top_sites)  # copie non filtrée pour dashboard live
    allowed_tlds = _build_tld_filter(args)
    if allowed_tlds:
        before = len(top_sites)
        top_sites = [s for s in top_sites if _extract_tld(s) in GENERIC_TLDS or _extract_tld(s) in allowed_tlds]
        log.info(f"[TLD] Filtre appliqué: {len(top_sites)}/{before} sites restants (ccTLD: {sorted(allowed_tlds)})")

    if not top_sites:
        log.error("[FATAL] Aucun site CRUX chargé — arrêt.")
        return

    # ---- History replay ----
    history_urls = []
    if args.history_file:
        history_urls = load_browser_history(args.history_file)
        if history_urls:
            log.info(f"[HISTORY] {len(history_urls)} URLs chargées depuis {args.history_file}")

    # ---- Schedule ----
    schedule = None
    if args.schedule:
        parts = args.schedule.split("-")
        schedule = (int(parts[0]), int(parts[1]))
        log.info(f"[SCHEDULE] Actif {schedule[0]}h–{schedule[1]}h")

    # ---- Geo profiles ----
    geo_list = []
    if args.geo:
        geo_list = [args.geo]
    elif args.regions:
        # Auto-assign geo from region (pick random sub-geos)
        available = [g for g in GEO_PROFILES if any(g.startswith(r) for r in args.regions)]
        geo_list = available if available else []

    stop_event = asyncio.Event()
    shared_visited = LRUSet(maxsize=DEFAULT_VISITED_MAX)
    rate_limiter = DomainRateLimiter(domain_delay=args.domain_delay)
    shared_metrics = SharedMetrics()

    _rng = random.Random()
    per_user_queue = max(10, args.max_queue_size // args.num_users)

    # ---- Mobile ratio ----
    n_mobile = int(args.num_users * args.mobile_ratio)
    n_desktop = args.num_users - n_mobile

    # Build UA lists
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
        sites = list(top_sites)
        if history_urls:
            sites = history_urls + sites  # history URLs prioritaires
        profile.rng.shuffle(sites)
        depth = min(3, args.max_depth) if is_mobile else args.max_depth
        crawlers.append(UserCrawler(
            profile=profile, shared_root_urls=sites[:500],
            shared_visited=shared_visited, rate_limiter=rate_limiter,
            max_depth=depth, concurrency=args.threads,
            min_sleep=args.min_sleep, max_sleep=args.max_sleep,
            max_queue_size=per_user_queue, max_links_per_page=args.max_links_per_page,
            url_blacklist=DEFAULT_URL_BLACKLIST, stop_event=stop_event,
            total_connections=args.total_connections,
            connections_per_host=args.connections_per_host,
            keepalive_timeout=args.keepalive_timeout,
            shared_metrics=shared_metrics,
            domain_blocklist=blocklist_set,
        ))
    log.info(f"[USERS] {n_desktop} desktop + {n_mobile} mobile | geo={geo_list or 'auto'} | schedule={schedule or 'always'}")

    dns_hosts = [h for h in (urlsplit(s).hostname for s in top_sites) if h]
    ua_refresh_s = int(args.ua_refresh_days * SECONDS_PER_DAY)

    tasks = (
        [asyncio.create_task(c.run()) for c in crawlers]
        + [asyncio.create_task(dns_noise_worker(dns_hosts, stop_event, worker_id=i)) for i in range(args.dns_workers)]
        + [asyncio.create_task(stats_reporter(crawlers, stop_event)),
           asyncio.create_task(refresh_user_agents_loop(stop_event, ua_refresh_s, crawlers, ua_pool))]
        + [asyncio.create_task(http_noise_worker(dns_hosts, stop_event, worker_id=i, domain_blocklist=blocklist_set))
           for i in range(args.post_noise_workers)]
        + [asyncio.create_task(search_noise_worker(stop_event, worker_id=i, domain_blocklist=blocklist_set))
           for i in range(args.search_workers)]
    )

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

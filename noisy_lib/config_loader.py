# config_loader.py - Parsing CLI, validation, chargement config fichier
# IN: sys.argv, fichier JSON | OUT: argparse.Namespace | MODIFIE: rien
# APPELÉ PAR: noisy.py | APPELLE: config, argparse, json

import argparse
import json
import logging
from typing import List

from .config import (
    DEFAULT_CONNECTIONS_PER_HOST, DEFAULT_CRUX_COUNT, DEFAULT_CRUX_REFRESH_DAYS,
    DEFAULT_DASHBOARD_PORT, DEFAULT_DNS_WORKERS, DEFAULT_DOMAIN_DELAY,
    DEFAULT_KEEPALIVE_TIMEOUT, DEFAULT_MAX_DEPTH, DEFAULT_MAX_LINKS_PER_PAGE,
    DEFAULT_MAX_QUEUE_SIZE, DEFAULT_MAX_SLEEP, DEFAULT_MIN_SLEEP,
    DEFAULT_MOBILE_RATIO, DEFAULT_NUM_USERS, DEFAULT_POST_NOISE_WORKERS,
    DEFAULT_RUN_TIMEOUT_SECONDS, DEFAULT_SEARCH_WORKERS,
    DEFAULT_THREADS, DEFAULT_TOTAL_CONNECTIONS, DEFAULT_UA_REFRESH_DAYS,
    REGION_PRESETS,
)

log = logging.getLogger(__name__)


def load_config_file(path: str) -> dict:
    """Charge un fichier JSON et retourne les overrides CLI compatibles."""
    log.info(f"[DEBUT] load_config_file | path={path}")
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        log.warning(f"[WARN] load_config_file | {e}")
        return {}

    supported = {
        "max_depth", "min_sleep", "max_sleep", "timeout",
        "threads", "num_users", "domain_delay", "max_queue_size",
        "max_links_per_page", "crux_count", "dns_workers",
    }
    result = {k: v for k, v in data.items() if k in supported and v not in (None, False)}
    log.info(f"[FIN] load_config_file | keys={list(result.keys())}")
    return result


def validate_args(args) -> List[str]:
    """Valide les arguments. Retourne liste d'erreurs (vide = OK)."""
    errors = []
    if args.min_sleep > args.max_sleep:
        errors.append(f"--min_sleep ({args.min_sleep}) doit être <= --max_sleep ({args.max_sleep})")
    if args.threads <= 0:
        errors.append(f"--threads doit être > 0, reçu {args.threads}")
    if args.num_users <= 0:
        errors.append(f"--num_users doit être > 0, reçu {args.num_users}")
    if args.max_depth <= 0:
        errors.append(f"--max_depth doit être > 0, reçu {args.max_depth}")
    if args.crux_count <= 0:
        errors.append(f"--crux_count doit être > 0, reçu {args.crux_count}")
    if args.domain_delay < 0:
        errors.append(f"--domain_delay doit être >= 0, reçu {args.domain_delay}")
    if args.connections_per_host <= 0:
        errors.append("--connections_per_host doit être > 0")
    if args.total_connections < args.connections_per_host:
        errors.append(
            f"--total_connections ({args.total_connections}) doit être >= "
            f"--connections_per_host ({args.connections_per_host})"
        )
    per_user_queue = args.max_queue_size // args.num_users if args.num_users > 0 else 0
    if per_user_queue < 10:
        errors.append(f"Queue par user trop petite ({per_user_queue}). Augmenter --max_queue_size.")
    for r in (getattr(args, "regions", None) or []):
        if r not in REGION_PRESETS:
            errors.append(f"--region inconnu '{r}'. Valides: {', '.join(sorted(REGION_PRESETS))}")
    schedule = getattr(args, "schedule", None)
    if schedule:
        try:
            parts = schedule.split("-")
            s, e = int(parts[0]), int(parts[1])
            if not (0 <= s <= 23 and 0 <= e <= 23):
                errors.append(f"--schedule heures doivent être 0-23, reçu {schedule}")
        except (ValueError, IndexError):
            errors.append(f"--schedule format invalide '{schedule}'. Attendu: 8-23")
    mr = getattr(args, "mobile_ratio", 0)
    if not (0 <= mr <= 1):
        errors.append(f"--mobile-ratio doit être entre 0 et 1, reçu {mr}")
    return errors


def build_parser() -> argparse.ArgumentParser:
    """Construit le parser CLI complet."""
    p = argparse.ArgumentParser(description="Générateur de bruit DNS/HTTP")
    p.add_argument("--config", help="Fichier JSON de configuration (les flags CLI ont priorité)")
    p.add_argument("--validate-config", action="store_true", help="Valide la config et quitte")
    p.add_argument("--dry-run", action="store_true", help="Affiche la config résolue sans crawler")
    p.add_argument("--log", default="info", choices=["debug", "info", "warning", "error"])
    p.add_argument("--logfile")
    p.add_argument("--threads", type=int, default=DEFAULT_THREADS,
                   help="Workers parallèles par user (défaut: %(default)s)")
    p.add_argument("--num_users", type=int, default=DEFAULT_NUM_USERS,
                   help="Nombre d'utilisateurs virtuels (défaut: %(default)s)")
    p.add_argument("--max_depth", type=int, default=DEFAULT_MAX_DEPTH)
    p.add_argument("--min_sleep", type=float, default=DEFAULT_MIN_SLEEP)
    p.add_argument("--max_sleep", type=float, default=DEFAULT_MAX_SLEEP)
    p.add_argument("--domain_delay", type=float, default=DEFAULT_DOMAIN_DELAY)
    p.add_argument("--total_connections", type=int, default=DEFAULT_TOTAL_CONNECTIONS)
    p.add_argument("--connections_per_host", type=int, default=DEFAULT_CONNECTIONS_PER_HOST)
    p.add_argument("--keepalive_timeout", type=int, default=DEFAULT_KEEPALIVE_TIMEOUT)
    p.add_argument("--crux_count", type=int, default=DEFAULT_CRUX_COUNT)
    p.add_argument("--crux_refresh_days", type=float, default=DEFAULT_CRUX_REFRESH_DAYS)
    p.add_argument("--ua_refresh_days", type=float, default=DEFAULT_UA_REFRESH_DAYS)
    p.add_argument("--max_queue_size", type=int, default=DEFAULT_MAX_QUEUE_SIZE)
    p.add_argument("--max_links_per_page", type=int, default=DEFAULT_MAX_LINKS_PER_PAGE)
    p.add_argument("--dns_workers", type=int, default=DEFAULT_DNS_WORKERS)
    p.add_argument("--timeout", type=int, default=DEFAULT_RUN_TIMEOUT_SECONDS,
                   help="Arrêt après N secondes (défaut: infini)")
    p.add_argument("--dashboard", action="store_true",
                   help="Active le dashboard web temps réel")
    p.add_argument("--dashboard-port", type=int, default=DEFAULT_DASHBOARD_PORT,
                   help="Port du dashboard (défaut: %(default)s)")
    p.add_argument("--dashboard-host", default="127.0.0.1",
                   help="Adresse du dashboard (défaut: 127.0.0.1)")
    p.add_argument("--post-noise-workers", type=int, default=DEFAULT_POST_NOISE_WORKERS,
                   help="Workers POST bruit (défaut: %(default)s)")
    p.add_argument("--webhook-url", default=None,
                   help="URL webhook pour alertes (optionnel)")
    p.add_argument("--tld", default=None,
                   help="Filtrer par TLD pays (ex: fr,de,uk). Les TLD génériques passent toujours.")
    p.add_argument("--region", dest="regions", action="append", default=None,
                   help=f"Preset régional ({', '.join(sorted(REGION_PRESETS))}). Répétable.")
    p.add_argument("--schedule", default=None,
                   help="Heures actives (ex: 8-23). Hors plage = pause.")
    p.add_argument("--geo", default=None,
                   help="Profil géo (ex: europe_fr, asia_jp, americas_us). Auto-assign Accept-Language.")
    p.add_argument("--mobile-ratio", type=float, default=DEFAULT_MOBILE_RATIO,
                   help="Ratio d'utilisateurs mobiles 0-1 (défaut: %(default)s)")
    p.add_argument("--search-workers", type=int, default=DEFAULT_SEARCH_WORKERS,
                   help="Workers de bruit recherche web (défaut: %(default)s)")
    p.add_argument("--history-file", default=None,
                   help="Fichier historique navigateur (JSON/TXT) à mixer dans le bruit")
    return p

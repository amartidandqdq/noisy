# stealth_lifecycle.py - Spawn/cancel/drain des workers stealth piloté par dashboard
# IN: collector (acces a _stealth_workers, _stealth_ctx, _crawler_params, crawlers)
# OUT: tasks asyncio managed | APPELLE: dns_prefetch, dns_stealth, stream_noise, ech_client, quic_probe

import asyncio
import logging
import random as _r
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .dashboard_collector import MetricsCollector

log = logging.getLogger(__name__)

# Features that spawn background workers; managed by MetricsCollector lifecycle.
STEALTH_WORKER_KEYS = (
    "dns_prefetch", "thirdparty_burst", "background_noise",
    "nxdomain_probes", "stream_noise", "ech", "quic_probe",
)


def setup_context(collector: "MetricsCollector", dns_hosts, dns_cache):
    """Context requis pour spawn/cancel des workers stealth via toggles."""
    collector._stealth_ctx = {"dns_hosts": dns_hosts, "dns_cache": dns_cache}


def start_worker(collector: "MetricsCollector", key: str):
    """Spawn le(s) worker(s) pour une feature stealth. Idempotent."""
    if not collector._stealth_ctx:
        log.warning(f"[FEATURES] {key}: context non init, skip spawn")
        return
    live = [t for t in collector._stealth_workers.get(key, []) if not t.done()]
    if live:
        return
    stop = collector._stop_event
    dns_hosts = collector._stealth_ctx["dns_hosts"]
    dns_cache = collector._stealth_ctx["dns_cache"]
    bl = collector._crawler_params.get("domain_blocklist", set()) if collector._crawler_params else set()
    tasks = []
    if key == "dns_prefetch":
        from .dns_prefetch import dns_prefetch_worker
        tasks.append(asyncio.create_task(
            dns_prefetch_worker(dns_hosts, stop, dns_cache, domain_blocklist=bl, worker_id=0)))
    elif key == "thirdparty_burst":
        from .dns_stealth import thirdparty_burst_worker, microburst_worker
        tasks.append(asyncio.create_task(thirdparty_burst_worker(dns_hosts, stop, dns_cache)))
        tasks.append(asyncio.create_task(microburst_worker(dns_hosts, stop, dns_cache)))
    elif key == "background_noise":
        from .dns_stealth import background_noise_worker
        tasks.append(asyncio.create_task(background_noise_worker(stop, dns_cache)))
    elif key == "nxdomain_probes":
        from .dns_stealth import nxdomain_probe_worker
        tasks.append(asyncio.create_task(nxdomain_probe_worker(stop, dns_cache)))
    elif key == "stream_noise":
        from .stream_noise import stream_noise_worker
        tasks.append(asyncio.create_task(stream_noise_worker(stop, dns_cache)))
    elif key == "ech":
        from .ech_client import ech_worker
        tasks.append(asyncio.create_task(ech_worker(dns_hosts, stop)))
    elif key == "quic_probe":
        from .quic_probe import quic_worker
        tasks.append(asyncio.create_task(quic_worker(stop, _r.Random(), dns_cache)))
    if tasks:
        collector._stealth_workers[key] = tasks
        log.info(f"[FEATURES] {key}: {len(tasks)} worker(s) demarre(s)")


def stop_worker(collector: "MetricsCollector", key: str):
    """Cancel tous les workers d'une feature + drain en arriere-plan."""
    tasks = collector._stealth_workers.get(key, [])
    alive = [t for t in tasks if not t.done()]
    for t in alive:
        t.cancel()
    collector._stealth_workers[key] = []
    if alive:
        drain = asyncio.create_task(_drain_cancelled(alive))
        collector._drain_tasks.add(drain)
        drain.add_done_callback(collector._drain_tasks.discard)
        log.info(f"[FEATURES] {key}: {len(alive)} worker(s) arrete(s)")


async def _drain_cancelled(tasks):
    """Attend la terminaison propre de tasks cancelled (evite RuntimeWarning)."""
    await asyncio.gather(*tasks, return_exceptions=True)


def worker_status(collector: "MetricsCollector") -> dict:
    """Pour chaque feature worker: state (running/error/off) + count running."""
    status = {}
    features = collector.crawlers[0].features if collector.crawlers else {}
    for key in STEALTH_WORKER_KEYS:
        tasks = collector._stealth_workers.get(key, [])
        running = sum(1 for t in tasks if not t.done())
        enabled = bool(features.get(key, False))
        if enabled and running > 0:
            state = "running"
        elif enabled and running == 0:
            state = "error"
        else:
            state = "off"
        status[key] = {"state": state, "running": running}
    return status


def sync_workers(collector: "MetricsCollector"):
    """Au demarrage: spawn les workers pour toutes les features deja ON."""
    features = collector.crawlers[0].features if collector.crawlers else {}
    for key in STEALTH_WORKER_KEYS:
        if features.get(key, False):
            start_worker(collector, key)

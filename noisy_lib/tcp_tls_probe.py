# tcp_tls_probe.py - TCP+TLS+GET avec Range payload (anti-DPI)
# IN: ip, host, rng | OUT: bool ok
# APPELE PAR: dns_prefetch, dns_stealth | APPELLE: tls_profiles, config

import asyncio
import logging
import random

from .config import PROBE_RANGE_MAX, PROBE_RANGE_MIN, UA_FALLBACK
from .tls_profiles import get_rotated_ssl_context

log = logging.getLogger(__name__)


async def tcp_tls_probe(ip: str, host: str, rng: random.Random, timeout: float = 10) -> bool:
    """TCP+TLS+GET avec Range payload (4-12KB) — anti-DPI. Retourne True si OK.

    Resout pas le DNS : prend l'IP deja resolue. Ouvre une connexion TLS,
    envoie un GET / avec Range pour faire arriver un payload visible par DPI
    (vs HEAD 0-byte qui est detectable comme scan), lit la reponse, ferme.

    Garantit la fermeture du writer en cas d'exception (try/finally) pour
    eviter le socket leak documente dans CLAUDE.md.
    """
    writer = None
    try:
        ssl_ctx = get_rotated_ssl_context(rng, include_h2=True)
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, 443, ssl=ssl_ctx, server_hostname=host),
            timeout=timeout,
        )
        ua = rng.choice(UA_FALLBACK)
        range_end = rng.randint(PROBE_RANGE_MIN, PROBE_RANGE_MAX)
        req = (
            f"GET / HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"User-Agent: {ua}\r\n"
            f"Accept: text/html,application/xhtml+xml,*/*;q=0.8\r\n"
            f"Accept-Language: en-US,en;q=0.9\r\n"
            f"Range: bytes=0-{range_end}\r\n"
            f"Connection: close\r\n\r\n"
        )
        writer.write(req.encode())
        await writer.drain()
        await asyncio.wait_for(reader.read(range_end + 2048), timeout=timeout)
        return True
    except Exception:
        return False
    finally:
        if writer is not None:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

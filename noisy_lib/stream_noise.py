# stream_noise.py - Simulation streaming video (connexions longues CDN)
# IN: stop_event, dns_cache | OUT: none | MODIFIE: rien
# APPELE PAR: noisy.py | APPELLE: dns_resolver, tls_profiles, config, throttle

import asyncio
import logging
import random
import time

from .config import (
    STREAM_CHUNK_DELAY, STREAM_CHUNK_SIZE,
    STREAM_PAUSE, STREAM_SESSION_DURATION,
    STREAMING_CDN_DOMAINS, UA_FALLBACK,
)
from .profiles import diurnal_sleep
from .throttle import BandwidthThrottle, assign_throttle
from .tls_profiles import get_rotated_ssl_context

log = logging.getLogger(__name__)

# Read buffer for chunked download
_READ_CHUNK = 16_384  # 16KB per read (simule buffering video)


async def _stream_session(
    ip: str, host: str, rng: random.Random,
    duration: float, throttle: BandwidthThrottle,
) -> int:
    """Maintient une connexion longue et telecharge en chunks. Retourne bytes total."""
    total_bytes = 0
    writer = None
    try:
        ssl_ctx = get_rotated_ssl_context(rng, include_h2=True)
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, 443, ssl=ssl_ctx, server_hostname=host),
            timeout=15,
        )
        # Requete Range large (simule buffer video)
        chunk_size = rng.randint(*STREAM_CHUNK_SIZE)
        ua = rng.choice(UA_FALLBACK)
        req = (
            f"GET / HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"User-Agent: {ua}\r\n"
            f"Accept: */*\r\n"
            f"Range: bytes=0-{chunk_size}\r\n"
            f"Connection: keep-alive\r\n\r\n"
        )
        writer.write(req.encode())
        await writer.drain()

        # Lire en chunks avec delai (simule buffering)
        start = time.monotonic()
        while time.monotonic() - start < duration:
            try:
                data = await asyncio.wait_for(reader.read(_READ_CHUNK), timeout=10)
                if not data:
                    break
                total_bytes += len(data)
                if throttle:
                    await throttle.consume(len(data))
            except asyncio.TimeoutError:
                break
            # Delai inter-chunk (simule player video qui buffer)
            await asyncio.sleep(rng.uniform(*STREAM_CHUNK_DELAY))
    except Exception as e:
        log.debug(f"[STREAM] session error host={host}: {e}")
    finally:
        if writer is not None:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
    return total_bytes


async def stream_noise_worker(
    stop_event: asyncio.Event,
    dns_cache,
    worker_id: int = 0,
) -> None:
    """Simule streaming video : connexions longues CDN avec chunks reguliers."""
    log.info(f"[DEBUT] stream_noise | id={worker_id} cdn_pool={len(STREAMING_CDN_DOMAINS)}")
    rng = random.Random()
    # Throttle dedie au streaming — profil fiber (simule streaming HD)
    throttle = assign_throttle(is_mobile=False, rng=rng)

    while not stop_event.is_set():
        host = rng.choice(STREAMING_CDN_DOMAINS)
        ip = await dns_cache.resolve(host)
        if ip is None:
            await asyncio.sleep(rng.uniform(10, 30))
            continue

        # Session streaming : 1-5 min
        duration = rng.uniform(*STREAM_SESSION_DURATION)
        total = await _stream_session(ip, host, rng, duration, throttle)
        log.debug(f"[STREAM] host={host} duration={duration:.0f}s bytes={total}")

        # Pause entre sessions (simule pause entre videos)
        await diurnal_sleep(rng, *STREAM_PAUSE)

    log.info(f"[FIN] stream_noise | id={worker_id}")

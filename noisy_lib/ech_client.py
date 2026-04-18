# ech_client.py - Probe ECH (Encrypted Client Hello) via curl_cffi + worker periodique
# IN: host:str, rng / domains, stop_event | OUT: bool / None | MODIFIE: rien
# APPELE PAR: dashboard_collector (ech_worker), dns_stealth.py, dns_prefetch.py | APPELLE: curl_cffi, config

import asyncio
import logging
import random
from typing import Optional

from .config import PROBE_RANGE_MAX, PROBE_RANGE_MIN, UA_FALLBACK

log = logging.getLogger(__name__)

_ECH_AVAILABLE: Optional[bool] = None


def is_ech_available() -> bool:
    """True si curl_cffi est installe et fonctionnel."""
    global _ECH_AVAILABLE
    if _ECH_AVAILABLE is None:
        try:
            from curl_cffi.requests import AsyncSession  # noqa: F401
            _ECH_AVAILABLE = True
        except ImportError:
            _ECH_AVAILABLE = False
            log.warning("[ECH] curl_cffi non installe — ECH desactive, fallback TLS classique")
    return _ECH_AVAILABLE


async def ech_probe(host: str, rng: random.Random) -> bool:
    """GET+Range via curl_cffi en impersonate=chrome.
    ECH n'est negocie QUE si (a) curl_cffi est link a une BoringSSL recente avec ECH,
    ET (b) le serveur publie un ECHConfig via DNS HTTPS RR (ex: Cloudflare).
    Sinon = TLS classique avec SNI en clair. Cette fonction ne verifie pas la negotiation.
    Retourne True si la requete a abouti."""
    if not is_ech_available():
        return False

    try:
        from curl_cffi.requests import AsyncSession

        range_end = rng.randint(PROBE_RANGE_MIN, PROBE_RANGE_MAX)
        url = f"https://{host}/"

        async with AsyncSession(impersonate="chrome") as session:
            resp = await asyncio.wait_for(
                session.get(
                    url,
                    headers={
                        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Range": f"bytes=0-{range_end}",
                        "Connection": "close",
                    },
                    timeout=15,
                    allow_redirects=True,
                ),
                timeout=20,
            )
            log.debug(f"[ECH] host={host} status={resp.status_code} bytes={len(resp.content)}")
            return resp.status_code < 500

    except asyncio.TimeoutError:
        log.debug(f"[ECH] timeout host={host}")
        return False
    except Exception as e:
        log.debug(f"[ECH] failed host={host}: {e}")
        return False


async def ech_worker(domains, stop_event: asyncio.Event) -> None:
    """Probe ECH periodiquement sur des hosts aleatoires (60-180s interval)."""
    if not is_ech_available():
        log.warning("[ECH] worker exit — curl_cffi non dispo")
        return
    log.info(f"[DEBUT] ech_worker | hosts={len(domains)}")
    rng = random.Random()
    while not stop_event.is_set():
        try:
            if domains:
                host = rng.choice(domains)
                await ech_probe(host, rng)
            await asyncio.sleep(rng.uniform(60, 180))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.debug(f"[ECH] worker loop err: {e}")
            await asyncio.sleep(30)

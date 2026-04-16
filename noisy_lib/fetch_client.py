# fetch_client.py - Requête HTTP avec retry exponentiel
# IN: session, url:str, headers:dict | OUT: FetchResult | MODIFIE: rien
# APPELÉ PAR: crawler.py | APPELLE: aiohttp, config, tls_profiles, throttle

import asyncio
import logging
import ssl
from typing import Optional

import aiohttp

from .config import MAX_RESPONSE_BYTES, MAX_RETRIES, PREFETCH_MAX_BODY, REQUEST_TIMEOUT, RETRY_BASE_DELAY
from .tls_profiles import DEFAULT_SSL_CONTEXT

log = logging.getLogger(__name__)


class FetchResult:
    """Résultat d'un fetch : html, status, bytes, ou erreur réseau."""
    __slots__ = ("html", "status", "bytes_received", "error_msg")

    def __init__(self, html: Optional[str], status: int, bytes_received: int = 0, error_msg: str = ""):
        self.html = html
        self.status = status
        self.bytes_received = bytes_received
        self.error_msg = error_msg

    @property
    def ok(self) -> bool:
        return self.html is not None

    @property
    def is_client_error(self) -> bool:
        return 400 <= self.status < 500

    @property
    def is_server_error(self) -> bool:
        return self.status >= 500


async def fetch_with_retry(
    session: aiohttp.ClientSession,
    url: str,
    headers: dict,
    ssl_context: Optional[ssl.SSLContext] = None,
    throttle=None,
    lightweight: bool = False,
) -> FetchResult:
    """GET avec backoff exponentiel. lightweight=True: Connection:close, 64KB max, 0 retry."""
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    last_exc: Optional[Exception] = None
    ctx = ssl_context or DEFAULT_SSL_CONTEXT

    max_bytes = PREFETCH_MAX_BODY if lightweight else MAX_RESPONSE_BYTES
    max_retries = 1 if lightweight else MAX_RETRIES
    req_headers = dict(headers)
    if lightweight:
        req_headers["Connection"] = "close"

    for attempt in range(max_retries):
        try:
            async with session.get(
                url, headers=req_headers, timeout=timeout,
                ssl=ctx, allow_redirects=True,
            ) as resp:
                if resp.status >= 500:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))
                        continue
                    return FetchResult(None, resp.status, error_msg=f"HTTP {resp.status}")
                if resp.status >= 400:
                    return FetchResult(None, resp.status, error_msg=f"HTTP {resp.status}")
                raw = await resp.content.read(max_bytes)
                # Apply bandwidth throttle if provided
                if throttle:
                    await throttle.consume(len(raw))
                html = raw.decode(resp.charset or "utf-8", errors="replace")
                return FetchResult(html, resp.status, bytes_received=len(raw))
        except (aiohttp.ClientError, asyncio.TimeoutError, ssl.SSLError) as e:
            last_exc = e
            log.debug(f"[RETRY] attempt={attempt + 1}/{max_retries} url={url} err={e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))

    if last_exc:
        raise last_exc
    return FetchResult(None, 0)

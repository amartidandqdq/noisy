# asset_fetcher.py - Telechargement partiel de ressources statiques
# IN: session, asset_urls, rng | OUT: bytes fetched | MODIFIE: rien
# APPELE PAR: crawler.py | APPELLE: aiohttp, config

import asyncio
import logging
import random
from typing import List
from urllib.parse import urlsplit

import aiohttp

from .config import REQUEST_TIMEOUT

log = logging.getLogger(__name__)

# Max assets to fetch per page
ASSET_MAX_PER_PAGE = 5
# Partial download size for images/media (16-64 KB)
ASSET_PARTIAL_MIN = 16_384
ASSET_PARTIAL_MAX = 65_536

# Extensions that get partial download (Range header)
_PARTIAL_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
                       ".ico", ".pdf", ".woff", ".woff2", ".ttf"}

# Extensions to skip entirely (too large or binary)
_SKIP_EXTENSIONS = {".mp4", ".mp3", ".avi", ".mov", ".zip", ".tar",
                    ".gz", ".exe", ".dmg", ".iso", ".bin"}


async def fetch_assets(
    session: aiohttp.ClientSession,
    asset_urls: List[str],
    rng: random.Random,
    headers: dict,
    ssl_context=None,
    max_assets: int = ASSET_MAX_PER_PAGE,
) -> int:
    """Fetch 2-max_assets ressources statiques. Retourne total bytes."""
    if not asset_urls:
        return 0
    upper = min(max_assets, len(asset_urls))
    n = rng.randint(min(1, upper), max(1, upper))
    selected = rng.sample(asset_urls, min(n, len(asset_urls)))
    total_bytes = 0
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)

    for url in selected:
        ext = _get_extension(url)
        if ext in _SKIP_EXTENSIONS:
            continue
        try:
            req_headers = dict(headers)
            req_headers.pop("Upgrade-Insecure-Requests", None)
            # Partial download for images/media
            if ext in _PARTIAL_EXTENSIONS:
                end = rng.randint(ASSET_PARTIAL_MIN, ASSET_PARTIAL_MAX)
                req_headers["Range"] = f"bytes=0-{end}"
                req_headers["Accept"] = "image/webp,image/apng,image/*,*/*;q=0.8"
            elif ext in (".css",):
                req_headers["Accept"] = "text/css,*/*;q=0.1"
            elif ext in (".js",):
                req_headers["Accept"] = "*/*"

            async with session.get(
                url, headers=req_headers, timeout=timeout,
                ssl=ssl_context, allow_redirects=True,
            ) as resp:
                if resp.status < 400:
                    chunk = await resp.content.read(ASSET_PARTIAL_MAX)
                    total_bytes += len(chunk)
            # Small delay between asset fetches (realistic)
            await asyncio.sleep(rng.uniform(0.1, 0.5))
        except Exception:
            pass
    return total_bytes


def _get_extension(url: str) -> str:
    """Extrait l'extension du path URL."""
    path = urlsplit(url).path
    dot = path.rfind(".")
    if dot >= 0:
        ext = path[dot:].lower().split("?")[0]
        return ext if len(ext) <= 6 else ""
    return ""

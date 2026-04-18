# page_consent.py - Detection CMP + simulation acceptation cookies
# IN: HTML brut, session aiohttp | OUT: bytes downloaded | MODIFIE: rien
# APPELE PAR: crawler.fetch | APPELLE: aiohttp session GET

import asyncio
import logging
import ssl
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

import aiohttp

from . import efficacy

log = logging.getLogger(__name__)

# Marqueurs CMP detectables dans le HTML (script src ou onclick)
# -> URL de "consent log" typique a frapper apres acceptation
CMP_MARKERS = {
    "cookielaw.org": "https://cdn.cookielaw.org/consent/{id}/consentReceipt.json",
    "cookiebot.com": "https://consent.cookiebot.com/uc.js",
    "didomi.io": "https://api.privacy-center.org/v1/apps/sdk/notice/config",
    "sourcepoint.com": "https://cdn.privacy-mgmt.com/wrapperMessagingWithoutDetection.js",
    "quantcast.com": "https://quantcast.mgr.consensu.org/cmp.js",
    "trustarc.com": "https://consent.trustarc.com/notice",
    "iubenda.com": "https://cdn.iubenda.com/cs/iubenda_cs.js",
    "termly.io": "https://app.termly.io/embed.min.js",
}


def detect_cmp(html: str) -> list:
    """Renvoie la liste des CMP URLs a frapper si detecte dans le HTML."""
    if not html or len(html) > 2_000_000:
        return []
    found = []
    for marker, url in CMP_MARKERS.items():
        if marker in html:
            found.append(url)
    return found


async def simulate_consent(
    session: aiohttp.ClientSession,
    html: str,
    base_url: str,
    headers: dict,
    rng,
    ssl_context: Optional[ssl.SSLContext] = None,
    timeout: float = 5.0,
) -> int:
    """Apres detection CMP, frappe 1-2 endpoints consent avec petit jitter.

    Returns total bytes downloaded (best-effort, errors swallowed).
    """
    urls = detect_cmp(html)
    if not urls:
        return 0
    efficacy.bump("cookie_consent_detected", len(urls))
    # Limite pour ne pas exploser le trafic: max 2 CMP par page
    rng.shuffle(urls)
    urls = urls[:2]
    referer_headers = dict(headers)
    referer_headers["Referer"] = base_url
    referer_headers["Sec-Fetch-Dest"] = "script"
    referer_headers["Sec-Fetch-Mode"] = "no-cors"
    referer_headers["Sec-Fetch-Site"] = "cross-site"

    total = 0
    for url in urls:
        # Petit jitter pour ne pas tout frapper en burst (browser reel)
        await asyncio.sleep(rng.uniform(0.1, 0.6))
        try:
            async with session.get(
                url, headers=referer_headers, ssl=ssl_context,
                timeout=aiohttp.ClientTimeout(total=timeout),
                allow_redirects=True,
            ) as resp:
                # Lecture limitee: 32KB suffit pour simuler un script CMP
                chunk = await resp.content.read(32_768)
                total += len(chunk)
                efficacy.bump("cookie_consent")
        except (aiohttp.ClientError, asyncio.TimeoutError, ssl.SSLError):
            continue
        except Exception as e:
            log.debug(f"[consent] {url} failed: {e}")
            continue
    return total

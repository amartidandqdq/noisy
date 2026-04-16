# profiles.py - Profils utilisateurs, pool UA, modèle diurnal
# IN: user_id, ua:str, rng | OUT: UserProfile, UAPool | MODIFIE: pool interne
# APPELÉ PAR: noisy.py, crawler.py, workers.py | APPELLE: rien (stdlib)

import asyncio
import logging
import math
import random
import ssl
import time
from typing import List, Optional

log = logging.getLogger(__name__)

try:
    import brotli as _brotli
    _BR_SUPPORTED = True
except ImportError:
    _BR_SUPPORTED = False

_ACCEPT_ENCODING = "gzip, deflate, br" if _BR_SUPPORTED else "gzip, deflate"

# ---- Accept combos (base, sans Accept-Language — ajouté par geo) ----
_ACCEPT_VARIANTS = [
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
]

_CACHE_VARIANTS = [
    {"Cache-Control": "no-cache", "Pragma": "no-cache"},
    {"Cache-Control": "max-age=0"},
    {},  # pas de cache header (comme un vrai navigateur parfois)
]

# ---- Sec-Fetch (navigation réaliste) ----
SEC_FETCH_NAVIGATE = {"Sec-Fetch-Site": "none", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document", "Sec-Fetch-User": "?1"}
SEC_FETCH_SAME = {"Sec-Fetch-Site": "same-origin", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"}
SEC_FETCH_CROSS = {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"}

# ---- Sec-CH-UA (browser brand hints) ----
SEC_CH_UA_COMBOS = [
    {
        "Sec-CH-UA": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "Sec-CH-UA-Platform": '"Windows"',
    },
    {
        "Sec-CH-UA": '"Chromium";v="125", "Google Chrome";v="125", "Not-A.Brand";v="99"',
        "Sec-CH-UA-Platform": '"macOS"',
    },
    {
        "Sec-CH-UA": '"Chromium";v="126", "Microsoft Edge";v="126", "Not-A.Brand";v="99"',
        "Sec-CH-UA-Platform": '"Windows"',
    },
    {
        "Sec-CH-UA": '"Chromium";v="123", "Google Chrome";v="123", "Not-A.Brand";v="99"',
        "Sec-CH-UA-Platform": '"Linux"',
    },
]

# ---- Referrers externes réalistes ----
EXTERNAL_REFERRERS = [
    "https://www.google.com/",
    "https://www.google.com/search?q=",
    "https://www.bing.com/search?q=",
    "https://duckduckgo.com/?q=",
    "https://www.facebook.com/",
    "https://t.co/",
    "https://www.reddit.com/",
    "https://news.ycombinator.com/",
]

# ---- Geo profiles ----
GEO_PROFILES = {
    "europe_fr": {"lang": "fr-FR,fr;q=0.9,en;q=0.5", "tz_offset": 1},
    "europe_de": {"lang": "de-DE,de;q=0.9,en;q=0.5", "tz_offset": 1},
    "europe_es": {"lang": "es-ES,es;q=0.9,en;q=0.5", "tz_offset": 1},
    "europe_it": {"lang": "it-IT,it;q=0.9,en;q=0.5", "tz_offset": 1},
    "europe_uk": {"lang": "en-GB,en;q=0.9", "tz_offset": 0},
    "europe_nl": {"lang": "nl-NL,nl;q=0.9,en;q=0.5", "tz_offset": 1},
    "europe_pl": {"lang": "pl-PL,pl;q=0.9,en;q=0.3", "tz_offset": 1},
    "europe_pt": {"lang": "pt-PT,pt;q=0.9,en;q=0.5", "tz_offset": 0},
    "europe_se": {"lang": "sv-SE,sv;q=0.9,en;q=0.5", "tz_offset": 1},
    "americas_us": {"lang": "en-US,en;q=0.9", "tz_offset": -5},
    "americas_br": {"lang": "pt-BR,pt;q=0.9,en;q=0.5", "tz_offset": -3},
    "americas_mx": {"lang": "es-MX,es;q=0.9,en;q=0.3", "tz_offset": -6},
    "americas_ca": {"lang": "en-CA,en;q=0.9,fr;q=0.5", "tz_offset": -5},
    "asia_jp": {"lang": "ja-JP,ja;q=0.9,en;q=0.3", "tz_offset": 9},
    "asia_kr": {"lang": "ko-KR,ko;q=0.9,en;q=0.3", "tz_offset": 9},
    "asia_cn": {"lang": "zh-CN,zh;q=0.9,en;q=0.3", "tz_offset": 8},
    "asia_in": {"lang": "hi-IN,hi;q=0.9,en;q=0.7", "tz_offset": 5},
    "middle_east_ae": {"lang": "ar-AE,ar;q=0.9,en;q=0.5", "tz_offset": 4},
    "middle_east_tr": {"lang": "tr-TR,tr;q=0.9,en;q=0.3", "tz_offset": 3},
    "africa_za": {"lang": "en-ZA,en;q=0.9,af;q=0.5", "tz_offset": 2},
    "oceania_au": {"lang": "en-AU,en;q=0.9", "tz_offset": 10},
}

# ---- Mobile UAs ----
MOBILE_UA_POOL = [
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-A546B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 7a) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/122.0.6261.89 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_7_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; SAMSUNG SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/23.0 Chrome/115.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; 22101316G) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPad; CPU OS 17_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Mobile/15E148 Safari/604.1",
]

MOBILE_EXTRA_HEADERS = {
    "Sec-CH-UA-Mobile": "?1",
}

# Legacy compat
ACCEPT_HEADERS_POOL = [
    {"Accept": _ACCEPT_VARIANTS[0], "Accept-Language": "en-US,en;q=0.9",
     "Accept-Encoding": _ACCEPT_ENCODING, "Cache-Control": "no-cache",
     "Pragma": "no-cache", "Upgrade-Insecure-Requests": "1"},
]

_UA_FALLBACK = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.3; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
]


def _build_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0)
    return ctx


SSL_CONTEXT = _build_ssl_context()


def _diurnal_weight(hour: float) -> float:
    """Poids d'activité selon l'heure locale (0.05–1.0)."""
    t = (hour - 4) / 24 * 2 * math.pi
    daytime = 0.5 + 0.5 * math.cos(t + math.pi)
    evening_boost = max(0.0, math.cos((hour - 20) / 6 * math.pi) * 0.4)
    return max(0.05, min(1.0, daytime + evening_boost))


def _activity_pause_seconds(rng: random.Random) -> float:
    """5% de chance de pause AFK (5–30 min)."""
    return rng.uniform(300, 1800) if rng.random() < 0.05 else 0.0


class UserProfile:
    """Empreinte de navigation par utilisateur virtuel."""

    def __init__(
        self, user_id: int, ua: str, rng: random.Random,
        geo: Optional[str] = None,
        is_mobile: bool = False,
        schedule: Optional[tuple] = None,
    ):
        self.user_id = user_id
        self.ua = ua
        self.rng = rng
        self.geo = geo
        self.is_mobile = is_mobile
        self.schedule = schedule  # (start_hour, end_hour) or None
        self.diurnal_enabled = True  # False = vitesse constante
        self.sleep_phase_offset = rng.uniform(-1.5, 1.5)

        # Geo-aware Accept-Language
        geo_data = GEO_PROFILES.get(geo, {})
        self._accept_lang = geo_data.get("lang", "en-US,en;q=0.9")
        self._tz_offset = geo_data.get("tz_offset", 0)

        # Stealth: per-profile combos (stable per session, rotated periodically)
        self._rotate_interval = rng.randint(900, 3600)  # 15-60 min
        self._last_rotate = time.monotonic()
        self._rotate_fingerprint()

    def _rotate_fingerprint(self):
        """Rotation des headers stealth (simule mise à jour navigateur)."""
        self._accept = self.rng.choice(_ACCEPT_VARIANTS)
        self._cache = self.rng.choice(_CACHE_VARIANTS)
        self._sec_ch_ua = self.rng.choice(SEC_CH_UA_COMBOS) if not self.is_mobile else {}
        self._dnt = str(self.rng.randint(0, 1))
        self._last_rotate = time.monotonic()

    def _maybe_rotate(self):
        if time.monotonic() - self._last_rotate > self._rotate_interval:
            self._rotate_fingerprint()

    def get_headers(self, referrer: Optional[str] = None) -> dict:
        self._maybe_rotate()
        h = {
            "User-Agent": self.ua,
            "Accept": self._accept,
            "Accept-Language": self._accept_lang,
            "Accept-Encoding": _ACCEPT_ENCODING,
            "Upgrade-Insecure-Requests": "1",
            "DNT": self._dnt,
            "Connection": "keep-alive",
        }
        h.update(self._cache)
        h.update(self._sec_ch_ua)

        # Sec-Fetch headers (vary per request)
        if referrer:
            h["Referer"] = referrer
            h.update(SEC_FETCH_SAME if self.rng.random() < 0.7 else SEC_FETCH_CROSS)
        else:
            h.update(SEC_FETCH_NAVIGATE)

        # 10% external referrer (simulate coming from search/social)
        if not referrer and self.rng.random() < 0.10:
            h["Referer"] = self.rng.choice(EXTERNAL_REFERRERS)
            h.update(SEC_FETCH_CROSS)

        # Mobile headers
        if self.is_mobile:
            h.update(MOBILE_EXTRA_HEADERS)
            h["Sec-CH-UA-Platform"] = self.rng.choice(['"Android"', '"iOS"'])

        return h

    def diurnal_weight(self) -> float:
        if not self.diurnal_enabled:
            return 1.0  # vitesse constante
        lt = time.localtime()
        hour = lt.tm_hour + lt.tm_min / 60
        adjusted = (hour + self.sleep_phase_offset + self._tz_offset) % 24
        return _diurnal_weight(adjusted)

    def is_active_hour(self) -> bool:
        if self.schedule is None:
            return True
        hour = time.localtime().tm_hour
        start, end = self.schedule
        if start < end:
            return start <= hour < end
        return hour >= start or hour < end  # wrap (ex: 22-6)


class UAPool:
    """Pool thread-safe de user agents avec remplacement async."""

    def __init__(self, initial: List[str]):
        self._pool: List[str] = list(initial)
        self._lock = asyncio.Lock()

    def get_random(self, rng: Optional[random.Random] = None) -> str:
        return (rng or random).choice(self._pool)

    def sample(self, n: int, rng: Optional[random.Random] = None) -> List[str]:
        r = rng or random.Random()
        return r.sample(self._pool, n) if len(self._pool) >= n else [r.choice(self._pool) for _ in range(n)]

    async def replace(self, agents: List[str]) -> None:
        log.info(f"[DEBUT] UAPool.replace | count={len(agents)}")
        async with self._lock:
            self._pool = list(agents)
        log.info(f"[FIN] UAPool.replace")

    def __len__(self) -> int:
        return len(self._pool)

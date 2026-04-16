# throttle.py - Token bucket bandwidth throttling
# IN: profile_name, stream | OUT: throttled bytes | MODIFIE: rien
# APPELE PAR: fetch_client.py | APPELLE: asyncio, config

import asyncio
import random
import time
from typing import Optional

# Bandwidth profiles: (min_mbps, max_mbps)
BANDWIDTH_PROFILES = {
    "fiber": (50, 100),
    "4g": (10, 30),
    "adsl": (2, 8),
    "3g": (1, 5),
}

# Default assignment: desktop -> fiber/adsl, mobile -> 4g/3g
DESKTOP_PROFILES = ["fiber", "adsl", "fiber", "fiber"]  # 75% fiber, 25% adsl
MOBILE_PROFILES = ["4g", "4g", "4g", "3g"]  # 75% 4G, 25% 3G


class BandwidthThrottle:
    """Token bucket rate limiter pour simuler une bande passante reelle."""

    __slots__ = ("_bytes_per_sec", "_tokens", "_last_refill", "_capacity")

    def __init__(self, mbps: float):
        self._bytes_per_sec = mbps * 125_000  # Mbps -> bytes/sec
        self._capacity = self._bytes_per_sec  # 1 second burst
        self._tokens = self._capacity
        self._last_refill = time.monotonic()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._bytes_per_sec)
        self._last_refill = now

    async def consume(self, nbytes: int) -> None:
        """Attend que nbytes tokens soient disponibles."""
        while nbytes > 0:
            self._refill()
            available = min(nbytes, self._tokens)
            if available > 0:
                self._tokens -= available
                nbytes -= available
            if nbytes > 0:
                # Wait proportional to remaining bytes needed
                wait = nbytes / self._bytes_per_sec
                await asyncio.sleep(min(wait, 0.5))


def assign_throttle(is_mobile: bool, rng: Optional[random.Random] = None) -> BandwidthThrottle:
    """Assigne un profil de bande passante selon le type d'appareil."""
    r = rng or random.Random()
    profiles = MOBILE_PROFILES if is_mobile else DESKTOP_PROFILES
    name = r.choice(profiles)
    min_mbps, max_mbps = BANDWIDTH_PROFILES[name]
    mbps = r.uniform(min_mbps, max_mbps)
    return BandwidthThrottle(mbps)

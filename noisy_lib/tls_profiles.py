# tls_profiles.py - Rotation TLS cipher suites pour diversite JA3
# IN: rng | OUT: ssl.SSLContext | MODIFIE: rien
# APPELE PAR: profiles.py, crawler_session.py, workers.py | APPELLE: ssl, config

import logging
import random
import ssl
from typing import Optional

log = logging.getLogger(__name__)

# 6 cipher orderings producing different JA3 fingerprints.
# All use strong ciphers only — just reordered.
TLS_CIPHER_SUITES = [
    # Chrome-like: AES-256 first
    "TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256:TLS_AES_128_GCM_SHA256:"
    "ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20",
    # Firefox-like: ChaCha20 first
    "TLS_CHACHA20_POLY1305_SHA256:TLS_AES_256_GCM_SHA384:TLS_AES_128_GCM_SHA256:"
    "ECDHE+CHACHA20:ECDHE+AESGCM:DHE+CHACHA20:DHE+AESGCM",
    # Edge-like: AES-128 first
    "TLS_AES_128_GCM_SHA256:TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256:"
    "ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM",
    # Safari-like: ECDHE preference
    "TLS_AES_256_GCM_SHA384:TLS_AES_128_GCM_SHA256:TLS_CHACHA20_POLY1305_SHA256:"
    "ECDHE+AESGCM:DHE+AESGCM:ECDHE+CHACHA20",
    # Mixed: ChaCha20+AES interleaved
    "TLS_CHACHA20_POLY1305_SHA256:TLS_AES_128_GCM_SHA256:TLS_AES_256_GCM_SHA384:"
    "ECDHE+CHACHA20:DHE+AESGCM:ECDHE+AESGCM:DHE+CHACHA20",
    # Conservative: AES-256 only then fallback
    "TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256:TLS_AES_128_GCM_SHA256:"
    "DHE+AESGCM:ECDHE+AESGCM:DHE+CHACHA20:ECDHE+CHACHA20",
]

# Elliptic curve groups — vary to change JA3 extension fingerprint
_EC_GROUPS = [
    "x25519:prime256v1:secp384r1",
    "prime256v1:x25519:secp384r1",
    "x25519:secp384r1:prime256v1",
    "prime256v1:secp384r1:x25519",
]


def _build_default_context() -> ssl.SSLContext:
    """Contexte SSL par défaut (pas de rotation)."""
    ctx = ssl.create_default_context()
    ctx.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0)
    return ctx


# Singleton fallback — used when TLS rotation disabled
DEFAULT_SSL_CONTEXT = _build_default_context()


def get_rotated_ssl_context(rng: Optional[random.Random] = None) -> ssl.SSLContext:
    """Crée un SSLContext avec cipher suite aléatoire pour diversité JA3."""
    r = rng or random.Random()
    ctx = ssl.create_default_context()
    ctx.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0)

    cipher_str = r.choice(TLS_CIPHER_SUITES)
    try:
        ctx.set_ciphers(cipher_str)
    except ssl.SSLError:
        log.debug(f"[TLS] cipher set failed, using default")
        return DEFAULT_SSL_CONTEXT

    # Rotate elliptic curve groups if supported (Python 3.10+)
    if hasattr(ctx, "set_ecdh_curve"):
        try:
            ctx.set_ecdh_curve(r.choice(_EC_GROUPS).split(":")[0])
        except Exception:
            pass

    return ctx

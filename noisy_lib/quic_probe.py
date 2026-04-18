# quic_probe.py - Probe HTTP/3 (QUIC) via UDP/443
# IN: liste hosts QUIC-capables | OUT: rien | MODIFIE: rien
# APPELE PAR: dashboard_collector / noisy.py | APPELLE: socket UDP

import asyncio
import logging
import os
import secrets
import socket
from typing import Optional

from . import efficacy

log = logging.getLogger(__name__)

# Endpoints QUIC-capables (Cloudflare, Google, Fastly, Akamai, Apple)
# Real browsers periodically attempt HTTP/3 to these to upgrade if Alt-Svc says so.
QUIC_CAPABLE_HOSTS = [
    "www.cloudflare.com",
    "www.google.com",
    "fonts.googleapis.com",
    "www.youtube.com",
    "instagram.com",
    "facebook.com",
    "www.fastly.com",
    "www.akamai.com",
    "ajax.cloudflare.com",
    "imgs.xkcd.com",
]

# QUIC version 1 = 0x00000001 (RFC 9000)
QUIC_VERSION = b"\x00\x00\x00\x01"


def _build_quic_initial(dcid: bytes, scid: bytes) -> bytes:
    """Construit un paquet QUIC Initial minimal (long header).

    Format (RFC 9000, simplifie):
      1 byte:  header form + fixed bit + type (Initial=00) + reserved + PN length
      4 bytes: version
      1 byte:  DCID length
      N bytes: DCID
      1 byte:  SCID length
      N bytes: SCID
      1 byte:  token length (0 pour client Initial sans token)
      2 bytes: length (varint, length du reste)
      1 byte:  packet number (encrypted en vrai, on met du random)
      N bytes: payload encrypted (random pour observer = looks like QUIC)
    """
    # Header byte: long header (1) + fixed bit (1) + type Initial (00) + reserved (00) + PN length 0 (00) = 0xC0
    header = b"\xc0"
    header += QUIC_VERSION
    header += bytes([len(dcid)]) + dcid
    header += bytes([len(scid)]) + scid
    header += b"\x00"  # token length (varint, 0)
    # Payload: random ~1200 bytes (QUIC Initial doit etre >= 1200 bytes pour anti-amplification)
    payload = os.urandom(1180)
    # Length varint: 2-byte form (0x4000 prefix) for values 64-16383
    length_val = len(payload) + 1  # +1 for packet number
    length_bytes = (0x4000 | length_val).to_bytes(2, "big")
    header += length_bytes
    header += b"\x00"  # packet number (truncated, en vrai chiffre)
    header += payload
    return header


async def quic_probe(host: str, dns_cache=None, timeout: float = 1.5) -> bool:
    """Envoie un paquet QUIC Initial UDP/443 a host. Fire-and-forget.

    Returns True si paquet envoye (pas de reponse attendue).
    """
    loop = asyncio.get_running_loop()
    try:
        if dns_cache:
            ip = await dns_cache.resolve(host)
            if not ip:
                return False
        else:
            infos = await loop.getaddrinfo(host, 443, type=socket.SOCK_DGRAM)
            ip = infos[0][4][0]
    except Exception as e:
        log.debug(f"[quic] resolve {host} failed: {e}")
        return False

    dcid = secrets.token_bytes(8)
    scid = secrets.token_bytes(8)
    pkt = _build_quic_initial(dcid, scid)

    sock = socket.socket(socket.AF_INET if "." in ip else socket.AF_INET6, socket.SOCK_DGRAM)
    sock.setblocking(False)
    try:
        await asyncio.wait_for(loop.sock_sendto(sock, pkt, (ip, 443)), timeout=timeout)
        efficacy.bump("quic_probe")
        return True
    except (OSError, asyncio.TimeoutError) as e:
        log.debug(f"[quic] send {host}/{ip} failed: {e}")
        return False
    finally:
        sock.close()


async def quic_worker(stop_event: asyncio.Event, rng, dns_cache=None):
    """Worker periodique: probe QUIC sur 1 host random toutes 60-180s."""
    log.info("[quic_worker] started")
    while not stop_event.is_set():
        host = rng.choice(QUIC_CAPABLE_HOSTS)
        try:
            await quic_probe(host, dns_cache=dns_cache)
        except Exception as e:
            log.debug(f"[quic_worker] {host}: {e}")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=rng.uniform(60, 180))
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            raise
    log.info("[quic_worker] stopped")

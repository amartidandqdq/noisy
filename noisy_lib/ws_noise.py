# ws_noise.py - WebSocket/SSE idle connection noise
# IN: stop_event | OUT: none | MODIFIE: rien
# APPELE PAR: noisy.py | APPELLE: aiohttp, config

import asyncio
import logging
import random
import time
from typing import List

import aiohttp

from .config import UA_FALLBACK
from .profiles import _diurnal_weight

log = logging.getLogger(__name__)

# WebSocket/SSE endpoints for protocol diversity
WS_ENDPOINTS = [
    # Crypto tickers (public WebSocket)
    "wss://stream.binance.com:9443/ws/btcusdt@trade",
    "wss://ws.kraken.com/",
    "wss://ws-feed.exchange.coinbase.com",
    # Public chat/IRC-style
    "wss://irc-ws.chat.twitch.tv:443/",
    # News SSE-like (will fail gracefully)
    "wss://push.services.mozilla.com/",
]

# Messages to send on connect (protocol handshakes)
_WS_INIT_MESSAGES = {
    "stream.binance.com": None,  # auto-subscribed via URL
    "ws.kraken.com": '{"event":"subscribe","pair":["XBT/USD"],"subscription":{"name":"ticker"}}',
    "ws-feed.exchange.coinbase.com": '{"type":"subscribe","channels":["ticker"],"product_ids":["BTC-USD"]}',
    "irc-ws.chat.twitch.tv": "CAP REQ :twitch.tv/tags\r\nPASS SCHMOOPIIE\r\nNICK justinfan12345\r\nJOIN #twitchdev\r\n",
}

WS_MAX_CONNECTIONS = 5
WS_RECONNECT_BASE = 30  # seconds before reconnect on failure
WS_READ_TIMEOUT = 300  # 5 min idle read timeout


async def _ws_connect_one(
    session: aiohttp.ClientSession,
    url: str,
    stop_event: asyncio.Event,
    rng: random.Random,
) -> None:
    """Maintient une connexion WS, lit passivement, reconnecte sur drop."""
    ua = rng.choice(UA_FALLBACK)
    backoff = 0
    while not stop_event.is_set():
        try:
            async with session.ws_connect(
                url, headers={"User-Agent": ua}, timeout=30,
            ) as ws:
                log.debug(f"[WS] connected to {url.split('/')[2]}")
                backoff = 0
                # Send init message if needed
                host = url.split("/")[2].split(":")[0]
                init = _WS_INIT_MESSAGES.get(host)
                if init:
                    await ws.send_str(init)
                # Read passively until disconnect or stop
                while not stop_event.is_set():
                    try:
                        msg = await asyncio.wait_for(
                            ws.receive(), timeout=WS_READ_TIMEOUT,
                        )
                        if msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING,
                                        aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
                    except asyncio.TimeoutError:
                        # Send ping to keep alive
                        try:
                            await ws.ping()
                        except Exception:
                            break
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.debug(f"[WS] error {url.split('/')[2]}: {e}")
        # Exponential backoff on reconnect
        backoff = min(backoff + 1, 5)
        wait = WS_RECONNECT_BASE * (2 ** backoff) * rng.uniform(0.5, 1.5)
        lt = time.localtime()
        hour = lt.tm_hour + lt.tm_min / 60
        wait /= max(0.1, _diurnal_weight(hour))
        await asyncio.sleep(min(wait, 600))


async def ws_noise_worker(
    stop_event: asyncio.Event,
    worker_id: int = 0,
    max_connections: int = WS_MAX_CONNECTIONS,
) -> None:
    """Maintient N connexions WebSocket idle pour diversite protocole."""
    log.info(f"[DEBUT] ws_noise_worker | id={worker_id} max_conn={max_connections}")
    rng = random.Random()
    endpoints = list(WS_ENDPOINTS)
    rng.shuffle(endpoints)
    n = min(max_connections, len(endpoints))

    async with aiohttp.ClientSession() as session:
        tasks = [
            asyncio.create_task(_ws_connect_one(session, endpoints[i], stop_event, rng))
            for i in range(n)
        ]
        await stop_event.wait()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    log.info(f"[FIN] ws_noise_worker | id={worker_id}")

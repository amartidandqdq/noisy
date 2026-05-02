# dashboard.py - Serveur dashboard temps reel (FastAPI + WebSocket)
# IN: MetricsCollector | OUT: app FastAPI | MODIFIE: rien
# APPELE PAR: noisy.py | APPELLE: dashboard_collector, config, fastapi, uvicorn

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, PlainTextResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import (
    AUTO_PAUSE_FAIL_THRESHOLD, AUTO_PAUSE_MIN_REQUESTS,
    DASHBOARD_UPDATE_INTERVAL, REGION_PRESETS, WEBHOOK_TIMEOUT,
)
from .dashboard_collector import (
    MetricsCollector, STATIC_DIR,
)

# Re-export for backward compatibility (noisy.py imports from here)
__all__ = ["MetricsCollector", "start_dashboard", "create_app"]

log = logging.getLogger(__name__)


def create_app(collector: MetricsCollector) -> FastAPI:
    app = FastAPI(title="Noisy Dashboard", docs_url=None, redoc_url=None)

    app.mount("/css", StaticFiles(directory=str(STATIC_DIR / "css")), name="css")
    app.mount("/js", StaticFiles(directory=str(STATIC_DIR / "js")), name="js")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(html, headers={"Cache-Control": "no-cache, must-revalidate"})

    @app.get("/api/metrics")
    async def metrics():
        return collector.collect()

    @app.get("/api/export")
    async def export_metrics():
        data = collector.collect()
        return JSONResponse(
            content=data,
            headers={"Content-Disposition": "attachment; filename=noisy-metrics.json"},
        )

    @app.get("/api/config")
    async def get_config():
        return collector.get_runtime_config()

    @app.post("/api/config")
    async def set_config(data: dict):
        errors = collector.apply_config(data)
        if errors:
            return JSONResponse(status_code=400, content={"errors": errors})
        return {"status": "ok", "config": collector.get_runtime_config()}

    @app.post("/api/features")
    async def set_features(data: dict):
        result = collector.apply_features(data)
        if "error" in result:
            return JSONResponse(status_code=400, content=result)
        return result

    @app.get("/api/features")
    async def get_features():
        return collector.collect().get("features", {})

    @app.post("/api/tld-filter")
    async def set_tld_filter(data: dict):
        regions = data.get("regions", [])
        custom_tlds = data.get("custom_tlds", [])
        for r in regions:
            if r not in REGION_PRESETS:
                return JSONResponse(status_code=400, content={"error": f"region inconnue: {r}"})
        result = collector.apply_tld_filter(regions, custom_tlds)
        return result

    @app.get("/api/tld-filter")
    async def get_tld_filter():
        return {
            "regions": sorted(collector.regions),
            "tld_filter": sorted(collector.tld_filter),
            "available_regions": sorted(REGION_PRESETS.keys()),
        }

    @app.post("/api/users/add")
    async def add_user():
        result = collector.add_user()
        if "error" in result:
            return JSONResponse(status_code=400, content=result)
        return result

    @app.post("/api/users/remove")
    async def remove_user(data: dict = None):
        uid = data.get("user_id") if data else None
        result = await collector.remove_user(uid)
        if "error" in result:
            return JSONResponse(status_code=400, content=result)
        return result

    @app.post("/api/clear-logs")
    async def clear_logs():
        collector.shared_metrics.request_log.clear()
        collector.shared_metrics.recent_errors.clear()
        return {"status": "ok"}

    @app.post("/api/clear-stats")
    async def clear_stats():
        collector.shared_metrics.domain_stats.clear()
        collector.shared_metrics.tld_counts.clear()
        collector.shared_metrics.category_counts.clear()
        return {"status": "ok"}

    @app.post("/api/pause")
    async def pause():
        collector.shared_metrics.pause()
        log.info("[DASHBOARD] crawlers mis en pause")
        if collector.webhook_url:
            await _fire_webhook(collector.webhook_url, "paused", {})
        return {"paused": True}

    @app.post("/api/resume")
    async def resume():
        collector.shared_metrics.resume()
        log.info("[DASHBOARD] crawlers repris")
        if collector.webhook_url:
            await _fire_webhook(collector.webhook_url, "resumed", {})
        return {"paused": False}

    @app.get("/metrics", response_class=PlainTextResponse)
    async def prometheus():
        return PlainTextResponse(collector.prometheus_metrics(), media_type="text/plain; version=0.0.4")

    @app.websocket("/ws/metrics")
    async def ws_metrics(websocket: WebSocket):
        await websocket.accept()
        log.info("[DASHBOARD] client WebSocket connecte")
        try:
            while True:
                data = collector.collect()
                await websocket.send_text(json.dumps(data))
                # Webhook alert check
                if data["aggregate"]["alert_active"] and not collector._alert_fired:
                    collector._alert_fired = True
                    if collector.webhook_url:
                        await _fire_webhook(collector.webhook_url, "alert_high_fail_rate", data["aggregate"])
                elif not data["aggregate"]["alert_active"]:
                    collector._alert_fired = False
                # Auto-pause on fail spike
                a = data["aggregate"]
                total = a["visited"] + a["failed"]
                if (collector.auto_pause_enabled and not collector._auto_paused
                        and total >= AUTO_PAUSE_MIN_REQUESTS
                        and a["fail_pct"] >= AUTO_PAUSE_FAIL_THRESHOLD):
                    collector.shared_metrics.pause()
                    collector._auto_paused = True
                    log.warning(f"[AUTO-PAUSE] fail%={a['fail_pct']:.1f}% >= {AUTO_PAUSE_FAIL_THRESHOLD}%")
                    if collector.webhook_url:
                        await _fire_webhook(collector.webhook_url, "auto_paused", a)
                elif collector._auto_paused and a["fail_pct"] < AUTO_PAUSE_FAIL_THRESHOLD:
                    collector._auto_paused = False
                await asyncio.sleep(DASHBOARD_UPDATE_INTERVAL)
        except WebSocketDisconnect:
            log.info("[DASHBOARD] client WebSocket deconnecte")

    return app


async def _fire_webhook(url: str, event: str, data: dict):
    """Envoie un webhook POST (http/https uniquement)."""
    if not url.startswith(("http://", "https://")):
        log.warning(f"[WEBHOOK] URL invalide ignoree: {url}")
        return
    import aiohttp
    payload = {"event": event, "timestamp": datetime.now(timezone.utc).isoformat(), "data": data}
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=WEBHOOK_TIMEOUT))
        log.info(f"[WEBHOOK] {event} envoye a {url}")
    except Exception as e:
        log.warning(f"[WEBHOOK] echec {url}: {e}")


async def start_dashboard(collector: MetricsCollector, port: int, host: str = "127.0.0.1"):
    """Lance le serveur uvicorn en tache de fond asyncio."""
    import uvicorn

    if host != "127.0.0.1":
        log.warning(f"[DASHBOARD] bind sur {host} — AUCUNE authentification ! "
                    f"Toute machine du reseau peut controler le crawler.")
    app = create_app(collector)
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    log.info(f"[DASHBOARD] demarre sur http://{host}:{port}")
    await server.serve()

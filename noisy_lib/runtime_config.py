# runtime_config.py - Settings persistence + apply_config + apply_tld_filter
# IN: collector + data dict | OUT: errors list / status dict | MODIFIE: .noisy_settings.json
# APPELE PAR: dashboard_collector.MetricsCollector | APPELLE: config

import json
import logging
from pathlib import Path
from typing import List, TYPE_CHECKING

from .config import GENERIC_TLDS, REGION_PRESETS

if TYPE_CHECKING:
    from .dashboard_collector import MetricsCollector

log = logging.getLogger(__name__)

SETTINGS_FILE = Path(__file__).parent.parent / ".noisy_settings.json"


def save_settings(data: dict):
    """Sauvegarde les settings dans .noisy_settings.json (merge, pas overwrite)."""
    try:
        existing = load_settings()
        existing.update(data)
        SETTINGS_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        log.debug(f"[SETTINGS] sauvegarde: {list(data.keys())}")
    except Exception as e:
        log.warning(f"[SETTINGS] erreur sauvegarde: {e}")


def load_settings() -> dict:
    """Charge les settings persistes."""
    try:
        if SETTINGS_FILE.exists():
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning(f"[SETTINGS] erreur lecture: {e}")
    return {}


def get_runtime_config(collector: "MetricsCollector") -> dict:
    if not collector.crawlers:
        return {}
    c = collector.crawlers[0]
    cfg = {
        "num_users": len(collector.crawlers),
        "min_sleep": c.min_sleep,
        "max_sleep": c.max_sleep,
        "max_depth": c.max_depth,
        "concurrency": c.concurrency,
        "max_links_per_page": c.max_links_per_page,
        "domain_delay": collector.rate_limiter._domain_delay,
    }
    if collector.tld_filter:
        cfg["tld_filter"] = sorted(collector.tld_filter)
    if collector.regions:
        cfg["regions"] = sorted(collector.regions)
    return cfg


def apply_config(collector: "MetricsCollector", data: dict) -> list:
    errors = []
    safe = {}
    for key, cast, lo, hi in [
        ("min_sleep", float, 0.1, 300),
        ("max_sleep", float, 0.1, 600),
        ("max_depth", int, 1, 50),
        ("max_links_per_page", int, 1, 500),
        ("domain_delay", float, 0, 120),
    ]:
        if key in data:
            try:
                v = cast(data[key])
                if not (lo <= v <= hi):
                    errors.append(f"{key}: doit etre entre {lo} et {hi}")
                else:
                    safe[key] = v
            except (ValueError, TypeError):
                errors.append(f"{key}: valeur invalide")
    if errors:
        return errors
    for c in collector.crawlers:
        if "min_sleep" in safe:
            c.min_sleep = safe["min_sleep"]
        if "max_sleep" in safe:
            c.max_sleep = safe["max_sleep"]
        if "max_depth" in safe:
            c.max_depth = safe["max_depth"]
        if "max_links_per_page" in safe:
            c.max_links_per_page = safe["max_links_per_page"]
    if "domain_delay" in safe:
        collector.rate_limiter.domain_delay = safe["domain_delay"]
    save_settings({"config": safe})
    return []


def apply_tld_filter(collector: "MetricsCollector", regions: List[str], custom_tlds: List[str]) -> dict:
    """Applique un nouveau filtre TLD live sur les crawlers."""
    from . import extract_tld
    allowed = set()
    for r in regions:
        allowed |= REGION_PRESETS.get(r, set())
    allowed |= {t.strip().lower() for t in custom_tlds if t.strip()}
    collector.regions = regions
    collector.tld_filter = allowed

    if not collector.all_top_sites:
        return {"status": "ok", "filtered": 0, "message": "pas de sites CRUX charges"}

    if allowed:
        filtered = [s for s in collector.all_top_sites
                    if extract_tld(s) in GENERIC_TLDS or extract_tld(s) in allowed]
    else:
        filtered = list(collector.all_top_sites)

    for c in collector.crawlers:
        shuffled = list(filtered)
        c.rng.shuffle(shuffled)
        c.root_urls = set(shuffled[:500])
        while not c.queue.empty():
            try:
                c.queue.get_nowait()
                c.queue.task_done()
            except Exception:
                break
        for url in shuffled[:200]:
            try:
                c.queue.put_nowait((url, 0, None, c.max_depth))
            except Exception:
                break
    log.info(f"[TLD] Filtre live applique: {len(filtered)} sites (ccTLD: {sorted(allowed) if allowed else 'aucun'})")
    save_settings({"tld_filter": {"regions": regions, "custom_tlds": custom_tlds}})
    return {"status": "ok", "filtered": len(filtered), "tld_filter": sorted(allowed)}


def restore_saved_settings(collector: "MetricsCollector"):
    """Restaure les settings persistes depuis .noisy_settings.json."""
    saved = load_settings()
    if not saved:
        return
    restored = []
    if "features" in saved:
        try:
            collector.apply_features(saved["features"])
            restored.append("features")
        except Exception as e:
            log.warning(f"[SETTINGS] erreur restore features: {e}")
    if "config" in saved:
        try:
            apply_config(collector, saved["config"])
            restored.append("config")
        except Exception as e:
            log.warning(f"[SETTINGS] erreur restore config: {e}")
    if "tld_filter" in saved:
        try:
            tf = saved["tld_filter"]
            apply_tld_filter(collector, tf.get("regions", []), tf.get("custom_tlds", []))
            restored.append("tld_filter")
        except Exception as e:
            log.warning(f"[SETTINGS] erreur restore tld_filter: {e}")
    if restored:
        log.info(f"[SETTINGS] restaure: {', '.join(restored)}")

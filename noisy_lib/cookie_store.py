# cookie_store.py - Serialisation / deserialisation cookie jar
# IN: cookies dict, user_id | OUT: saved/loaded cookies | MODIFIE: .noisy_cookies/
# APPELE PAR: crawler.py | APPELLE: json, pathlib

import json
import logging
import time
from pathlib import Path
from typing import Dict, List

log = logging.getLogger(__name__)

COOKIE_DIR = Path(".noisy_cookies")


def save_cookies(cookies: Dict[str, str], user_id: int, domain_cookies: dict = None) -> None:
    """Sauvegarde les cookies d'un user dans un fichier JSON."""
    try:
        COOKIE_DIR.mkdir(exist_ok=True)
        path = COOKIE_DIR / f"user_{user_id}.json"
        data = {
            "user_id": user_id,
            "saved_at": time.time(),
            "cookies": domain_cookies or {},
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        log.debug(f"[COOKIES] saved user_{user_id} | {len(domain_cookies or {})} domains")
    except Exception as e:
        log.debug(f"[COOKIES] save failed user_{user_id}: {e}")


def load_cookies(user_id: int, max_age_days: int = 30) -> dict:
    """Charge les cookies d'un user depuis le fichier JSON.

    Retourne dict vide si fichier absent ou expire.
    Format retourne: {domain: {name: value, ...}, ...}
    """
    path = COOKIE_DIR / f"user_{user_id}.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        saved_at = data.get("saved_at", 0)
        if time.time() - saved_at > max_age_days * 86400:
            log.debug(f"[COOKIES] expired user_{user_id}")
            return {}
        cookies = data.get("cookies", {})
        log.debug(f"[COOKIES] loaded user_{user_id} | {len(cookies)} domains")
        return cookies
    except Exception as e:
        log.debug(f"[COOKIES] load failed user_{user_id}: {e}")
        return {}


def clear_cookies(user_id: int) -> None:
    """Supprime le fichier cookies d'un user."""
    path = COOKIE_DIR / f"user_{user_id}.json"
    if path.exists():
        path.unlink()

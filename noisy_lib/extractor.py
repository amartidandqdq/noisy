# extractor.py - Extraction et filtrage de liens HTML
# IN: html:str, base_url:str, blacklist:list | OUT: List[str] URLs | MODIFIE: rien
# APPELÉ PAR: crawler.py | APPELLE: html.parser (stdlib)

import logging
from html.parser import HTMLParser
from typing import List, Optional, Set
from urllib.parse import urljoin, urlsplit

log = logging.getLogger(__name__)


class LinkExtractor(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.links: List[str] = []
        self.assets: List[str] = []

    def handle_starttag(self, tag: str, attrs):
        attr_dict = dict(attrs)
        if tag == "base" and "href" in attr_dict:
            self.base_url = attr_dict["href"]
        elif tag == "a" and "href" in attr_dict:
            resolved = urljoin(self.base_url, attr_dict["href"])
            resolved = resolved.split("#")[0]
            if resolved.startswith("http"):
                self.links.append(resolved)
        # Static assets: img, link[stylesheet], script[src]
        elif tag == "img" and "src" in attr_dict:
            resolved = urljoin(self.base_url, attr_dict["src"]).split("#")[0]
            if resolved.startswith("http"):
                self.assets.append(resolved)
        elif tag == "link" and attr_dict.get("rel", "").lower() == "stylesheet" and "href" in attr_dict:
            resolved = urljoin(self.base_url, attr_dict["href"]).split("#")[0]
            if resolved.startswith("http"):
                self.assets.append(resolved)
        elif tag == "script" and "src" in attr_dict:
            resolved = urljoin(self.base_url, attr_dict["src"]).split("#")[0]
            if resolved.startswith("http"):
                self.assets.append(resolved)


def _host_blocked(url: str, domain_blocklist: Set[str]) -> bool:
    from . import host_in_blocklist
    return host_in_blocklist(url, domain_blocklist)


def extract_links(
    html: str, base_url: str,
    blacklist: Optional[List[str]] = None,
    domain_blocklist: Optional[Set[str]] = None,
) -> List[str]:
    """Extrait les liens http(s) du HTML, filtre la blacklist."""
    parser = LinkExtractor(base_url)
    try:
        parser.feed(html)
    except (ValueError, RuntimeError) as e:
        log.debug(f"[WARN] parsing | url={base_url} {e}")
    except Exception as e:
        log.error(f"[ERREUR] parsing | url={base_url} {e}")

    links = parser.links
    if blacklist:
        links = [lnk for lnk in links if not any(b in lnk for b in blacklist)]
    if domain_blocklist:
        links = [lnk for lnk in links if not _host_blocked(lnk, domain_blocklist)]
    return links


def extract_assets(
    html: str, base_url: str,
    blacklist: Optional[List[str]] = None,
) -> List[str]:
    """Extrait les URLs de ressources statiques (img, css, js) du HTML."""
    parser = LinkExtractor(base_url)
    try:
        parser.feed(html)
    except Exception:
        pass
    assets = parser.assets
    if blacklist:
        assets = [a for a in assets if not any(b in a for b in blacklist)]
    return assets

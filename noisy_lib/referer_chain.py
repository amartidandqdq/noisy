# referer_chain.py - Simulation realiste de chaines HTTP Referer
# IN: rng, target_url | OUT: referer str ou None | MODIFIE: rien
# APPELE PAR: crawler.py | APPELLE: config

import random
from typing import Optional
from urllib.parse import quote_plus, urlsplit

from .config import SEARCH_WORDS

# Search engine referer templates
_SEARCH_REFERERS = [
    "https://www.google.com/search?q={query}&sourceid=chrome&ie=UTF-8",
    "https://www.google.com/search?q={query}",
    "https://www.bing.com/search?q={query}&form=QBLH",
    "https://duckduckgo.com/?q={query}&t=h_&ia=web",
    "https://search.yahoo.com/search?p={query}",
    "https://www.google.com/search?q={query}&oq={query}&gs_lcrp=",
]

# Social media referers
_SOCIAL_REFERERS = [
    "https://www.facebook.com/",
    "https://www.reddit.com/",
    "https://www.reddit.com/r/all/",
    "https://twitter.com/",
    "https://x.com/",
    "https://news.ycombinator.com/",
    "https://www.linkedin.com/feed/",
    "https://t.co/redirect",
    "https://www.pinterest.com/",
    "https://www.threads.net/",
]


def _build_search_query(rng: random.Random, target_url: str) -> str:
    """Construit une requete de recherche plausible a partir du domaine cible."""
    host = urlsplit(target_url).hostname or ""
    # 50% : mots aleatoires, 50% : inclut le nom de domaine
    if rng.random() < 0.5 and host:
        domain_word = host.split(".")[0]
        extra = rng.sample(SEARCH_WORDS, min(2, len(SEARCH_WORDS)))
        return quote_plus(f"{domain_word} {' '.join(extra)}")
    n = rng.randint(2, 4)
    words = rng.sample(SEARCH_WORDS, min(n, len(SEARCH_WORDS)))
    return quote_plus(" ".join(words))


def pick_origin_referer(rng: random.Random, target_url: str) -> Optional[str]:
    """Choisit un referer initial pour une visite root URL.

    Distribution :
      40% search engine (Google/Bing/DDG avec query)
      30% direct (None — pas de referer)
      20% social media (Facebook/Reddit/Twitter)
      10% cross-site (autre domaine aleatoire)
    """
    roll = rng.random()

    if roll < 0.40:
        # Search engine avec query plausible
        query = _build_search_query(rng, target_url)
        template = rng.choice(_SEARCH_REFERERS)
        return template.format(query=query)

    if roll < 0.70:
        # Direct navigation — pas de referer
        return None

    if roll < 0.90:
        # Social media
        return rng.choice(_SOCIAL_REFERERS)

    # Cross-site (10%) — utilise le domaine cible avec prefixe blog/news
    host = urlsplit(target_url).hostname or "example.com"
    prefixes = ["blog.", "news.", "www.", "info.", "wiki."]
    return f"https://{rng.choice(prefixes)}{host}/"

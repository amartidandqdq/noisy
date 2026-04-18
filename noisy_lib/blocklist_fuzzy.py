# blocklist_fuzzy.py - Index "stem" pour catch les variants hostname
# IN: set blocklist | OUT: index frozen | MODIFIE: rien
# APPELE PAR: noisy.py au demarrage | APPELLE: rien

# Variants type: grandpashabet1.com, grandpashabet42.com, grandpashabet9000.com
# Si >=3 variants partagent le meme stem alphabetique + TLD, on indexe le stem.
# Lookup: hostname -> strip digits trailing -> stem in index -> BLOCK.

import re
from collections import defaultdict
from typing import FrozenSet, Set, Tuple

# Securite: stem >= 8 chars (pas "ad", "shop") et stem doit contenir au moins 1 lettre.
MIN_STEM_LEN = 8
MIN_VARIANTS = 3
# Limites pour eviter explosion memoire
MAX_DOMAIN_LEN = 80

_STEM_RE = re.compile(r"^([a-z]+?)\d+$")


def _stem_of(label: str) -> str:
    """Extrait le stem alphabetique avant les digits trailing.
    'grandpashabet7092' -> 'grandpashabet'. 'foo' -> 'foo'. 'bar2bar' -> 'bar2bar' (pas que digits)."""
    m = _STEM_RE.match(label)
    return m.group(1) if m else label


def build_stem_index(blocklist: Set[str]) -> FrozenSet[Tuple[str, str]]:
    """Scan la blocklist, regroupe par (stem, tld), garde ceux avec >=MIN_VARIANTS."""
    counts: dict = defaultdict(int)
    for domain in blocklist:
        if not domain or len(domain) > MAX_DOMAIN_LEN or "." not in domain:
            continue
        # Split off TLD (just the last label; subdomains rare in pure blocklists)
        parts = domain.rsplit(".", 1)
        if len(parts) != 2:
            continue
        label, tld = parts
        # Only consider labels matching <letters><digits> pattern
        m = _STEM_RE.match(label)
        if not m:
            continue
        stem = m.group(1)
        if len(stem) < MIN_STEM_LEN:
            continue
        counts[(stem, tld)] += 1
    return frozenset((s, t) for (s, t), c in counts.items() if c >= MIN_VARIANTS)


def host_matches_stem(host: str, index: FrozenSet[Tuple[str, str]]) -> bool:
    """True si l'hostname (sans subdomain) matche un stem indexe.

    Verifie le label registrable (avant TLD) ET les labels parents intermediaires.
    Ex: 'cdn.grandpashabet7092.com' -> teste 'cdn.grandpashabet7092' puis 'grandpashabet7092'.
    """
    if not host or not index:
        return False
    parts = host.split(".")
    if len(parts) < 2:
        return False
    tld = parts[-1]
    # Try each label before the TLD as the registrable label
    for i in range(len(parts) - 1):
        label = parts[i]
        stem = _stem_of(label)
        if len(stem) >= MIN_STEM_LEN and (stem, tld) in index:
            return True
    return False


# Module-level cache: id(blocklist) -> frozenset (avoid rebuilding per crawler)
_INDEX_CACHE: dict = {}


def build_stem_index_cached(blocklist):
    """Build stem index once per unique blocklist object (by id)."""
    key = id(blocklist)
    cached = _INDEX_CACHE.get(key)
    if cached is not None:
        return cached
    idx = build_stem_index(blocklist)
    _INDEX_CACHE[key] = idx
    return idx

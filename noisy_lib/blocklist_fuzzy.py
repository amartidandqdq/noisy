# blocklist_fuzzy.py - Index "stem" + "label/TLD" pour catch les variants hostname
# IN: set blocklist | OUT: index frozen | MODIFIE: rien
# APPELE PAR: noisy.py au demarrage | APPELLE: rien

# Pattern 1 (numeric): grandpashabet1.com, grandpashabet42.com, grandpashabet9000.com
#   >=3 variants partagent stem alphabetique + TLD -> index stem.
# Pattern 2 (TLD spray): themoviesflix.com, themoviesflix.net, themoviesflix.cc, themoviesflix.llc
#   meme label sur >=3 TLDs distincts -> index label.

import re
from collections import defaultdict
from typing import FrozenSet, Set, Tuple

# Securite: stem >= 8 chars (pas "ad", "shop") et stem doit contenir au moins 1 lettre.
MIN_STEM_LEN = 8
MIN_VARIANTS = 3
# Label index plus strict: 10 chars min, 3 TLDs distincts pour reduire faux-positifs
MIN_LABEL_LEN = 10
MIN_TLD_VARIANTS = 3
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


def build_label_tld_index(blocklist: Set[str]) -> FrozenSet[str]:
    """Index labels qui apparaissent sur >=MIN_TLD_VARIANTS TLDs distincts.

    Catch variants type 'themoviesflix.{com,net,cc,llc}'. Le label seul (pas la combo
    label+TLD) est indexe -> n'importe quel TLD nouveau matche.
    """
    tlds_by_label: dict = defaultdict(set)
    for domain in blocklist:
        if not domain or len(domain) > MAX_DOMAIN_LEN or "." not in domain:
            continue
        parts = domain.rsplit(".", 1)
        if len(parts) != 2:
            continue
        label, tld = parts
        # Sous-domaines (cdn.foo.com): garder seulement le dernier label avant TLD
        if "." in label:
            label = label.rsplit(".", 1)[1]
        if len(label) < MIN_LABEL_LEN:
            continue
        if not any(c.isalpha() for c in label):
            continue
        tlds_by_label[label].add(tld)
    return frozenset(lbl for lbl, tlds in tlds_by_label.items() if len(tlds) >= MIN_TLD_VARIANTS)


def host_matches_label(host: str, index: FrozenSet[str]) -> bool:
    """True si le label registrable du host apparait dans l'index."""
    if not host or not index:
        return False
    parts = host.split(".")
    if len(parts) < 2:
        return False
    label = parts[-2]
    return len(label) >= MIN_LABEL_LEN and label in index


# Module-level cache: id(blocklist) -> {"stem": frozenset, "label": frozenset}
_INDEX_CACHE: dict = {}


def build_stem_index_cached(blocklist):
    """Build stem index once per unique blocklist object (by id). [legacy entry]"""
    cached = _build_indexes_cached(blocklist)
    return cached["stem"]


def _build_indexes_cached(blocklist) -> dict:
    """Build both indexes (stem + label) once per blocklist."""
    key = id(blocklist)
    cached = _INDEX_CACHE.get(key)
    if cached is not None:
        return cached
    idxs = {
        "stem": build_stem_index(blocklist),
        "label": build_label_tld_index(blocklist),
    }
    _INDEX_CACHE[key] = idxs
    return idxs


def host_matches_any(host: str, indexes: dict) -> bool:
    """True si host matche stem OU label index. Retourne aussi le pattern via cle."""
    if not indexes:
        return False
    if host_matches_stem(host, indexes.get("stem", frozenset())):
        return True
    if host_matches_label(host, indexes.get("label", frozenset())):
        return True
    return False

# noisy_lib - modular internals for the noisy crawler


def extract_tld(url: str) -> str:
    """Extrait le TLD d'une URL (ex: 'https://bbc.co.uk' → 'uk')."""
    from urllib.parse import urlsplit
    host = urlsplit(url).hostname or ""
    return host.rsplit(".", 1)[-1] if "." in host else ""


def host_in_blocklist(url: str, blocklist: set) -> bool:
    """Vérifie si le hostname ou un parent est dans la blocklist."""
    from urllib.parse import urlsplit
    host = urlsplit(url).hostname or ""
    parts = host.split(".")
    for i in range(len(parts)):
        if ".".join(parts[i:]) in blocklist:
            return True
    return False

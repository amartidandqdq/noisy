# noisy_lib - modular internals for the noisy crawler


def host_in_blocklist(url: str, blocklist: set) -> bool:
    """Vérifie si le hostname ou un parent est dans la blocklist."""
    from urllib.parse import urlsplit
    host = urlsplit(url).hostname or ""
    parts = host.split(".")
    for i in range(len(parts)):
        if ".".join(parts[i:]) in blocklist:
            return True
    return False

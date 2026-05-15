from urllib.parse import urlparse, urlunparse

MAX_URL_LENGTH = 2048

BLOCKED_DOMAINS = {
    "evil.com",
    "malware.example.com",
    "phishing.example.com",
}


def validate_url(url: str) -> str:
    """Validate format, normalize, and check blocklist. Returns normalized URL."""
    if len(url) > MAX_URL_LENGTH:
        raise ValueError(f"URL exceeds maximum length of {MAX_URL_LENGTH}")

    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Invalid URL scheme '{parsed.scheme}': only http/https allowed")

    hostname = parsed.hostname
    if hostname is None:
        raise ValueError("URL is missing a hostname")

    if hostname.lower() in BLOCKED_DOMAINS:
        raise ValueError(f"Domain '{hostname}' is blocked")

    # Normalize: upgrade to https, lowercase hostname, strip trailing slash from path
    normalized_path = parsed.path.rstrip("/") or ""
    normalized = urlunparse((
        "https",
        hostname.lower() + (f":{parsed.port}" if parsed.port else ""),
        normalized_path,
        parsed.params,
        parsed.query,
        parsed.fragment,
    ))

    return normalized

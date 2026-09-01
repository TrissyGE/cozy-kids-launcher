"""Exact-origin boundaries for embedded browser tiles."""

import ipaddress
import re
from urllib.parse import urlsplit


MAX_BROWSER_ALLOWED_ORIGINS = 20
MAX_WEB_URL_LENGTH = 2048
_DNS_NAME = re.compile(r"[A-Za-z0-9.-]+")


def web_origin(value):
    """Return a canonical HTTP(S) origin or reject an unsafe web URL."""
    if not isinstance(value, str) or not value or len(value) > MAX_WEB_URL_LENGTH:
        raise ValueError("Invalid browser URL")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid browser URL") from exc
    if (
        parsed.scheme.lower() not in ("http", "https")
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("Invalid browser URL")

    raw_host = parsed.hostname
    try:
        host = raw_host.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("Invalid browser URL") from exc
    if ":" in host:
        try:
            ipaddress.IPv6Address(host)
        except ValueError as exc:
            raise ValueError("Invalid browser URL") from exc
        authority = f"[{host}]"
    else:
        if not _DNS_NAME.fullmatch(host) or ".." in host or host.startswith(".") or host.endswith("."):
            raise ValueError("Invalid browser URL")
        authority = host

    scheme = parsed.scheme.lower()
    if port is not None and not (
        (scheme == "http" and port == 80)
        or (scheme == "https" and port == 443)
    ):
        authority += f":{port}"
    return f"{scheme}://{authority}"


def is_safe_web_url(value):
    try:
        web_origin(value)
    except ValueError:
        return False
    return True


def normalize_browser_allowed_origins(values):
    """Validate, canonicalize, and deduplicate optional extra origins."""
    if values is None:
        return []
    if not isinstance(values, list) or len(values) > MAX_BROWSER_ALLOWED_ORIGINS:
        raise ValueError(
            f"browserAllowedOrigins must contain at most {MAX_BROWSER_ALLOWED_ORIGINS} entries"
        )
    result = []
    for value in values:
        try:
            origin = web_origin(value)
        except ValueError as exc:
            raise ValueError("browserAllowedOrigins contains an invalid web origin") from exc
        if origin not in result:
            result.append(origin)
    return result


def allowed_frame_origins(tile, start_url):
    """Return the start origin followed by explicitly configured extra origins."""
    result = [web_origin(start_url)]
    for origin in normalize_browser_allowed_origins(
        tile.get("browserAllowedOrigins", []) if isinstance(tile, dict) else []
    ):
        if origin not in result:
            result.append(origin)
    return result


def embedded_browser_csp(origins):
    """Build the wrapper CSP from already validated exact origins."""
    frame_sources = " ".join(origins)
    return (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        f"frame-src {frame_sources}; "
        "connect-src 'self'; img-src 'self' data:; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'"
    )

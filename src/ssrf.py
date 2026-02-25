"""Centralized SSRF validation for all URL-accepting endpoints.

Uses Python's ipaddress module for proper IP range checking instead
of fragile startswith() string matching.
"""
from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

# Hostnames that always resolve to loopback/internal
_BLOCKED_HOSTNAMES = frozenset({
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
})


def _is_blocked_ip(hostname: str) -> bool:
    """Check if a hostname is an IP address pointing to a blocked range."""
    # Strip IPv6 brackets
    clean = hostname.strip("[]")
    try:
        addr = ipaddress.ip_address(clean)
    except ValueError:
        return False

    return (
        addr.is_private        # RFC1918 (10/8, 172.16/12, 192.168/16) + IPv6 fc00::/7
        or addr.is_loopback    # 127.0.0.0/8, ::1
        or addr.is_link_local  # 169.254.0.0/16, fe80::/10
        or addr.is_multicast   # 224.0.0.0/4, ff00::/8
        or addr.is_reserved    # other IANA reserved
        or addr.is_unspecified  # 0.0.0.0, ::
        or _in_cgnat(addr)     # 100.64.0.0/10 (carrier-grade NAT)
    )


def _in_cgnat(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check if address falls in CGNAT range (100.64.0.0/10)."""
    if isinstance(addr, ipaddress.IPv4Address):
        return addr in ipaddress.IPv4Network("100.64.0.0/10")
    return False


def validate_url(url: str, *, field_name: str = "url") -> str:
    """Validate a URL is not pointing to internal/private addresses.

    Args:
        url: The URL to validate.
        field_name: Name of the field for error messages.

    Returns:
        The validated URL string.

    Raises:
        ValueError: If the URL points to an internal address or has
            an invalid scheme.
    """
    if not url.startswith(("https://", "http://")):
        raise ValueError(f"{field_name} must use http:// or https:// scheme")

    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()

    if not hostname:
        raise ValueError(f"{field_name} must contain a valid hostname")

    # Check blocked hostnames
    if hostname in _BLOCKED_HOSTNAMES:
        raise ValueError(f"{field_name} cannot point to internal addresses")

    # Check if hostname is an IP in a blocked range
    if _is_blocked_ip(hostname):
        raise ValueError(f"{field_name} cannot point to internal addresses")

    return url


def validate_url_https(url: str, *, field_name: str = "url") -> str:
    """Like validate_url but requires https:// scheme."""
    if not url.startswith("https://"):
        raise ValueError(f"{field_name} must use https:// scheme")

    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()

    if not hostname:
        raise ValueError(f"{field_name} must contain a valid hostname")

    if hostname in _BLOCKED_HOSTNAMES:
        raise ValueError(f"{field_name} cannot point to internal addresses")

    if _is_blocked_ip(hostname):
        raise ValueError(f"{field_name} cannot point to internal addresses")

    return url


def validate_url_optional(
    url: str | None, *, field_name: str = "url",
) -> str | None:
    """Validate URL if present, pass through None."""
    if url is None:
        return None
    return validate_url(url, field_name=field_name)


def validate_url_https_optional(
    url: str | None, *, field_name: str = "url",
) -> str | None:
    """Validate HTTPS URL if present, pass through None."""
    if url is None:
        return None
    return validate_url_https(url, field_name=field_name)

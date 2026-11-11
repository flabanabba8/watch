"""Public HTTPS destination validation for stream metadata."""
import ipaddress
import socket
from urllib.parse import urlsplit


def public_url(url):
    if not isinstance(url, str) or len(url) > 8192 or any(ord(c) < 32 for c in url):
        raise ValueError('Invalid provider URL')
    p = urlsplit(url)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.fragment or p.port not in (None, 443):
        raise ValueError('Provider URLs must use public HTTPS without credentials')
    addresses = socket.getaddrinfo(p.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Private or reserved provider destination refused')
    return p


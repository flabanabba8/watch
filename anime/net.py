"""Bounded public HTTPS fetches for the pinned ani-cli provider adapter."""
import http.client
import ipaddress
import socket
import sys
from urllib.parse import urljoin, urlsplit

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'


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


def fetch(url, referer=None):
    for _ in range(5):
        p = public_url(url)
        conn = http.client.HTTPSConnection(p.hostname, 443, timeout=12)
        try:
            conn.connect()
            if not ipaddress.ip_address(conn.sock.getpeername()[0]).is_global:
                raise ValueError('Provider connected to a non-public destination')
            headers = {'User-Agent': USER_AGENT, 'Accept': '*/*'}
            if referer:
                public_url(referer)
                headers['Referer'] = referer
            conn.request('GET', p.path + ('?' + p.query if p.query else ''), headers=headers)
            response = conn.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader('Location')
                if not location:
                    raise ValueError('Provider redirect has no destination')
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise ValueError(f'Provider returned HTTP {response.status}; retry later')
            data = response.read(4 * 1024 * 1024 + 1)
            if len(data) > 4 * 1024 * 1024:
                raise ValueError('Provider response exceeded 4 MiB')
            return data.decode('utf-8', errors='replace')
        finally:
            conn.close()
    raise ValueError('Too many provider redirects')


if __name__ == '__main__':
    try:
        args = sys.argv[1:]
        if len(args) not in (1, 3) or (len(args) == 3 and args[1] != '-e'):
            raise ValueError('Invalid provider request arguments')
        print(fetch(args[0], args[2] if len(args) == 3 else None))
    except Exception as exc:
        # Do not include signed URLs or HTTP bodies in diagnostics.
        print(str(exc) if isinstance(exc, ValueError) else 'Provider connection failed (' + type(exc).__name__ + ')', file=sys.stderr)
        sys.exit(1)

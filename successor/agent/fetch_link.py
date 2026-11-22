"""follow_link: fetch one announcement the notice links, behind an allow-list and an SSRF guard.

- the URL must appear verbatim in the notice text;
- https only; the host must be in CMC's own urls (website, announcement, technical_doc, message_board) for
  the coin or a coin the notice links on coinmarketcap.com, or a fixed publishing host;
- x.com / twitter.com / t.me / discord are always refused (they need a logged-in JS session);
- every DNS answer must be public (no private, loopback, link-local, reserved or multicast address);
- at most 3 redirects, each re-checked; 1 MB cap; 8 s timeout; HTML is reduced to text without running JS.
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import re
import socket
import time
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

FIXED_HOSTS = ("medium.com", "mirror.xyz", "substack.com", "gitbook.io", "github.com")
REFUSED = ("x.com", "twitter.com", "t.me", "discord.gg", "discord.com", "discordapp.com")
URL_CATEGORIES = ("website", "announcement", "technical_doc", "message_board", "explorer")
# hosts where the registrable domain is shared by unrelated owners: keep the full host, never widen
SHARED_SUFFIXES = (
    "github.io",
    "gitbook.io",
    "medium.com",
    "substack.com",
    "vercel.app",
    "netlify.app",
    "pages.dev",
    "notion.site",
    "blogspot.com",
    "wordpress.com",
    "co.uk",
    "com.au",
    "co.jp",
    "com.br",
    "co.kr",
)
# explorer hosts that serve every token: allowed as listed, never widened to their whole domain
GENERIC_EXPLORERS = (
    "etherscan.io",
    "bscscan.com",
    "solscan.io",
    "oklink.com",
    "mintscan.io",
    "polygonscan.com",
)


def registrable(host: str) -> str:
    """Project domain for allow-listing: blog.fetch.ai and explore-fetchhub.fetch.ai both give fetch.ai."""
    host = host.lower().rstrip(".")
    if any(host == s or host.endswith("." + s) for s in SHARED_SUFFIXES + GENERIC_EXPLORERS):
        return host
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) > 2 else host


MAX_BYTES = 1_000_000
TIMEOUT = 8.0
UA = "Mozilla/5.0 (compatible; SuccessorBot/0.1; reads CMC-linked migration announcements)"


class LinkRefused(Exception):
    pass


def _host_ok(host: str, allowed: set[str]) -> bool:
    host = host.lower().rstrip(".")
    if any(host == r or host.endswith("." + r) for r in REFUSED):
        return False
    if any(host == f or host.endswith("." + f) for f in FIXED_HOSTS):
        return True
    return any(host == a or host.endswith("." + a) for a in allowed)


def allowed_hosts(info_rows: list[dict]) -> set[str]:
    hosts: set[str] = set()
    for row in info_rows:
        for cat in URL_CATEGORIES:
            for u in (row.get("urls") or {}).get(cat) or []:
                h = (urlparse(u).hostname or "").lower().removeprefix("www.")
                generic = any(h == g or h.endswith("." + g) for g in GENERIC_EXPLORERS)
                if h and not (cat == "explorer" and generic):
                    hosts.add(registrable(h))
    return {h for h in hosts if not any(h == r or h.endswith("." + r) for r in REFUSED)}


def notice_urls(notice: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"https?://[^\s)\]\"'<>]+", notice or "")))


def check_url(url: str, notice: str, allowed: set[str], *, in_notice: bool = True) -> str:
    """Returns the host or raises LinkRefused with the reason shown in the trace."""
    if in_notice and url not in notice:
        raise LinkRefused("URL is not in the notice text")
    p = urlparse(url)
    if p.scheme != "https":
        raise LinkRefused("https only")
    host = (p.hostname or "").lower()
    if not host or not _host_ok(host, allowed):
        raise LinkRefused(f"host {host or '?'} is not on the allow-list")
    return host


async def _public_dns(host: str) -> None:
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise LinkRefused(f"DNS failed for {host}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise LinkRefused(f"{host} resolves to a non-public address")


class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.depth += 1
        elif tag in ("p", "br", "li", "h1", "h2", "h3", "h4", "tr", "div"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if not self.depth:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    p = _Text()
    p.feed(html)
    text = unescape("".join(p.parts))
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", text)).strip()


async def follow_link(url: str, notice: str, allowed: set[str]) -> dict:
    """Returns {url, final_url, host, http_status, text, sha256, fetched_at, latency_ms} or raises LinkRefused."""
    check_url(url, notice, allowed)
    t0 = time.perf_counter()
    current = url
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False, headers={"User-Agent": UA}) as c:
        for _hop in range(4):
            host = check_url(current, notice, allowed, in_notice=False)
            await _public_dns(host)
            async with c.stream("GET", current) as r:
                if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                    current = urljoin(current, r.headers["location"])
                    continue
                if r.status_code != 200:
                    raise LinkRefused(f"HTTP {r.status_code} from {host}")
                body = b""
                async for chunk in r.aiter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES:
                        body = body[:MAX_BYTES]
                        break
                ctype = r.headers.get("content-type", "")
                break
        else:
            raise LinkRefused("more than 3 redirects")
    raw = body.decode("utf-8", errors="replace")
    text = html_to_text(raw) if "html" in ctype or raw.lstrip()[:1] == "<" else raw
    return {
        "url": url,
        "final_url": current,
        "host": host,
        "http_status": 200,
        "text": text,
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "latency_ms": round((time.perf_counter() - t0) * 1000),
    }

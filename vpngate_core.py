"""Core VPN Gate API client (stdlib only).

Endpoint: http://www.vpngate.net/api/iphone/
Format:
    line 1: *vpn_servers
    line 2: #HostName,IP,Score,Ping,Speed,CountryLong,CountryShort,
            NumVpnSessions,Uptime,TotalUsers,TotalTraffic,LogType,
            Operator,Message,OpenVPN_ConfigData_Base64
    lines 3+: one server per CSV row.
Credentials for all public servers: vpn / vpn.
"""

from __future__ import annotations

import csv
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

API_URL = "http://www.vpngate.net/api/iphone/"
CACHE_DIR = Path.home() / ".cache" / "vpn-gate"
CACHE_FILE = CACHE_DIR / "servers.csv"
CACHE_MAX_AGE = 6 * 3600  # seconds


def _to_int(value: str, default: int = 0) -> int:
    try:
        return int(str(value).strip() or default)
    except (ValueError, TypeError):
        return default


@dataclass
class Server:
    host: str
    ip: str
    score: int
    ping_ms: int
    speed_bps: int
    country_long: str
    country_short: str
    sessions: int
    uptime: int
    total_users: int
    total_traffic: int
    log_type: str
    operator: str
    message: str
    config_b64: str

    @property
    def speed_mbps(self) -> float:
        return self.speed_bps / 1_000_000.0

    @property
    def country_label(self) -> str:
        if self.country_long and self.country_short:
            return f"{self.country_long} ({self.country_short})"
        return self.country_long or self.country_short or "-"

    @property
    def ddns(self) -> str:
        h = self.host.strip()
        if not h:
            return ""
        if "." in h:
            return h
        return f"{h}.opengw.net"


def fetch_csv(timeout: int = 25) -> str:
    req = urllib.request.Request(
        API_URL,
        headers={"User-Agent": "vpn-gate-client/1.0 (+linux; python)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


def parse_csv(text: str) -> list[Server]:
    lines = text.splitlines()
    # Drop the "*vpn_servers" marker line(s) and blank lines.
    rows = [ln for ln in lines if ln and not ln.startswith("*")]
    if not rows:
        return []
    # First remaining line is the header, prefixed with '#'.
    if rows[0].startswith("#"):
        rows[0] = rows[0][1:]
    reader = csv.DictReader(rows)
    servers: list[Server] = []
    for r in reader:
        try:
            config_b64 = (r.get("OpenVPN_ConfigData_Base64") or "").strip()
            if not config_b64:
                continue
            servers.append(
                Server(
                    host=(r.get("HostName") or "").strip(),
                    ip=(r.get("IP") or "").strip(),
                    score=_to_int(r.get("Score", 0)),
                    ping_ms=_to_int(r.get("Ping", -1), -1),
                    speed_bps=_to_int(r.get("Speed", 0)),
                    country_long=(r.get("CountryLong") or "").strip(),
                    country_short=(r.get("CountryShort") or "").strip(),
                    sessions=_to_int(r.get("NumVpnSessions", 0)),
                    uptime=_to_int(r.get("Uptime", 0)),
                    total_users=_to_int(r.get("TotalUsers", 0)),
                    total_traffic=_to_int(r.get("TotalTraffic", 0)),
                    log_type=(r.get("LogType") or "").strip(),
                    operator=(r.get("Operator") or "").strip(),
                    message=(r.get("Message") or "").strip(),
                    config_b64=config_b64,
                )
            )
        except Exception:
            continue
    return servers


def save_cache(text: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(text, encoding="utf-8")


def load_cache_max_age() -> float:
    try:
        return time.time() - CACHE_FILE.stat().st_mtime
    except OSError:
        return float("inf")


def load(force_refresh: bool = False, timeout: int = 25) -> list[Server]:
    """Load server list, using cache unless stale/forced."""
    if not force_refresh and CACHE_FILE.exists():
        if load_cache_max_age() < CACHE_MAX_AGE:
            try:
                return parse_csv(CACHE_FILE.read_text(encoding="utf-8"))
            except OSError:
                pass
    text = fetch_csv(timeout=timeout)
    try:
        save_cache(text)
    except OSError:
        pass
    return parse_csv(text)


def filter_servers(servers: list[Server], query: str) -> list[Server]:
    q = query.strip().lower()
    if not q:
        return list(servers)
    out = []
    for s in servers:
        hay = f"{s.country_long} {s.country_short} {s.host} {s.ip} {s.operator}".lower()
        if q in hay:
            out.append(s)
    return out


def sort_servers(servers: list[Server], key: str = "score", reverse: bool = True) -> list[Server]:
    keymap = {
        "score": lambda s: s.score,
        "ping": lambda s: (s.ping_ms if s.ping_ms >= 0 else 10**9),
        "speed": lambda s: s.speed_bps,
        "sessions": lambda s: s.sessions,
        "country": lambda s: (s.country_long.lower(), -s.score),
    }
    fn = keymap.get(key, keymap["score"])
    rev = reverse if key != "ping" else not reverse if key == "ping" and reverse else False
    # ping: ascending by default; others descending.
    if key == "ping":
        return sorted(servers, key=fn, reverse=False)
    return sorted(servers, key=fn, reverse=rev)


def countries(servers: list[Server]) -> list[str]:
    seen: dict[str, str] = {}
    for s in servers:
        if s.country_short and s.country_short not in seen:
            seen[s.country_short] = s.country_long
    return sorted(seen.keys())

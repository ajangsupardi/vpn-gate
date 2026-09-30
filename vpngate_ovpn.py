"""Decode + patch VPN Gate OpenVPN configs for modern clients.

Problem: VPN Gate servers use legacy ``cipher AES-128-CBC`` / ``auth SHA1``.
OpenVPN 2.6 defaults to GCM-only negotiation and NetworkManager-openvpn
1.10 on Ubuntu 24.04 does not forward data-ciphers unless set explicitly,
so connections fail without patching (Launchpad #2071366).
Fix: force the legacy cipher on both the .ovpn text AND via nmcli
(vpn.py companion module tries vpn.data-ciphers; failures are ignored).
"""

from __future__ import annotations

import base64
from pathlib import Path

from vpngate_core import CACHE_DIR, Server

OVPN_DIR = CACHE_DIR / "profiles"
AUTH_USER = "vpn"
AUTH_PASS = "vpn"

FORCE_DIRECTIVES = [
    "cipher AES-128-CBC",
    "data-ciphers AES-128-CBC",
    "data-ciphers-fallback AES-128-CBC",
    "auth SHA1",
]

# IPv6 leak protection: VPN Gate tunnels are IPv4-only, so any IPv6 route
# pushed by the server must be ignored — otherwise IPv6 traffic bypasses
# the tunnel via the physical interface.
PULL_FILTER_DIRECTIVES = [
    'pull-filter ignore "route-ipv6"',
    'pull-filter ignore "ifconfig-ipv6"',
]


def decode_config(b64: str) -> str:
    return base64.b64decode(b64.strip()).decode("utf-8", errors="replace")


def _is_droppable(line: str) -> bool:
    s = line.strip().lower()
    if s.startswith("cipher ") or s.startswith("data-ciphers ") or s.startswith("data-ciphers-fallback "):
        return True
    if s == "auth sha1" or s.startswith("auth sha1 ") or s.startswith("auth sha ") and "user" not in s:
        # drop plain 'auth <algo>' lines; keep auth-user-pass / auth-nocache / auth-retry
        return True
    if s.startswith("auth ") and not any(
        s.startswith(p) for p in ("auth-user-pass", "auth-nocache", "auth-retry", "auth-token")
    ):
        return True
    return False


def patch_config(text: str, auth_file: str | None = None) -> str:
    lines = text.splitlines()
    kept = [ln for ln in lines if not _is_droppable(ln)]
    body = "\n".join(kept).rstrip() + "\n"

    # Ensure auth-user-pass points at our credentials file.
    if auth_file:
        body_lines = [ln for ln in body.splitlines() if not ln.strip().lower().startswith("auth-user-pass")]
        body = "\n".join(body_lines).rstrip() + "\n"
        body += f"auth-user-pass {auth_file}\n"
        if "auth-nocache" not in body:
            body += "auth-nocache\n"

    body += "\n# --- patched by vpn-gate-client for OpenVPN 2.6 / OpenSSL 3 ---\n"
    for d in FORCE_DIRECTIVES:
        body += d + "\n"
    body += "# --- IPv6 leak protection (tunnel is IPv4-only) ---\n"
    for d in PULL_FILTER_DIRECTIVES:
        if d not in body:
            body += d + "\n"
    return body


def write_profile(server: Server, dest_dir: Path | None = None) -> tuple[Path, Path]:
    """Write patched .ovpn + auth file (mode 0600). Returns (ovpn, auth)."""
    dest = Path(dest_dir) if dest_dir else OVPN_DIR
    dest.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in server.host) or "server"
    auth_path = dest / f"{safe}.auth.txt"
    ovpn_path = dest / f"{safe}.ovpn"
    auth_path.write_text(f"{AUTH_USER}\n{AUTH_PASS}\n", encoding="utf-8")
    try:
        auth_path.chmod(0o600)
    except OSError:
        pass
    raw = decode_config(server.config_b64)
    patched = patch_config(raw, auth_file=str(auth_path))
    ovpn_path.write_text(patched, encoding="utf-8")
    try:
        ovpn_path.chmod(0o600)
    except OSError:
        pass
    return ovpn_path, auth_path


def validate(text: str) -> list[str]:
    problems = []
    if "<ca>" not in text:
        problems.append("missing <ca> block")
    if "remote " not in text:
        problems.append("missing remote directive")
    if "data-ciphers-fallback AES-128-CBC" not in text:
        problems.append("missing legacy data-ciphers-fallback")
    if 'pull-filter ignore "route-ipv6"' not in text:
        problems.append("missing IPv6 pull-filter (leak risk)")
    return problems

"""NetworkManager wrapper via nmcli subprocess (no extra deps, PolicyKit auth).

Pattern proven by Me3paw/VPN-gate-client: import the patched .ovpn, then
modify vpn.data to inject legacy crypto + vpn/vpn credentials, then up.
"""

from __future__ import annotations

import re
import subprocess
import urllib.request
from pathlib import Path

CONN_PREFIX = "vpngate-"


def _run(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def sanitize(name: str) -> str:
    safe = "".join(c if (c.isalnum() or c in "-_") else "-" for c in name).strip("-")
    return (CONN_PREFIX + safe)[:60] or (CONN_PREFIX + "server")


def existing_uuids() -> set[str]:
    p = _run(["nmcli", "-t", "-f", "UUID", "connection", "show"])
    if p.returncode != 0:
        return set()
    return {ln.strip() for ln in p.stdout.splitlines() if ln.strip()}


def import_connection(ovpn_path: Path | str, conn_name: str, timeout: int = 30) -> str:
    """Import .ovpn, rename to conn_name. Returns connection id (name)."""
    before = existing_uuids()
    p = _run(["nmcli", "connection", "import", "type", "openvpn", "file", str(ovpn_path)], timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"nmcli import failed: {(p.stderr or p.stdout).strip()}")
    after = existing_uuids()
    new = after - before
    target = conn_name
    if new:
        uuid = sorted(new)[0]
        q = _run(["nmcli", "connection", "modify", uuid, "connection.id", conn_name], timeout=timeout)
        if q.returncode != 0:
            target = uuid  # fall back to uuid if rename fails
    # Legacy crypto + credentials. NOTE: vpn.data is a dict — entries MUST be
    # added with the '+' prefix. Without it, nmcli REPLACES the whole dict
    # with the single key (this silently dropped cipher/auth/data-ciphers
    # and caused "No valid secrets" on activation).
    # NOTE: 'data-ciphers-fallback' is deliberately NOT set here — the
    # installed network-manager-openvpn 1.10.2 plugin rejects it with
    # BadArguments "invalid or not supported" (it stays in the .ovpn text
    # only, where openvpn itself understands it).
    _run(["nmcli", "connection", "modify", target, "connection.autoconnect", "no"], timeout=timeout)
    mods = [
        "cipher=AES-128-CBC",
        "auth=SHA1",
        "data-ciphers=AES-128-CBC",
        "username=vpn",
        "password-flags=0",
    ]
    for kv in mods:
        p = _run(["nmcli", "connection", "modify", target, "+vpn.data", kv], timeout=timeout)
        if p.returncode != 0:
            raise RuntimeError(f"nmcli modify +vpn.data {kv} failed: {(p.stderr or p.stdout).strip()}")
    p = _run(["nmcli", "connection", "modify", target, "+vpn.secrets", "password=vpn"], timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"nmcli modify vpn.secrets failed: {(p.stderr or p.stdout).strip()}")
    # Verify the password really landed in the profile; otherwise 'up'
    # fails later with a cryptic "No valid secrets".
    p = _run(["nmcli", "-s", "-t", "-f", "vpn.secrets", "connection", "show", target], timeout=timeout)
    if "password" not in (p.stdout or ""):
        raise RuntimeError(
            "NetworkManager refused to store the VPN password in the profile "
            "(vpn.secrets empty after modify). Try: nmcli connection delete "
            f"{target}, then reconnect."
        )
    return target


def up(conn_id: str, timeout: int = 25) -> None:
    p = _run(["nmcli", "connection", "up", conn_id], timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"nmcli up failed: {(p.stderr or p.stdout).strip()[:500]}")


def down(conn_id: str, timeout: int = 15) -> None:
    _run(["nmcli", "connection", "down", conn_id], timeout=timeout)


def delete(conn_id: str, timeout: int = 15) -> None:
    _run(["nmcli", "connection", "delete", conn_id], timeout=timeout)


def disconnect_all(purge_files: bool = True) -> int:
    """Down+delete every vpngate-* profile (and by default its files)."""
    p = _run(["nmcli", "-t", "-f", "NAME", "connection", "show"])
    if p.returncode != 0:
        return 0
    n = 0
    for line in p.stdout.splitlines():
        name = line.strip()
        if name.startswith(CONN_PREFIX):
            forget_profile(name)
            n += 1
    if purge_files:
        profiles_dir = Path.home() / ".cache" / "vpn-gate" / "profiles"
        try:
            for fp in profiles_dir.glob("*"):
                if fp.suffix in (".ovpn", ".txt") and fp.is_file():
                    fp.unlink(missing_ok=True)
        except OSError:
            pass
    return n


def _vpn_data_dict(conn_id: str, timeout: int = 15) -> dict[str, str]:
    p = _run(["nmcli", "-t", "-f", "vpn.data", "connection", "show", conn_id], timeout=timeout)
    out: dict[str, str] = {}
    if p.returncode != 0:
        return out
    for chunk in (p.stdout or "").split(","):
        if "=" not in chunk:
            continue
        k, v = chunk.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def connection_cert_paths(conn_id: str, timeout: int = 15) -> list[Path]:
    """CA/cert/key files NM generated for this profile (under ~/.cert)."""
    base = Path.home() / ".cert" / "nm-openvpn"
    paths = []
    data = _vpn_data_dict(conn_id, timeout)
    for key in ("ca", "cert", "key"):
        fp = Path(data.get(key, ""))
        try:
            if fp.is_file() and str(fp).startswith(str(base)):
                paths.append(fp)
        except OSError:
            pass
    return paths


def connection_remote(conn_id: str, timeout: int = 15) -> tuple[str, str]:
    """(ip, port) of the profile's remote, e.g. ('219.100.37.102', '443')."""
    remote = _vpn_data_dict(conn_id, timeout).get("remote", "")
    if ":" in remote:
        ip, port = remote.rsplit(":", 1)
        return ip.strip(), port.strip()
    parts = remote.split()
    if len(parts) >= 2:
        return parts[0], parts[1]
    return "", ""


def cache_files_for_remote(ip: str, port: str) -> list[tuple[Path, Path | None]]:
    """Find our cached .ovpn (+sibling .auth.txt) containing this remote."""
    found = []
    if not ip:
        return found
    profiles_dir = Path.home() / ".cache" / "vpn-gate" / "profiles"
    try:
        ovpns = sorted(profiles_dir.glob("*.ovpn"))
    except OSError:
        return found
    for ovpn_path in ovpns:
        try:
            text = ovpn_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("remote ") and ip in s and (not port or port in s):
                auth = ovpn_path.with_suffix(".auth.txt")
                found.append((ovpn_path, auth if auth.is_file() else None))
                break
    return found


def forget_profile(conn_id: str, timeout: int = 15) -> str:
    """Fully remove a VPN Gate connection: down + delete profile + delete
    its generated cert files + cached .ovpn/.auth. Returns '' or a warning.
    """
    warns: list[str] = []
    certs = connection_cert_paths(conn_id, timeout)
    remote = connection_remote(conn_id, timeout)
    down(conn_id, timeout)
    _run(["nmcli", "connection", "delete", conn_id], timeout=timeout)
    # Verify it is really gone from NetworkManager.
    q = _run(["nmcli", "-t", "-f", "NAME", "connection", "show"], timeout=timeout)
    names = [ln.strip() for ln in (q.stdout or "").splitlines()]
    if conn_id in names:
        warns.append(f"profile {conn_id} still listed in NetworkManager")
    for fp in certs:
        try:
            fp.unlink(missing_ok=True)
        except OSError as e:
            warns.append(f"{fp.name}: {e}")
    for ovpn_path, auth_path in cache_files_for_remote(*remote):
        for fp in (ovpn_path, auth_path):
            if fp is None:
                continue
            try:
                fp.unlink(missing_ok=True)
            except OSError as e:
                warns.append(f"{fp.name}: {e}")
    return "; ".join(warns)


def sweep_orphans() -> int:
    """Delete every INACTIVE vpngate-* profile + its files. Active one kept."""
    p = _run(["nmcli", "-t", "-f", "NAME", "connection", "show", "--active"])
    active = {ln.strip() for ln in (p.stdout or "").splitlines()} if p.returncode == 0 else set()
    q = _run(["nmcli", "-t", "-f", "NAME", "connection", "show"])
    if q.returncode != 0:
        return 0
    n = 0
    for line in q.stdout.splitlines():
        name = line.strip()
        if name.startswith(CONN_PREFIX) and name not in active:
            forget_profile(name)
            n += 1
    purge_unowned_files(skip_active_certs=True)
    return n


def purge_unowned_files(skip_active_certs: bool = True) -> int:
    """Remove leftover .pem/.ovpn/.auth with no owning profile.

    The profiles dir is written solely by write_profile (transient files,
    recreated on every connect), so its contents are always safe to drop.
    Cert pems are dropped only when no vpngate-* profile references them —
    active connections are never touched.
    """
    profiles_dir = Path.home() / ".cache" / "vpn-gate" / "profiles"
    cert_dir = Path.home() / ".cert" / "nm-openvpn"
    n = 0
    try:
        ovpns = list(profiles_dir.glob("*.ovpn"))
    except OSError:
        ovpns = []
    stems = {p.stem for p in ovpns}
    # Collect cert paths still referenced by any vpngate-* profile.
    referenced: set[str] = set()
    q = _run(["nmcli", "-t", "-f", "NAME", "connection", "show"])
    if q.returncode == 0:
        for line in q.stdout.splitlines():
            name = line.strip()
            if name.startswith(CONN_PREFIX):
                for fp in connection_cert_paths(name):
                    referenced.add(fp.name)
    try:
        pems = list(cert_dir.glob("*.pem"))
    except OSError:
        pems = []
    for pem in pems:
        if pem.name in referenced:
            continue
        matched = any(
            pem.name in (f"{s}-ca.pem", f"{s}-cert.pem", f"{s}-key.pem") for s in stems
        )
        # Also drop vpngate-patterned pems with no cache stem left at all
        # (leftovers from before stem tracking), but NEVER other apps' files.
        orphan_pattern = (
            pem.name.startswith(("public-vpn-", "v-dot-pn-", "n26-"))
            or re.match(r"^vpn\d+-", pem.name) is not None
        )
        if matched or (orphan_pattern and pem.name not in referenced):
            try:
                pem.unlink(missing_ok=True)
                n += 1
            except OSError:
                pass
    for fp in profiles_dir.glob("*"):
        if fp.is_file() and fp.suffix in (".ovpn", ".txt"):
            try:
                fp.unlink(missing_ok=True)
                n += 1
            except OSError:
                pass
    return n


def active_vpngate() -> str | None:
    p = _run(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show", "--active"])
    if p.returncode != 0:
        return None
    for line in p.stdout.splitlines():
        if line.startswith(CONN_PREFIX):
            return line.split(":")[0]
    return None


_IPV4 = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def _looks_like_ip(text: str) -> bool:
    t = text.strip().split()[0] if text.strip() else ""
    if _IPV4.match(t):
        return all(0 <= int(p) <= 255 for p in t.split("."))
    # IPv6: hex + colons only, at least 2 colons.
    if t.count(":") >= 2 and re.fullmatch(r"[0-9a-fA-F:.]+", t or ""):
        return True
    return False


def get_public_ip(timeout: int = 10) -> str:
    for url in ("https://api.ipify.org", "https://api.ip.sb", "https://ifconfig.me"):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read().decode("utf-8", errors="replace").strip()
            if _looks_like_ip(body):
                return body.split()[0]
        except Exception:
            continue
    return "?"


def tunnel_ipv4(timeout: int = 10) -> str | None:
    """IPv4 address of an active tun/ppp interface (proof the tunnel is up)."""
    p = _run(["ip", "-o", "-4", "addr", "show"], timeout=timeout)
    if p.returncode != 0:
        return None
    import re as _re

    for line in (p.stdout or "").splitlines():
        m = _re.search(r"^\d+:\s+(tun\d+|ppp\d+)\s+inet\s+(\S+)", line)
        if m:
            return m.group(2).split("/")[0]
    return None


def get_public_ip_retry(timeout: int = 15, attempts: int = 3, delay: int = 5) -> str:
    """Public IP with retries — right after 'up', routes/DNS may need
    seconds to settle, so a single immediate check often fails."""
    import time as _time

    for i in range(attempts):
        ip = get_public_ip(timeout)
        if ip != "?":
            return ip
        if i < attempts - 1:
            _time.sleep(delay)
    return "?"

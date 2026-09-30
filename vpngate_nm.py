"""NetworkManager wrapper via nmcli subprocess (no extra deps, PolicyKit auth).

Pattern proven by Me3paw/VPN-gate-client: import the patched .ovpn, then
modify vpn.data to inject legacy crypto + vpn/vpn credentials, then up.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import urllib.request
from pathlib import Path

CONN_PREFIX = "vpngate-"

# IPv6 leak protection: VPN Gate tunnels are IPv4-only, so while a tunnel
# is up the kernel would still route IPv6 via the physical interface,
# bypassing the VPN entirely. We therefore disable IPv6 system-wide for
# the duration of the session and restore the previous state afterwards.
IPV6_SYSCTL_KEYS = (
    "net.ipv6.conf.all.disable_ipv6",
    "net.ipv6.conf.default.disable_ipv6",
)
# How long the polkit password dialog may stay open before we give up.
PKEXEC_TIMEOUT = 120

# Session memory: once the user cancels a privilege prompt, never nag again
# this session (each explicit CONNECT re-arms via reset_pkexec_decline).
_PKEXEC_DECLINED = False


def reset_pkexec_decline() -> None:
    """Re-arm privilege prompts (call on each explicit user retry)."""
    global _PKEXEC_DECLINED
    _PKEXEC_DECLINED = False


def decline_pkexec() -> None:
    """Remember a cancelled/dismissed prompt: no more dialogs this session."""
    global _PKEXEC_DECLINED
    _PKEXEC_DECLINED = True


class Cancelled(RuntimeError):
    """A cancellable operation was aborted via the CANCEL button."""


def _run(args: list[str], timeout: int = 30,
         cancel: threading.Event | None = None) -> subprocess.CompletedProcess:
    if cancel is None:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    # Cancellable: wait in slices so a CANCEL click kills the child within
    # ~0.2 s instead of hanging until `timeout`. Child output is small
    # (nmcli/sysctl one-liners), so plain wait() cannot deadlock here.
    import time as _time

    proc = subprocess.Popen(args, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    try:
        elapsed = 0.0
        step = 0.2
        while True:
            if cancel.is_set():
                proc.kill()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    pass
                raise Cancelled(f"cancelled: {' '.join(args[:4])}")
            try:
                proc.wait(timeout=step)
                break
            except subprocess.TimeoutExpired:
                pass
            elapsed += step
            if elapsed >= timeout:
                proc.kill()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    pass
                raise subprocess.TimeoutExpired(args, timeout)
        out, err = proc.communicate()
        return subprocess.CompletedProcess(args, proc.returncode, out, err)
    except BaseException:
        if proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass
        raise


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
    # IPv6 leak protection (layer 1/3): the tunnel is IPv4-only, so tell
    # NetworkManager the VPN profile has no IPv6 at all. Fail closed —
    # a profile without this is a leaking profile.
    p = _run(["nmcli", "connection", "modify", target, "ipv6.method", "disabled"], timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"nmcli modify ipv6.method failed: {(p.stderr or p.stdout).strip()}")
    # Private-key passphrase: VPN Gate ships unencrypted keys, yet NM pops
    # the desktop password dialog on EVERY connect unless told the secret
    # is not required (users then type 'vpn' into the wrong prompt and it
    # keeps coming back). Only set this when the real key proves to need
    # no passphrase; otherwise keep NM defaults so a truly encrypted key
    # still prompts. Best-effort: failure just means the old prompt stays.
    for fp in connection_cert_paths(target):
        if fp.name.endswith("-key.pem") and _key_is_unencrypted(fp) is True:
            _run(["nmcli", "connection", "modify", target, "+vpn.data",
                  "cert-pass-flags=4"], timeout=timeout)
            break
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


def up(conn_id: str, timeout: int = 25, cancel: threading.Event | None = None) -> None:
    p = _run(["nmcli", "connection", "up", conn_id], timeout=timeout, cancel=cancel)
    if p.returncode != 0:
        raise RuntimeError(f"nmcli up failed: {(p.stderr or p.stdout).strip()[:500]}")


def abort_on_auth_failed(conn_id: str, stop: threading.Event, poll: float = 1.0) -> bool:
    """Kill an activation as soon as the server rejects the login.

    When openvpn receives AUTH_FAILED, NetworkManager assumes the stored
    password is wrong and re-asks the desktop secret agent — in a loop the
    user can only escape by typing/cancelling. Since our credentials are
    always correct (vpn/vpn), AUTH_FAILED means a dead/full server, so the
    only right move is to abort immediately. Runs until `stop` is set;
    returns True if it killed the attempt. Only ever touches `conn_id`,
    so a stranger's AUTH_FAILED cannot harm another connection.
    """
    import datetime as _dt

    start = _dt.datetime.now().strftime("%H:%M:%S")
    while not stop.wait(poll):
        try:
            p = _run(
                ["journalctl", "--since", start, "-t", "nm-openvpn",
                 "-o", "cat", "--no-pager"],
                timeout=10,
            )
        except Exception:
            return False
        if p.returncode == 0 and "AUTH_FAILED" in (p.stdout or ""):
            down(conn_id)
            return True
    return False


def down(conn_id: str, timeout: int = 15) -> None:
    _run(["nmcli", "connection", "down", conn_id], timeout=timeout)


def delete(conn_id: str, timeout: int = 15) -> None:
    _run(["nmcli", "connection", "delete", conn_id], timeout=timeout)


def installer_path() -> Path:
    """One-time-setup script: next to this module (.deb) or under
    packaging/ (run-from-source)."""
    here = Path(__file__).resolve().parent
    for cand in (here / "setup-nopasswd-sudo.sh",
                 here / "packaging" / "setup-nopasswd-sudo.sh"):
        if cand.is_file():
            return cand
    return here / "setup-nopasswd-sudo.sh"


def ensure_passwordless(timeout: int = PKEXEC_TIMEOUT) -> bool:
    """One password prompt for permanent passwordless IPv6 control.

    Installs the scoped sudoers rule via a single polkit dialog, then
    verifies `sudo -n` works. Returns True when passwordless sysctl works
    (already did, or just installed). Never raises — False means the caller
    proceeds unprotected with an honest warning, never silence.
    """
    if not needs_password_prompt(timeout=10):
        return True
    # Explicit user consent (popup Continue) = fresh intent: re-arm.
    reset_pkexec_decline()
    src = installer_path()
    if not src.is_file():
        return False
    try:
        p = _run(["pkexec", str(src)], timeout=timeout)
    except Exception:
        decline_pkexec()
        return False
    if p.returncode != 0:
        # Cancelled/dismissed/failed: arm the session flag HERE, otherwise
        # disable_ipv6() falls back to one pkexec per sysctl key and the
        # user sees a 2nd (and 3rd) dialog for a single Cancel.
        decline_pkexec()
        return False
    return not needs_password_prompt(timeout=10)


def _ipv6_state_file() -> Path:
    return Path.home() / ".cache" / "vpn-gate" / "ipv6.json"


def _key_is_unencrypted(key_path: Path, timeout: int = 10) -> bool | None:
    """True if the PEM private key needs no passphrase.

    Returns None when inconclusive (openssl missing, unreadable/encrypted
    key) — callers must then keep NM defaults so the desktop still prompts
    instead of breaking the connection.
    """
    try:
        p = _run(
            ["openssl", "rsa", "-in", str(key_path), "-check", "-noout",
             "-passin", "pass:"],
            timeout=timeout,
        )
    except Exception:
        return None
    if p.returncode != 0:
        return None
    return True


def _sysctl_get(key: str, timeout: int = 10) -> str | None:
    try:
        p = _run(["sysctl", "-n", key], timeout=timeout)
    except Exception:
        return None
    if p.returncode != 0:
        return None
    return (p.stdout or "").strip()


def needs_password_prompt(timeout: int = 10) -> bool:
    """True if flipping IPv6 will pop a password dialog.

    Used by the GUI to show an explanatory popup first. Side-effect free:
    probes with a no-op write (same value) via passwordless sudo. Note we
    cannot trust a bare returncode here — sysctl -w exits 0 while printing
    'permission denied ... ignoring' as non-root — so stderr is checked too.
    """
    import os as _os

    if _os.geteuid() == 0:
        return False
    key = IPV6_SYSCTL_KEYS[0]
    cur = _sysctl_get(key, timeout)
    if cur is None:
        return True
    try:
        p = _run(["sudo", "-n", "sysctl", "-w", f"{key}={cur}"], timeout=timeout)
    except Exception:
        return True
    if p.returncode != 0:
        return True
    if "permission denied" in (p.stderr or ""):
        return True
    return False


def _sysctl_set(key: str, value: str, timeout: int = 10) -> bool:
    """Write one IPv6 sysctl, escalating to root only when needed.

    Fast path first (already root / under sudo). Otherwise fall back to
    ``pkexec`` so the desktop shows its system password dialog — once per
    session, since polkit caches the grant for a few minutes and the
    matching connect+disconnect pair normally falls inside that window.
    The app itself never sees or stores the password.
    """
    try:
        p = _run(["sysctl", "-w", f"{key}={value}"], timeout=timeout)
    except Exception:
        p = None
    # NOTE: sysctl -w may exit 0 while merely printing
    # 'permission denied ... ignoring' as non-root — trust only a read-back.
    if p is not None and p.returncode == 0 and _sysctl_get(key) == value:
        return True
    # Passwordless sudo (one-time setup via packaging/setup-nopasswd-sudo.sh):
    # never prompts — fails fast when the rule isn't installed yet.
    try:
        p = _run(["sudo", "-n", "sysctl", "-w", f"{key}={value}"], timeout=timeout)
    except Exception:
        p = None
    if p is not None and p.returncode == 0 and _sysctl_get(key) == value:
        return True
    # Not privileged: ask polkit — unless declined earlier this session.
    # Generous timeout — the user may need a minute to find the dialog
    # and type. Callers run this off the UI thread already
    # (connect/disconnect workers), so the GUI stays alive.
    # ANY pkexec failure (cancelled, dismissed, no agent) arms the session
    # flag: nagging twice more (once per sysctl key) is worse than an
    # honest warning.
    global _PKEXEC_DECLINED
    if _PKEXEC_DECLINED:
        return False
    sysctl_bin = shutil.which("sysctl") or "/usr/sbin/sysctl"
    try:
        p = _run(["pkexec", sysctl_bin, "-w", f"{key}={value}"], timeout=PKEXEC_TIMEOUT)
    except Exception:
        decline_pkexec()
        return False
    if p.returncode != 0:
        decline_pkexec()
        return False
    return True


def ipv6_summary() -> str:
    """One-word system IPv6 state for --status: disabled/enabled/unknown."""
    vals = [_sysctl_get(k) for k in IPV6_SYSCTL_KEYS]
    if any(v is None for v in vals):
        return "unknown"
    if all(v == "1" for v in vals):
        return "disabled"
    return "enabled"


def disable_ipv6() -> str:
    """Disable system IPv6 for the VPN session (layer 2/3).

    Saves the previous sysctl values to the state file so
    :func:`restore_ipv6` can put them back. Returns '' on success or a
    warning message (never raises) — callers must surface the warning
    because IPv6 may then leak outside the tunnel.
    """
    current: dict[str, str] = {}
    for key in IPV6_SYSCTL_KEYS:
        v = _sysctl_get(key)
        if v is None:
            return "could not read IPv6 sysctl state — IPv6 may leak outside the tunnel"
        current[key] = v
    if all(v == "1" for v in current.values()):
        return ""  # already disabled, nothing to save
    state_file = _ipv6_state_file()
    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(current), encoding="utf-8")
    except OSError as e:
        return f"could not save IPv6 state ({e}) — IPv6 left enabled, leak possible"
    failed = [k for k in IPV6_SYSCTL_KEYS if not _sysctl_set(k, "1")]
    if failed:
        # Nothing changed — drop the state file so a later restore does not
        # nag for something we never did.
        try:
            state_file.unlink(missing_ok=True)
        except OSError:
            pass
        # Deliberately key-free: this text reaches the status bar.
        return "IPv6 could not be disabled (permission not granted) — traffic may leak outside the tunnel"
    return ""


def restore_ipv6() -> str:
    """Restore pre-session IPv6 sysctl values. No-op if we never changed
    anything (no state file). Returns '' or a warning message."""
    state_file = _ipv6_state_file()
    try:
        raw = state_file.read_text(encoding="utf-8")
    except OSError:
        return ""
    try:
        saved = json.loads(raw)
    except ValueError:
        saved = {}
    failed = []
    for key in IPV6_SYSCTL_KEYS:
        orig = str(saved.get(key, "0"))
        if orig not in ("0", "1"):
            orig = "0"
        if not _sysctl_set(key, orig):
            failed.append(key)
    try:
        state_file.unlink(missing_ok=True)
    except OSError:
        pass
    if failed:
        return "IPv6 could not be restored — reboot to reset"
    return ""


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
    # Session over: put IPv6 back the way we found it — but only when no
    # other VPN Gate tunnel is still active (sweep/disconnect-all may
    # forget several profiles while one session keeps running).
    if active_vpngate() is None:
        rest = restore_ipv6()
        if rest:
            warns.append(rest)
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
    # Crash recovery: a previous session may have died with system IPv6
    # still disabled. Restore it — but only when no tunnel is active.
    if not any(nm.startswith(CONN_PREFIX) for nm in active):
        restore_ipv6()
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


def get_public_ip_retry(timeout: int = 15, attempts: int = 3, delay: int = 5,
                        cancel: threading.Event | None = None) -> str:
    """Public IP with retries — right after 'up', routes/DNS may need
    seconds to settle, so a single immediate check often fails."""
    import time as _time

    for i in range(attempts):
        if cancel is not None and cancel.is_set():
            raise Cancelled("cancelled during IP check")
        ip = get_public_ip(timeout)
        if ip != "?":
            return ip
        if i < attempts - 1:
            if cancel is None:
                _time.sleep(delay)
            else:
                end = _time.monotonic() + delay
                while _time.monotonic() < end:
                    if cancel.is_set():
                        raise Cancelled("cancelled during IP check")
                    _time.sleep(0.5)
    return "?"

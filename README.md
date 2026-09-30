<p align="center">
  <img src="data/io.github.ajangsupardi.vpngate.svg" width="96" alt="VPN Gate Client logo">
</p>

<h1 align="center">VPN Gate Client for Linux</h1>

<p align="center">
  <b>The missing Linux client for free VPN Gate servers — browse, connect, verify, clean up.</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-1.1--1-blue" alt="Version 1.1-1">
  <img src="https://img.shields.io/badge/python-3.12-blue?logo=python&logoColor=white" alt="Python 3.12">
  <img src="https://img.shields.io/badge/GTK-4 + libadwaita-4A90D9?logo=gnome&logoColor=white" alt="GTK4 + libadwaita">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT">
</p>

> ⚠️ **Positioning — read this first.** The name “VPN Gate Client” officially
> belongs to a **Windows-only** freeware (SoftEther VPN Client + VPN Gate
> Client Plugin) published by the VPN Gate Academic Experiment Project —
> Windows users should download it from the
> [official download page](https://www.vpngate.net/en/download.aspx).
> For macOS, iPhone/iPad, and Android the project publishes
> [step-by-step how-tos](https://www.vpngate.net/en/howto.aspx) based on the
> OS built-in L2TP/IPsec client or a generic OpenVPN app.
> **No official client of any kind exists for Linux** — Linux users are
> otherwise left with manual `.ovpn` handling. **This repo fills exactly that
> gap**: a native Linux app that automates browse → connect → verify →
> clean-disconnect. It is an independent community project, not affiliated
> with or endorsed by the VPN Gate Academic Project.

## Contents

- [Why this exists](#why-this-exists)
- [Features](#features)
- [Install](#install)
- [Usage](#usage)
- [How it works](#how-it-works)
- [Tech stack](#tech-stack)
- [Troubleshooting](#troubleshooting)
- [Security notes](#security-notes)
- [Project structure](#project-structure)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgements](#acknowledgements)

## Why this exists

The official project ships a one-click plug-in for Windows and guides for
macOS, iPhone, iPad and Android. For Linux it ships nothing — the only
documented path is hand-assembling OpenVPN configs, and the official guide
itself concedes that path is the hard one (“Other methods are easier than
OpenVPN. … OpenVPN client configurations are difficult.”).

The manual Linux ritual this replaces: download a `.ovpn` per server,
hand-patch the legacy ciphers modern OpenSSL rejects, import via Settings or
`nmcli`, type `vpn`/`vpn` on every connect, verify the IP yourself, leak IPv6
silently around the IPv4-only tunnel, then delete the profile and stray files
by hand — and repeat for the next server, because volunteer servers appear
and vanish without notice.

| Your OS | What to use |
|---|---|
| **Linux** (Debian/Ubuntu, GNOME) | ✅ **This repo** |
| Windows | The official SoftEther-based client (see note above) |
| macOS / iPhone / iPad / Android | The official how-tos (see note above) |

## Features

1. **Server browser** — live directory with country flag, ping, speed, score,
   sessions and uptime. Filter, sort, search; instant from cache, refreshed
   silently in the background.
2. **IPv6 leak blocked (3 layers)** — VPN Gate tunnels are IPv4-only, so
   untunneled IPv6 would bypass the VPN. The app filters `route-ipv6` /
   `ifconfig-ipv6` out of the profile, sets `ipv6.method disabled` on it, and
   switches system IPv6 off while connected — restoring your previous state
   on disconnect. Verify with `vpngate-client --status`.
3. **One-time setup** — the first CONNECT shows an info popup, then a single
   system password dialog installs a narrowly scoped permanent rule (only two
   sysctl keys may run passwordless). Never asked again, never a prompt loop;
   declining degrades honestly with a warning instead of silence.
4. **Zero leftovers** — disconnects, failed attempts and crashes all converge
   on the same cleanup: dead profiles deleted, staged files shredded, IPv6
   restored, verified gone.
5. **Honest errors** — detects server-side login rejections and aborts instead
   of looping desktop password prompts. Cancelling a connect aborts within a
   second with full cleanup. Every failure is a plain sentence, never a raw
   `nmcli` dump.
6. **Headless CLI** — `--list`, `--status`, `--dry-run-host` and
   `--disconnect-all` for scripting and diagnostics without a display.
7. **Native packaging** — dependency-declared `.deb` with app-grid entry,
   hicolor icon and manpage; Python standard library + PyGObject only, zero
   pip dependencies.

## Install

Current release: **1.1-1**. Debian/Ubuntu with GNOME and NetworkManager.

### Option A — download from Releases (recommended)

Grab `vpngate-client_*_all.deb` (latest: 1.1-1) from the
[Releases page](https://github.com/ajangsupardi/vpn-gate/releases), then:

```bash
sudo dpkg -i vpngate-client_*_all.deb
```

This installs `/usr/bin/vpngate-client`, the app-grid entry with its icon, and
a manpage. Runtime dependencies are declared in the package, so a plain
`dpkg -i` is enough on Debian/Ubuntu derivatives. No build tools needed.

### Option B — build from source

```bash
./packaging/build-deb.sh # → packaging/vpngate-client_*_all.deb (version from DEBIAN/control)
sudo dpkg -i packaging/vpngate-client_*_all.deb
```

### Option C — run from source (development)

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 network-manager-openvpn openvpn
python3 vpngate_gtk.py
```

## Usage

Launch **VPN Gate Client** from the app grid, or run `vpngate-client` /
`python3 vpngate_gtk.py`.

1. The server list loads instantly from cache, then refreshes in the background.
2. Filter by country, sort by ping/score/speed, or type to search.
3. Select a server → **CONNECT**. On a fresh machine an info popup appears
   first, then ONE system password dialog grants permanent access (see
   [Security notes](#security-notes)). Status and public IP appear
   bottom-right once verified.
4. **DISCONNECT** when done — the profile and its files are removed, IPv6 restored.

Headless equivalents (also used for diagnostics):

```bash
vpngate-client --list --country JP --limit 10 --sort ping
vpngate-client --dry-run-host <HostName>   # write + validate the .ovpn only
vpngate-client --status                    # active connection + public IP + IPv6 state
vpngate-client --disconnect-all            # remove every vpngate profile + leftovers
```

## How it works

1. **Fetch** the server CSV from the VPN Gate API, cached 6 h in
   `~/.cache/vpn-gate/servers.csv` (cache-first UI so a slow API never blocks
   startup).
2. **Decode** the server's Base64 OpenVPN config and patch legacy crypto for
   OpenVPN 2.6 / OpenSSL 3 (`cipher` + `data-ciphers` + `data-ciphers-fallback
   AES-128-CBC`, `auth SHA1`) plus IPv6 `pull-filter` ignores; write
   `~/.cache/vpn-gate/profiles/*.ovpn` (0600) plus a separate auth file.
3. **Import** via `nmcli` with legacy-compatible `vpn.data`
   (`username=vpn`, stored secrets), `ipv6.method disabled` on the profile,
   `cert-pass-flags=not-required` (VPN Gate keys are unencrypted — verified
   per key via openssl — so NM never pops a passphrase dialog),
   then disable system IPv6 (`net.ipv6.conf.all/default.disable_ipv6=1`,
   previous state saved to `~/.cache/vpn-gate/ipv6.json`), then
   `nmcli connection up` and verify the public IP actually changed.
4. **Disconnect** with `down` + `delete`, remove the staged `.pem` files and
   cached profile files, restore IPv6 to its pre-session state, then verify
   the profile is really gone — warning loudly in the status bar if anything
   remains.

## Tech stack

- **Language:** Python 3.12 (standard library + PyGObject, no extra pip packages)
- **UI:** GTK 4 + libadwaita (`python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`)
- **VPN:** OpenVPN 2.6 via NetworkManager (`network-manager-openvpn`, `openvpn`, `nmcli`)
- **Data:** VPN Gate API (`http://www.vpngate.net/api/iphone/`), cached locally for 6 hours
- **Packaging:** `dpkg-deb` + `fakeroot`, validated with `lintian`

## Troubleshooting

- **First refresh takes ~1 min.** The VPN Gate API is slow; the UI uses cache
  meanwhile. Use `--refresh` only when needed.
- **`IP: ?` right after connect.** Routes/DNS still settling — the app retries
  automatically and shows the tunnel IP meanwhile.
- **“Server rejected the login” / timeouts.** Volunteer servers fill up, die,
  or ignore handshakes; pick another server (low ping ≠ responsive OpenVPN).
  Failed attempts clean up after themselves.
- **Password dialog appears on CONNECT.** Expected once on a fresh machine
  (one-time permanent setup). Cancel = at most that single dialog, then a
  warning instead of silence.
- **“IPv6 is not blocked” warning.** The setup was declined or failed —
  reconnect and approve the password prompt, otherwise IPv6 can leak around
  the tunnel.
- **IP doesn't change after connect.** Another VPN (e.g. ProtonVPN) may be
  holding the default route — disconnect it first.
- **App-grid entry missing after install.** Log out and back in once so GNOME
  reloads the desktop database.

## Security notes

- Servers are volunteer-run; each one declares its own logging policy on the
  official server list — read it before you connect.
- **IPv6 leak protection (3 layers):** VPN Gate tunnels are IPv4-only, so
  untunneled IPv6 would bypass the VPN. On connect the app (1) adds
  `pull-filter ignore "route-ipv6" / "ifconfig-ipv6"` to the `.ovpn`,
  (2) sets `ipv6.method disabled` on the NetworkManager profile, and
  (3) disables system IPv6 via sysctl — first connect shows an info popup,
  then ONE system password dialog installs permanent scoped access
  (`%sudo` may run only these two sysctl keys without a password) and you
  are never asked again. Cancelling shows at most that single dialog, then
  an honest warning. Manual equivalent (same script the app uses):
  `sudo ./packaging/setup-nopasswd-sudo.sh`.
  Disconnect restores your previous IPv6 state; a startup sweep also
  restores it after a crash. Check with `vpngate-client --status`
  (`ipv6: disabled` while connected).
- There is **no killswitch** yet — IPv4 traffic may leak to the direct
  route if the tunnel drops. Do not use for high-risk activity.
- Credentials and auth files are mode `0600`; the VPN password lives in the
  NetworkManager profile, never in this repo.
- The app talks to the public server directory and nothing else: no accounts,
  no telemetry, no bundled servers.

## Project structure

```text
.
├── vpngate_gtk.py    # GUI: server table, connect/cancel/disconnect, status, theming
├── vpngate_core.py   # API fetch, CSV cache, filtering/sorting model
├── vpngate_ovpn.py   # Base64 decode + legacy-crypto patching, profile writer
├── vpngate_nm.py     # nmcli wrapper: import/up/down, IP retry, IPv6, cleanup, sweep
├── data/             # .desktop launcher + SVG app icon
├── packaging/        # build-deb.sh + setup-nopasswd-sudo.sh + DEBIAN control, wrapper, manpage, docs
├── tools/            # make-og-image.py — regenerates the website's Open Graph image
├── LICENSE           # MIT
└── README.md
```

## Contributing

Issues and pull requests are welcome. Please keep changes small and focused,
match the existing code style (standard library + PyGObject only, no new
runtime dependencies without discussion), and verify with:

```bash
python3 -m py_compile vpngate_gtk.py vpngate_core.py vpngate_nm.py vpngate_ovpn.py
python3 vpngate_gtk.py --status
./packaging/build-deb.sh # must stay lintian-clean
```

## License

MIT — see [LICENSE](LICENSE). You are free to use, modify, and redistribute,
including the styling and icon shipped in `data/`.

> Trademark note: the interface styling and icon are original work merely
> *inspired by* BMW M design cues (dark canvas, tricolor stripe). BMW M marks
> belong to BMW AG; this project has no affiliation with or endorsement from
> BMW.

## Acknowledgements

- [VPN Gate Academic Experiment Project](https://www.vpngate.net/), University
  of Tsukuba, Japan — free server network and the public `vpn`/`vpn`
  credentials used by every client. Windows users want the official client
  from their download page; other platforms are covered by their how-to index.
- GNOME, GTK, libadwaita, NetworkManager, and OpenVPN contributors.

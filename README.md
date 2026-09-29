<p align="center">
  <img src="data/io.github.ajangsupardi.vpngate.svg" width="96" alt="VPN Gate Client logo">
</p>

<h1 align="center">VPN Gate Client for Linux</h1>

<p align="center">
  <b>A Linux GUI for free VPN Gate servers — one-click connection, verified IP, and zero leftover profiles.</b>
</p>

<p align="center">
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
> **No official client of any kind exists for Linux** — the download page
> doesn't list one, so Linux users are otherwise left with manual `.ovpn`
> handling. **This repo fills exactly that gap**: a native Linux app that
> automates browse → connect → verify → clean-disconnect. It is an
> independent community project, not affiliated with or endorsed by the
> VPN Gate Academic Project.

## Contents

- [Who is this for?](#who-is-this-for)
- [Features](#features)
- [Install](#install)
- [Usage](#usage)
- [Tech stack](#tech-stack)
- [How it works](#how-it-works)
- [Troubleshooting](#troubleshooting)
- [Security notes](#security-notes)
- [Project structure](#project-structure)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgements](#acknowledgements)

## Who is this for?

| Your OS | What to use |
|---|---|
| **Linux** (Debian/Ubuntu, GNOME) | ✅ **This repo** — the only dedicated VPN Gate client app for Linux |
| Windows | ⬆️ [Official VPN Gate Client](https://www.vpngate.net/en/download.aspx) (SoftEther-based freeware, Windows x86/x64) |
| macOS / iPhone / iPad / Android | ⬆️ [Official how-tos](https://www.vpngate.net/en/howto.aspx) (built-in L2TP/IPsec or generic OpenVPN app) |

## Features

| Area | What you get |
|---|---|
| Server browser | Live list from the VPN Gate API with country flag, ping, speed, score, sessions, and uptime — sortable, filterable, searchable |
| One-click connect | Single CONNECT / DISCONNECT toggle with busy state; never leaves a half-connected UI |
| Legacy-cipher handling | Patches VPN Gate configs (`AES-128-CBC`, `SHA1`) so they import cleanly on OpenVPN 2.6 / OpenSSL 3 |
| Verified connection | Retries public-IP lookup after `up` (routes need seconds to settle); shows tunnel IP while verifying instead of a bare `?` |
| Full cleanup | Disconnect deletes the NM profile, staged `.pem` files, and cached `.ovpn`/auth files — and verifies nothing is left |
| Crash-safety sweep | Startup removes any inactive `vpngate-*` profile orphaned by a previous crash |
| Headless mode | `--list`, `--status`, `--dry-run-host`, `--disconnect-all` for scripting and testing without a display |
| Native packaging | Builds a dependency-declared `.deb` with app-grid entry, hicolor icon, and manpage |

## Install

### Option A — download from Releases (recommended)

Grab `vpngate-client_1.0-1_all.deb` from the
[Releases page](https://github.com/ajangsupardi/vpn-gate/releases), then:

```bash
sudo dpkg -i vpngate-client_1.0-1_all.deb
```

This installs `/usr/bin/vpngate-client`, the app-grid entry with its icon, and
a manpage. Runtime dependencies are declared in the package, so a plain
`dpkg -i` is enough on Debian/Ubuntu derivatives. No build tools needed.

### Option B — build from source

```bash
./packaging/build-deb.sh # → packaging/vpngate-client_1.0-1_all.deb
sudo dpkg -i packaging/vpngate-client_1.0-1_all.deb
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
3. Select a server → **CONNECT**. Status and public IP appear bottom-right.
4. **DISCONNECT** when done — the profile and its files are removed.

Headless equivalents (also used for diagnostics):

```bash
vpngate-client --list --country JP --limit 10 --sort ping
vpngate-client --dry-run-host <HostName>   # write + validate the .ovpn only
vpngate-client --status                    # active connection + public IP
vpngate-client --disconnect-all            # remove every vpngate profile + leftovers
```

## Tech stack

- **Language:** Python 3.12 (standard library + PyGObject, no extra pip packages)
- **UI:** GTK 4 + libadwaita (`python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`)
- **VPN:** OpenVPN 2.6 via NetworkManager (`network-manager-openvpn`, `openvpn`, `nmcli`)
- **Data:** VPN Gate API (`http://www.vpngate.net/api/iphone/`), cached locally for 6 hours
- **Packaging:** `dpkg-deb` + `fakeroot`, validated with `lintian`

## How it works

1. **Fetch** the server CSV from the VPN Gate API, cached 6 h in
   `~/.cache/vpn-gate/servers.csv` (cache-first UI so a slow API never blocks
   startup).
2. **Decode** the server's Base64 OpenVPN config and patch legacy crypto for
   OpenVPN 2.6 / OpenSSL 3 (`cipher` + `data-ciphers` + `data-ciphers-fallback
   AES-128-CBC`, `auth SHA1`); write `~/.cache/vpn-gate/profiles/*.ovpn`
   (0600) plus a separate auth file.
3. **Import** via `nmcli` with legacy-compatible `vpn.data`
   (`username=vpn`, stored secrets), then `nmcli connection up` and verify the
   public IP actually changed.
4. **Disconnect** with `down` + `delete`, remove the staged `.pem` files and
   cached profile files, then verify the profile is really gone — warning
   loudly in the status bar if anything remains.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| First refresh takes ~1 min | The VPN Gate API is slow; the UI uses cache meanwhile. Use `--refresh` only when needed. |
| `IP: ?` right after connect | Routes/DNS still settling — the app retries automatically and shows the tunnel IP meanwhile. |
| "Connect failed — try another server" | Volunteer servers come and go; pick one with low ping and recent uptime. |
| IP doesn't change after connect | Another VPN (e.g. ProtonVPN) may be holding the default route — disconnect it first. |
| App-grid entry missing after install | Log out and back in once so GNOME reloads the desktop database. |

## Security notes

- Servers are volunteer-run; their logging policy is typically 2 weeks.
  Choose servers accordingly.
- There is **no killswitch** in v1 — traffic may leak to the direct route if
  the tunnel drops. Do not use for high-risk activity.
- Credentials and auth files are mode `0600`; the VPN password lives in the
  NetworkManager profile, never in this repo.

## Project structure

```text
.
├── vpngate_gtk.py    # GUI: server table, CONNECT/DISCONNECT toggle, status, theming
├── vpngate_core.py   # API fetch, CSV cache, filtering/sorting model
├── vpngate_ovpn.py   # Base64 decode + legacy-crypto patching, profile writer
├── vpngate_nm.py     # nmcli wrapper: import/up/down, IP retry, cleanup, sweep
├── data/             # .desktop launcher + SVG app icon
├── packaging/        # build-deb.sh + DEBIAN control, wrapper, manpage, docs
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
./packaging/build-deb.sh # must stay lintian-clean apart from local-build notes
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
  credentials used by every client.
- [Official download page](https://www.vpngate.net/en/download.aspx) — home of
  the official Windows VPN Gate Client (SoftEther-based).
- [Official how-to index](https://www.vpngate.net/en/howto.aspx) — connection
  guides for Windows, Mac, iPhone/iPad, Android, L2TP/IPsec, OpenVPN, and
  MS-SSTP, which informed this app's Linux automation.
- GNOME, GTK, libadwaita, NetworkManager, and OpenVPN contributors.

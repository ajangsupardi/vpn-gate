#!/bin/sh
# One-time permanent setup for vpngate-client IPv6 control.
# Runs AS ROOT — invoke once via `pkexec $0` (one password dialog) or
# `sudo $0` (one password entry). Afterwards passwordless forever.
# Scope is tiny and fixed (no user input involved): members of the sudo
# group may run only the two net.ipv6 disable sysctls, nothing else.
set -e
RULE='%sudo ALL=(root) NOPASSWD: /usr/sbin/sysctl -w net.ipv6.conf.all.disable_ipv6=*, /usr/sbin/sysctl -w net.ipv6.conf.default.disable_ipv6=*'
TMP="$(mktemp)"
printf '%s\n' "$RULE" > "$TMP"
visudo -c -f "$TMP" >/dev/null
install -m 0440 -o root -g root "$TMP" /etc/sudoers.d/vpngate-client
rm -f "$TMP"
echo "OK: permanent passwordless IPv6 control installed."

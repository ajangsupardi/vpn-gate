#!/bin/sh
# Build vpngate-client_1.0-1_all.deb from this source tree.
# Usage: ./packaging/build-deb.sh   (run from repo root or anywhere)
set -e
SRC="$(dirname "$0")/.."
OUT="$(dirname "$0")"
PKG="$OUT/vpngate-client_1.0-1_all"

rm -rf "$PKG"
mkdir -p "$PKG/DEBIAN" \
         "$PKG/usr/share/vpngate-client" \
         "$PKG/usr/bin" \
         "$PKG/usr/share/applications" \
         "$PKG/usr/share/icons/hicolor/scalable/apps" \
         "$PKG/usr/share/man/man1" \
         "$PKG/usr/share/doc/vpngate-client"

cp "$SRC/vpngate_gtk.py" "$SRC/vpngate_core.py" \
   "$SRC/vpngate_nm.py" "$SRC/vpngate_ovpn.py" \
   "$PKG/usr/share/vpngate-client/"
cp "$SRC/packaging/meta/DEBIAN/control" "$PKG/DEBIAN/"
cp "$SRC/packaging/meta/usr/bin/vpngate-client" "$PKG/usr/bin/"
cp "$SRC/packaging/meta/usr/share/applications/io.github.ajangsupardi.vpngate.desktop" \
   "$PKG/usr/share/applications/"
cp "$SRC/data/io.github.ajangsupardi.vpngate.svg" \
   "$PKG/usr/share/icons/hicolor/scalable/apps/io.github.ajangsupardi.vpngate.svg"
cp "$SRC/packaging/meta/usr/share/man/man1/vpngate-client.1" \
   "$PKG/usr/share/man/man1/"
gzip -9 -n -f "$PKG/usr/share/man/man1/vpngate-client.1"
cp "$SRC/packaging/meta/usr/share/doc/vpngate-client/copyright" \
   "$PKG/usr/share/doc/vpngate-client/"
gzip -9 -n -c "$SRC/packaging/meta/usr/share/doc/vpngate-client/changelog" \
   > "$PKG/usr/share/doc/vpngate-client/changelog.gz"

chmod 755 "$PKG/usr/bin/vpngate-client"
chmod 755 "$PKG/DEBIAN" 2>/dev/null || true
# Normalize permissions (repo umask yields 0664/0775).
find "$PKG" -type d -exec chmod 755 {} +
chmod 644 "$PKG/usr/share/vpngate-client/"*.py \
          "$PKG/usr/share/applications/"*.desktop \
          "$PKG/usr/share/icons/hicolor/scalable/apps/"*.svg \
          "$PKG/usr/share/doc/vpngate-client/copyright" \
          "$PKG/usr/share/doc/vpngate-client/changelog.gz" \
          "$PKG/usr/share/man/man1/vpngate-client.1.gz"

cd "$OUT"
fakeroot dpkg-deb --build "vpngate-client_1.0-1_all"
echo "--- lintian ---"
lintian "vpngate-client_1.0-1_all.deb" || true
echo "--- contents ---"
dpkg-deb -c "vpngate-client_1.0-1_all.deb"

#!/bin/sh
# Build continuum-vpn-widget_<version>_amd64.deb for Ubuntu 24.04 and 26.04.
set -eu
ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
VERSION="$(tr -d '[:space:]' <"$ROOT/VERSION")"
STAGE="$ROOT/staging"
rm -rf "$STAGE"
"$ROOT/scripts/fetch-obfuscators.sh"

mkdir -p \
  "$STAGE/DEBIAN" \
  "$STAGE/usr/bin" \
  "$STAGE/usr/lib/continuum-vpn/bin" \
  "$STAGE/usr/share/applications" \
  "$STAGE/usr/share/icons/hicolor/256x256/apps" \
  "$STAGE/usr/share/polkit-1/actions" \
  "$STAGE/usr/share/doc/continuum-vpn-widget"

install -m 0755 "$ROOT/lib/engine.py" "$ROOT/lib/widget.py" "$ROOT/lib/priv-helper" "$STAGE/usr/lib/continuum-vpn/"
install -m 0644 "$ROOT/icons/continuum-vpn.png" "$ROOT/icons/continuum-logo.png" "$STAGE/usr/lib/continuum-vpn/"
install -m 0644 "$ROOT/icons/continuum-vpn.png" "$STAGE/usr/share/icons/hicolor/256x256/apps/continuum-vpn.png"
install -m 0644 "$ROOT/VERSION" "$STAGE/usr/lib/continuum-vpn/VERSION"
install -m 0755 "$ROOT/third-party/bin/sslocal" "$ROOT/third-party/bin/wg-obfuscator" "$ROOT/third-party/bin/udp2raw" "$STAGE/usr/lib/continuum-vpn/bin/"
install -m 0644 "$ROOT/continuum-vpn-widget.desktop" "$STAGE/usr/share/applications/continuum-vpn-widget.desktop"
install -m 0644 "$ROOT/polkit/com.continuumdao.vpn.policy" "$STAGE/usr/share/polkit-1/actions/com.continuumdao.vpn.policy"
install -m 0644 "$ROOT/THIRD_PARTY_NOTICES" "$STAGE/usr/share/doc/continuum-vpn-widget/THIRD_PARTY_NOTICES"
install -m 0644 "$ROOT/third-party/wg-obfuscator-LICENSE" "$STAGE/usr/share/doc/continuum-vpn-widget/wg-obfuscator-LICENSE"

cat >"$STAGE/usr/bin/continuum-vpn-widget" <<'EOF'
#!/bin/sh
exec python3 /usr/lib/continuum-vpn/widget.py "$@"
EOF
chmod 0755 "$STAGE/usr/bin/continuum-vpn-widget"

cat >"$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
chmod 0755 /usr/lib/continuum-vpn/priv-helper /usr/lib/continuum-vpn/bin/sslocal /usr/lib/continuum-vpn/bin/wg-obfuscator /usr/lib/continuum-vpn/bin/udp2raw /usr/bin/continuum-vpn-widget
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q /usr/share/icons/hicolor || true
fi
exit 0
EOF
chmod 0755 "$STAGE/DEBIAN/postinst"

cat >"$STAGE/DEBIAN/control" <<EOF
Package: continuum-vpn-widget
Version: $VERSION
Section: net
Priority: optional
Architecture: amd64
Depends: python3, python3-gi, gir1.2-gtk-3.0, gir1.2-ayatanaappindicator3-0.1, network-manager, wireguard-tools, iproute2, pkexec, polkitd | policykit-1
Maintainer: ContinuumDAO <https://github.com/ContinuumDAO/continuum-vpn-widgets>
Description: Optional Continuum VPN tray widget for Ubuntu
 Import a profile bundle from the Continuum node VPN panel and turn a
 tunnel on or off from the menu bar. Includes sslocal, wg-obfuscator,
 and udp2raw. Installing WireGuard and those tools yourself still works.
EOF

find "$STAGE" -type d -exec chmod 0755 {} +
OUT="$ROOT/../continuum-vpn-widget_${VERSION}_amd64.deb"
dpkg-deb --root-owner-group -Zxz --build "$STAGE" "$OUT"
cp -f "$OUT" "$ROOT/../continuum-vpn-widget_amd64.deb"
echo "$OUT"

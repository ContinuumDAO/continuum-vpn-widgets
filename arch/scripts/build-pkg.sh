#!/bin/sh
# Build continuum-vpn-widget-<version>-1-x86_64.pkg.tar.zst for Arch Linux.
# The tray program is the same one shipped in the Ubuntu package.
set -eu
ARCH_DIR="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
REPO="$(CDPATH= cd -- "$ARCH_DIR/.." && pwd)"
UBUNTU="$REPO/ubuntu"
VERSION="$(tr -d '[:space:]' <"$UBUNTU/VERSION")"
STAGE="$ARCH_DIR/staging"
PKGVER="${VERSION}-1"
NAME="continuum-vpn-widget"
rm -rf "$STAGE"
"$UBUNTU/scripts/fetch-obfuscators.sh"

mkdir -p \
  "$STAGE/usr/bin" \
  "$STAGE/usr/lib/continuum-vpn/bin" \
  "$STAGE/usr/share/applications" \
  "$STAGE/usr/share/icons/hicolor/256x256/apps" \
  "$STAGE/usr/share/polkit-1/actions" \
  "$STAGE/usr/share/doc/continuum-vpn-widget" \
  "$STAGE/usr/share/licenses/$NAME"

install -m 0755 "$UBUNTU/lib/engine.py" "$UBUNTU/lib/widget.py" "$UBUNTU/lib/priv-helper" "$STAGE/usr/lib/continuum-vpn/"
install -m 0644 "$UBUNTU/icons/continuum-vpn.png" "$UBUNTU/icons/continuum-logo.png" "$STAGE/usr/lib/continuum-vpn/"
install -m 0644 "$UBUNTU/icons/continuum-vpn.png" "$STAGE/usr/share/icons/hicolor/256x256/apps/continuum-vpn.png"
install -m 0644 "$UBUNTU/VERSION" "$STAGE/usr/lib/continuum-vpn/VERSION"
install -m 0755 "$UBUNTU/third-party/bin/sslocal" "$UBUNTU/third-party/bin/wg-obfuscator" "$UBUNTU/third-party/bin/udp2raw" "$STAGE/usr/lib/continuum-vpn/bin/"
install -m 0644 "$UBUNTU/continuum-vpn-widget.desktop" "$STAGE/usr/share/applications/continuum-vpn-widget.desktop"
install -m 0644 "$UBUNTU/polkit/com.continuumdao.vpn.policy" "$STAGE/usr/share/polkit-1/actions/com.continuumdao.vpn.policy"
install -m 0644 "$UBUNTU/THIRD_PARTY_NOTICES" "$STAGE/usr/share/doc/continuum-vpn-widget/THIRD_PARTY_NOTICES"
install -m 0644 "$UBUNTU/third-party/wg-obfuscator-LICENSE" "$STAGE/usr/share/doc/continuum-vpn-widget/wg-obfuscator-LICENSE"
install -m 0644 "$REPO/LICENSE" "$STAGE/usr/share/licenses/$NAME/LICENSE"

cat >"$STAGE/usr/bin/continuum-vpn-widget" <<'EOF'
#!/bin/sh
exec python3 /usr/lib/continuum-vpn/widget.py "$@"
EOF
chmod 0755 "$STAGE/usr/bin/continuum-vpn-widget"

cat >"$STAGE/.INSTALL" <<'EOF'
post_install() {
  if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q /usr/share/icons/hicolor || true
  fi
}

post_upgrade() {
  post_install
}
EOF

SIZE="$(find "$STAGE/usr" -type f -printf '%s\n' | awk '{s+=$1} END {print s+0}')"
BUILDDATE="$(date +%s)"
cat >"$STAGE/.PKGINFO" <<EOF
pkgname = $NAME
pkgbase = $NAME
pkgver = $PKGVER
pkgdesc = Optional Continuum VPN tray widget for Arch Linux
url = https://github.com/ContinuumDAO/continuum-vpn-widgets
builddate = $BUILDDATE
packager = ContinuumDAO <https://github.com/ContinuumDAO/continuum-vpn-widgets>
size = $SIZE
arch = x86_64
license = MIT
depend = python
depend = python-gobject
depend = gtk3
depend = libayatana-appindicator
depend = networkmanager
depend = wireguard-tools
depend = iproute2
depend = polkit
xdata = pkgtype=pkg
EOF

command -v zstd >/dev/null 2>&1 || {
  echo "zstd is required to build the Arch package" >&2
  exit 1
}

OUT="$REPO/${NAME}-${PKGVER}-x86_64.pkg.tar.zst"
ALIAS="$REPO/${NAME}-x86_64.pkg.tar.zst"
(
  cd "$STAGE"
  tar --owner=0 --group=0 --numeric-owner -cf - .PKGINFO .INSTALL usr | zstd -c -T0 >"$OUT"
)
cp -f "$OUT" "$ALIAS"
echo "$OUT"

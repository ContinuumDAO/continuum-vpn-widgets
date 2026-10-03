#!/bin/sh
# Build continuum-vpn-widget-<version>-1.suse.x86_64.rpm for openSUSE.
# The tray program is the same one shipped in the Ubuntu package.
set -eu
SUSE_DIR="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
REPO="$(CDPATH= cd -- "$SUSE_DIR/.." && pwd)"
UBUNTU="$REPO/ubuntu"
VERSION="$(tr -d '[:space:]' <"$UBUNTU/VERSION")"
STAGE="$SUSE_DIR/staging"
TOP="$SUSE_DIR/rpmbuild"
NAME="continuum-vpn-widget"
RELEASE="1.suse"
rm -rf "$STAGE" "$TOP"
"$UBUNTU/scripts/fetch-obfuscators.sh"

mkdir -p \
  "$STAGE/usr/bin" \
  "$STAGE/usr/lib/continuum-vpn/bin" \
  "$STAGE/usr/share/applications" \
  "$STAGE/usr/share/icons/hicolor/256x256/apps" \
  "$STAGE/usr/share/polkit-1/actions" \
  "$STAGE/usr/share/doc/continuum-vpn-widget" \
  "$STAGE/usr/share/licenses/$NAME" \
  "$TOP/BUILD" "$TOP/RPMS" "$TOP/SOURCES" "$TOP/SPECS" "$TOP/SRPMS"

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

command -v rpmbuild >/dev/null 2>&1 || {
  echo "rpmbuild is required to build the openSUSE package" >&2
  exit 1
}

SPEC="$TOP/SPECS/$NAME.spec"
cat >"$SPEC" <<EOF
Name: $NAME
Version: $VERSION
Release: $RELEASE
Summary: Optional Continuum VPN tray widget for openSUSE
License: MIT
URL: https://github.com/ContinuumDAO/continuum-vpn-widgets
BuildArch: x86_64
AutoReqProv: no

Requires: python3
Requires: python3-gobject
Requires: gtk3
Requires: libayatana-appindicator3-1
Requires: typelib-1_0-AyatanaAppIndicator3-0_1
Requires: NetworkManager
Requires: wireguard-tools
Requires: iproute2
Requires: polkit

%define debug_package %{nil}
%define _build_id_links none

%description
Import a profile bundle from the Continuum node VPN panel and turn a tunnel on or off from the menu bar. Includes sslocal, wg-obfuscator, and udp2raw.

%install
rm -rf %{buildroot}
mkdir -p %{buildroot}
cp -a $STAGE/. %{buildroot}/

%post
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q /usr/share/icons/hicolor || :
fi

%files
%defattr(-,root,root,-)
/usr/bin/continuum-vpn-widget
/usr/lib/continuum-vpn
/usr/share/applications/continuum-vpn-widget.desktop
/usr/share/icons/hicolor/256x256/apps/continuum-vpn.png
/usr/share/polkit-1/actions/com.continuumdao.vpn.policy
/usr/share/doc/continuum-vpn-widget
/usr/share/licenses/continuum-vpn-widget
EOF

rpmbuild -bb --define "_topdir $TOP" "$SPEC"
OUT="$REPO/${NAME}-${VERSION}-${RELEASE}.x86_64.rpm"
ALIAS="$REPO/${NAME}-suse.x86_64.rpm"
cp -f "$TOP/RPMS/x86_64/${NAME}-${VERSION}-${RELEASE}.x86_64.rpm" "$OUT"
cp -f "$OUT" "$ALIAS"
echo "$OUT"

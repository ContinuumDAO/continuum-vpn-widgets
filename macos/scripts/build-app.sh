#!/bin/sh
# Assemble Continuum VPN.app for arm64 and x64.
# The menu-bar binary is compiled when swiftc is available (the macOS release runner).
set -eu
MACOS="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
REPO="$(CDPATH= cd -- "$MACOS/.." && pwd)"
UBUNTU="$REPO/ubuntu"
# shellcheck disable=SC1091
. "$UBUNTU/versions.env"
VERSION="$(tr -d '[:space:]' <"$UBUNTU/VERSION")"
STAGE="$MACOS/staging"
rm -rf "$STAGE"
mkdir -p "$STAGE"
"$MACOS/scripts/fetch-obfuscators.sh"
"$MACOS/scripts/build-wireguard-go.sh"

python_asset() {
  if [ "$1" = "arm64" ]; then
    printf '%s\n' "$PYTHON_STANDALONE_ARM"
  else
    printf '%s\n' "$PYTHON_STANDALONE_X64"
  fi
}

swift_target() {
  if [ "$1" = "arm64" ]; then
    printf '%s\n' "arm64-apple-macosx13.0"
  else
    printf '%s\n' "x86_64-apple-macosx13.0"
  fi
}

stage_app() {
  arch="$1"
  root="$STAGE/$arch/Continuum VPN.app/Contents"
  mkdir -p "$root/MacOS" "$root/Resources/bin"
  cp "$UBUNTU/lib/engine.py" "$root/Resources/engine.py"
  cp "$UBUNTU/VERSION" "$root/Resources/VERSION"
  cp "$MACOS/lib/priv-helper" "$root/Resources/priv-helper"
  cp "$UBUNTU/icons/continuum-vpn.png" "$UBUNTU/icons/continuum-logo.png" "$root/Resources/"
  install -m 0755 "$MACOS/third-party/bin/$arch/sslocal" "$root/Resources/bin/sslocal"
  install -m 0755 "$MACOS/third-party/bin/$arch/wg-obfuscator" "$root/Resources/bin/wg-obfuscator"
  install -m 0755 "$MACOS/third-party/bin/$arch/wireguard-go" "$root/Resources/bin/wireguard-go"
  chmod 0755 "$root/Resources/priv-helper"
  if [ -e "$root/Resources/bin/udp2raw" ]; then
    echo "udp2raw must not be bundled in the macOS app" >&2
    exit 1
  fi
  asset="$(python_asset "$arch")"
  tarball="$MACOS/third-party/src/$asset"
  if [ ! -f "$tarball" ]; then
    curl -fsSL "https://github.com/astral-sh/python-build-standalone/releases/download/${PYTHON_STANDALONE_TAG}/${asset}" -o "$tarball"
  fi
  tar -xzf "$tarball" -C "$root/Resources"
  cat >"$root/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>continuum-vpn-widget</string>
  <key>CFBundleIdentifier</key>
  <string>com.continuumdao.vpn.widget</string>
  <key>CFBundleName</key>
  <string>Continuum VPN</string>
  <key>CFBundleDisplayName</key>
  <string>Continuum VPN</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>$VERSION</string>
  <key>CFBundleVersion</key>
  <string>$VERSION</string>
  <key>LSMinimumSystemVersion</key>
  <string>13.0</string>
  <key>LSUIElement</key>
  <true/>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
EOF
  if command -v swiftc >/dev/null 2>&1; then
    swiftc -O -target "$(swift_target "$arch")" -framework Cocoa \
      -o "$root/MacOS/continuum-vpn-widget" \
      "$MACOS/ContinuumVPN/main.swift"
  else
    echo "swiftc is not on this machine; $arch app resources are staged without the menu-bar binary" >&2
  fi
}

stage_app arm64
stage_app x64

if ! command -v swiftc >/dev/null 2>&1; then
  echo "Menu-bar binaries are compiled on the macOS release runner." >&2
  exit 0
fi

for arch in arm64 x64; do
  app="$STAGE/$arch/Continuum VPN.app"
  versioned="$REPO/continuum-vpn-widget-${VERSION}-macos-${arch}.zip"
  alias="$REPO/continuum-vpn-widget-macos-${arch}.zip"
  (
    cd "$STAGE/$arch"
    rm -f "$versioned" "$alias"
    zip -r -q "$versioned" "Continuum VPN.app"
  )
  cp -f "$versioned" "$alias"
  echo "$versioned"
done

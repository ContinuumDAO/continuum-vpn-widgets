#!/bin/sh
# Build the Windows Continuum VPN folder and zip it.
# The tunnel uses WireGuard for Windows. WSL is not involved.
set -eu
WINDOWS="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
REPO="$(CDPATH= cd -- "$WINDOWS/.." && pwd)"
UBUNTU="$REPO/ubuntu"
# shellcheck disable=SC1091
. "$UBUNTU/versions.env"
VERSION="$(tr -d '[:space:]' <"$UBUNTU/VERSION")"
WORK="$WINDOWS/third-party/src"
BIN="$WINDOWS/third-party/bin"
STAGE="$WINDOWS/staging/Continuum VPN"
rm -rf "$WINDOWS/staging"
mkdir -p "$WORK" "$BIN" "$STAGE/python" "$STAGE/resources/bin"

fetch() {
  url="$1"
  out="$2"
  if [ ! -f "$out" ]; then
    curl -fsSL "$url" -o "$out"
  fi
}

SS_URL="https://github.com/shadowsocks/shadowsocks-rust/releases/download/${SHADOWSOCKS_TAG}/${SHADOWSOCKS_ASSET_WINDOWS}"
SS="$WORK/$SHADOWSOCKS_ASSET_WINDOWS"
fetch "$SS_URL" "$SS"
fetch "${SS_URL}.sha256" "$SS.sha256"
(
  cd "$WORK"
  expected="$(awk '{print $1}' "$SHADOWSOCKS_ASSET_WINDOWS.sha256")"
  if command -v sha256sum >/dev/null 2>&1; then
    echo "$expected  $SHADOWSOCKS_ASSET_WINDOWS" | sha256sum -c -
  else
    actual="$(shasum -a 256 "$SHADOWSOCKS_ASSET_WINDOWS" | awk '{print $1}')"
    [ "$actual" = "$expected" ]
  fi
)
rm -rf "$WORK/sslocal"
mkdir -p "$WORK/sslocal"
unzip -q -o "$SS" -d "$WORK/sslocal"
found="$(find "$WORK/sslocal" -type f -name 'sslocal.exe' | head -n 1)"
[ -n "$found" ]
install -m 0755 "$found" "$BIN/sslocal.exe"

WO="$WORK/$WG_OBFUSCATOR_ASSET_WINDOWS"
fetch "https://github.com/ClusterM/wg-obfuscator/releases/download/${WG_OBFUSCATOR_TAG}/${WG_OBFUSCATOR_ASSET_WINDOWS}" "$WO"
rm -rf "$WORK/wg-obfuscator"
mkdir -p "$WORK/wg-obfuscator"
unzip -q -o "$WO" -d "$WORK/wg-obfuscator"
found="$(find "$WORK/wg-obfuscator" -type f -name 'wg-obfuscator.exe' | head -n 1)"
[ -n "$found" ]
install -m 0755 "$found" "$BIN/wg-obfuscator.exe"

PY="$WORK/$PYTHON_EMBED_WINDOWS"
fetch "https://www.python.org/ftp/python/${PYTHON_EMBED_VERSION}/${PYTHON_EMBED_WINDOWS}" "$PY"

(
  cd "$WINDOWS"
  GOWORK=off CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -ldflags "-s -w -H windowsgui" -o "$STAGE/continuum-vpn-widget.exe" .
)
unzip -q -o "$PY" -d "$STAGE/python"
cp "$UBUNTU/lib/engine.py" "$STAGE/resources/engine.py"
cp "$WINDOWS/lib/priv-helper" "$STAGE/resources/priv-helper"
cp "$UBUNTU/VERSION" "$STAGE/resources/VERSION"
install -m 0755 "$BIN/sslocal.exe" "$BIN/wg-obfuscator.exe" "$STAGE/resources/bin/"
if find "$STAGE" -name 'udp2raw*' | grep -q .; then
  echo "udp2raw must not be bundled in the Windows app" >&2
  exit 1
fi

versioned="$REPO/continuum-vpn-widget-${VERSION}-windows-x64.zip"
alias="$REPO/continuum-vpn-widget-windows-x64.zip"
(
  cd "$WINDOWS/staging"
  rm -f "$versioned" "$alias"
  zip -r -q "$versioned" "Continuum VPN"
)
cp -f "$versioned" "$alias"
echo "$versioned"

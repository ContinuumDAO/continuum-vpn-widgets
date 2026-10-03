#!/bin/sh
# Download the pinned macOS sslocal and wg-obfuscator builds. udp2raw is omitted.
set -eu
MACOS="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
UBUNTU="$(CDPATH= cd -- "$MACOS/../ubuntu" && pwd)"
# shellcheck disable=SC1091
. "$UBUNTU/versions.env"
DEST="$MACOS/third-party/bin"
WORK="$MACOS/third-party/src"
mkdir -p "$DEST/arm64" "$DEST/x64" "$WORK"

fetch() {
  url="$1"
  out="$2"
  if [ ! -f "$out" ]; then
    curl -fsSL "$url" -o "$out"
  fi
}

install_ss() {
  asset="$1"
  arch="$2"
  url="https://github.com/shadowsocks/shadowsocks-rust/releases/download/${SHADOWSOCKS_TAG}/${asset}"
  fetch "$url" "$WORK/$asset"
  fetch "${url}.sha256" "$WORK/$asset.sha256"
  (
    cd "$WORK"
    expected="$(awk '{print $1}' "$asset.sha256")"
    if command -v sha256sum >/dev/null 2>&1; then
      echo "$expected  $asset" | sha256sum -c -
    else
      actual="$(shasum -a 256 "$asset" | awk '{print $1}')"
      [ "$actual" = "$expected" ]
    fi
  )
  tar -xJf "$WORK/$asset" -C "$WORK"
  install -m 0755 "$WORK/sslocal" "$DEST/$arch/sslocal"
  rm -f "$WORK/sslocal"
}

install_wo() {
  asset="$1"
  arch="$2"
  url="https://github.com/ClusterM/wg-obfuscator/releases/download/${WG_OBFUSCATOR_TAG}/${asset}"
  fetch "$url" "$WORK/$asset"
  dir="$WORK/wg-obfuscator-$arch"
  rm -rf "$dir"
  mkdir -p "$dir"
  unzip -q -o "$WORK/$asset" -d "$dir"
  found="$(find "$dir" -type f -name 'wg-obfuscator' | head -n 1)"
  [ -n "$found" ]
  install -m 0755 "$found" "$DEST/$arch/wg-obfuscator"
}

install_ss "$SHADOWSOCKS_ASSET_DARWIN_ARM" arm64
install_ss "$SHADOWSOCKS_ASSET_DARWIN_X64" x64
install_wo "$WG_OBFUSCATOR_ASSET_DARWIN_ARM" arm64
install_wo "$WG_OBFUSCATOR_ASSET_DARWIN_X64" x64
echo "macOS obfuscators in $DEST"

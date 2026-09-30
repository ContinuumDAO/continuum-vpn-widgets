#!/bin/sh
# Download the pinned obfuscator binaries into ubuntu/third-party/bin.
set -eu
ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
. "$ROOT/versions.env"
DEST="$ROOT/third-party/bin"
WORK="$ROOT/third-party/src"
mkdir -p "$DEST" "$WORK"

fetch() {
  url="$1"
  out="$2"
  if [ ! -f "$out" ]; then
    curl -fsSL "$url" -o "$out"
  fi
}

SS_URL="https://github.com/shadowsocks/shadowsocks-rust/releases/download/${SHADOWSOCKS_TAG}/${SHADOWSOCKS_ASSET}"
SS_SUM_URL="${SS_URL}.sha256"
fetch "$SS_URL" "$WORK/$SHADOWSOCKS_ASSET"
fetch "$SS_SUM_URL" "$WORK/$SHADOWSOCKS_ASSET.sha256"
(
  cd "$WORK"
  expected="$(awk '{print $1}' "$SHADOWSOCKS_ASSET.sha256")"
  echo "$expected  $SHADOWSOCKS_ASSET" | sha256sum -c -
)
tar -xJf "$WORK/$SHADOWSOCKS_ASSET" -C "$WORK"
install -m 0755 "$WORK/sslocal" "$DEST/sslocal"

WO_URL="https://github.com/ClusterM/wg-obfuscator/releases/download/${WG_OBFUSCATOR_TAG}/${WG_OBFUSCATOR_ASSET}"
fetch "$WO_URL" "$WORK/$WG_OBFUSCATOR_ASSET"
rm -rf "$WORK/wg-obfuscator"
mkdir -p "$WORK/wg-obfuscator"
tar -xzf "$WORK/$WG_OBFUSCATOR_ASSET" -C "$WORK/wg-obfuscator"
found="$(find "$WORK/wg-obfuscator" -type f -name 'wg-obfuscator' | head -n 1)"
[ -n "$found" ]
install -m 0755 "$found" "$DEST/wg-obfuscator"
curl -fsSL "https://raw.githubusercontent.com/ClusterM/wg-obfuscator/${WG_OBFUSCATOR_TAG}/LICENSE" -o "$ROOT/third-party/wg-obfuscator-LICENSE"

U2_URL="https://github.com/wangyu-/udp2raw/releases/download/${UDP2RAW_TAG}/${UDP2RAW_ASSET}"
fetch "$U2_URL" "$WORK/$UDP2RAW_ASSET"
rm -rf "$WORK/udp2raw"
mkdir -p "$WORK/udp2raw"
tar -xzf "$WORK/$UDP2RAW_ASSET" -C "$WORK/udp2raw"
found="$(find "$WORK/udp2raw" -type f -name "$UDP2RAW_INNER" | head -n 1)"
[ -n "$found" ]
install -m 0755 "$found" "$DEST/udp2raw"

echo "obfuscators in $DEST"

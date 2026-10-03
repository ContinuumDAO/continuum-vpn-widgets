#!/bin/sh
# Cross-compile wireguard-go for Apple silicon and Intel.
set -eu
MACOS="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
UBUNTU="$(CDPATH= cd -- "$MACOS/../ubuntu" && pwd)"
# shellcheck disable=SC1091
. "$UBUNTU/versions.env"
SRC="$MACOS/third-party/src/wireguard-go"
DEST="$MACOS/third-party/bin"
mkdir -p "$DEST/arm64" "$DEST/x64"
if [ ! -d "$SRC/.git" ]; then
  rm -rf "$SRC"
  git clone --depth 1 --branch "$WIREGUARD_GO_TAG" https://github.com/WireGuard/wireguard-go.git "$SRC"
fi
(
  cd "$SRC"
  GOWORK=off GOOS=darwin GOARCH=arm64 CGO_ENABLED=0 go build -trimpath -ldflags '-s -w' -o "$DEST/arm64/wireguard-go" .
  GOWORK=off GOOS=darwin GOARCH=amd64 CGO_ENABLED=0 go build -trimpath -ldflags '-s -w' -o "$DEST/x64/wireguard-go" .
)
echo "wireguard-go in $DEST"

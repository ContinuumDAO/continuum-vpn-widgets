#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$ROOT/tests/bin:$PATH"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT
export CONTINUUM_VPN_CONFIG_DIR="$WORKDIR/config"
export CONTINUUM_VPN_RUNTIME_DIR="$WORKDIR/run"
export CONTINUUM_VPN_NM_STATE="$WORKDIR/nm"
export CONTINUUM_VPN_LISTEN_DIR="$WORKDIR/listen"
export CONTINUUM_VPN_IP_LOG="$WORKDIR/ip.log"
export CONTINUUM_VPN_NO_PRIV=1
export CONTINUUM_VPN_BIN_DIR="$WORKDIR/lib/bin"
export CONTINUUM_VPN_HELPER="$WORKDIR/lib/priv-helper"
mkdir -p "$CONTINUUM_VPN_CONFIG_DIR" "$CONTINUUM_VPN_RUNTIME_DIR" "$CONTINUUM_VPN_NM_STATE" "$CONTINUUM_VPN_LISTEN_DIR" "$WORKDIR/lib/bin"
cp "$ROOT/lib/priv-helper" "$CONTINUUM_VPN_HELPER"
cp "$ROOT/tests/bin/sslocal" "$ROOT/tests/bin/wg-obfuscator" "$ROOT/tests/bin/udp2raw" "$CONTINUUM_VPN_BIN_DIR/"
chmod 755 "$CONTINUUM_VPN_HELPER" "$CONTINUUM_VPN_BIN_DIR/"*

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

printf '%s\n' '#!/bin/sh' 'echo hi' >"$WORKDIR/evil.sh"
assert_fail "shell script" "${ENGINE[@]}" import-file "$WORKDIR/evil.sh"

# Hooks are stripped, not executed. A WireGuard config with PostUp still imports.
HOOK_LABEL="$("${ENGINE[@]}" import-text "cont-full.conf" <<EOF
[Interface]
PrivateKey = $PRIV
Address = 10.8.0.2/32
PostUp = curl evil.example
[Peer]
PublicKey = $PUB
Endpoint = 198.51.100.8:51820
AllowedIPs = 0.0.0.0/0
EOF
)"
[[ "$HOOK_LABEL" == "cont-full" ]]
if grep -q 'PostUp' "$CONTINUUM_VPN_CONFIG_DIR/profiles/cont-full/wg.conf"; then
  echo "hook line was stored" >&2
  exit 1
fi

# A pasted WireGuard config is stored under its endpoint, so a second node
# does not overwrite the first. The node's continuum-vpn-<iface>.json keeps
# the iface from the bundle.
PASTE_LABEL="$("${ENGINE[@]}" import-text "pasted.conf" <<EOF
[Interface]
PrivateKey = $PRIV
Address = 10.8.0.2/32
[Peer]
PublicKey = $PUB
Endpoint = 203.0.113.9:51820
AllowedIPs = 0.0.0.0/0
EOF
)"
[[ "$PASTE_LABEL" == "203.0.113.9" ]]
test -f "$CONTINUUM_VPN_CONFIG_DIR/profiles/203.0.113.9/meta.json"

NODEB="$WORKDIR/continuum-vpn-cont-full.json"
python3 - "$NODEB" "$PRIV" "$PUB" <<'PY'
import json, sys
path, priv, pub = sys.argv[1:]
json.dump({
  "label": "Full tunnel",
  "source": "admin",
  "obfuscation": "none",
  "iface": "cont-full",
  "detail": "WireGuard, with ad/tracking blocking with Blocky",
  "wireGuardConfig": f"[Interface]\nPrivateKey = {priv}\nAddress = 10.8.0.2/32\n[Peer]\nPublicKey = {pub}\nEndpoint = 198.51.100.8:51820\nAllowedIPs = 0.0.0.0/0\n",
}, open(path, "w"))
PY
[[ "$("${ENGINE[@]}" import-file "$NODEB")" == "Full tunnel" ]]
test -f "$CONTINUUM_VPN_CONFIG_DIR/profiles/cont-full/meta.json"
test -f "$CONTINUUM_VPN_CONFIG_DIR/profiles/203.0.113.9/meta.json"

SHELLB="$WORKDIR/shell.json"
python3 - "$SHELLB" "$PRIV" "$PUB" <<'PY'
import json, sys
path, priv, pub = sys.argv[1:]
json.dump({
  "label": "bad",
  "source": "egress",
  "obfuscation": "udp2raw",
  "iface": "10.1.1.1",
  "wireGuardConfig": f"[Interface]\nPrivateKey = {priv}\nAddress = 10.8.0.2/32\n[Peer]\nPublicKey = {pub}\nEndpoint = 127.0.0.1:1\nAllowedIPs = 0.0.0.0/0\n",
  "transportBinary": "udp2raw",
  "transportFilename": "10.1.1.1-u2r.sh",
  "transportConfig": "#!/bin/sh\necho hi\n",
}, open(path, "w"))
PY
assert_fail "shell script" "${ENGINE[@]}" import-file "$SHELLB"

LWO="$WORKDIR/lwo.json"
python3 - "$LWO" "$PRIV" "$PUB" <<'PY'
import json, sys
path, priv, pub = sys.argv[1:]
json.dump({
  "label": "lwo",
  "source": "admin",
  "obfuscation": "lwo",
  "iface": "cont-lwo",
  "wireGuardConfig": f"[Interface]\nPrivateKey = {priv}\nAddress = 10.8.0.2/32\n[Peer]\nPublicKey = {pub}\nEndpoint = 127.0.0.1:1\nAllowedIPs = 0.0.0.0/0\n",
}, open(path, "w"))
PY
assert_fail "lwo is not started" "${ENGINE[@]}" import-file "$LWO"

BUNDLE="$WORKDIR/exit.json"
python3 - "$BUNDLE" "$PRIV" "$PUB" <<'PY'
import json, sys
path, priv, pub = sys.argv[1:]
json.dump({
  "label": "Frankfurt",
  "countryCode": "de",
  "detail": "WireGuard, with Shadowsocks and ad/tracking blocking with Blocky",
  "source": "egress",
  "obfuscation": "shadowsocks",
  "iface": "1.2.3.4",
  "wireGuardConfig": f"[Interface]\nPrivateKey = {priv}\nAddress = 10.8.0.2/32\nDNS = 10.8.0.1\n[Peer]\nPublicKey = {pub}\nEndpoint = 127.0.0.1:51821\nAllowedIPs = 0.0.0.0/0\n",
  "transportBinary": "sslocal",
  "transportFilename": "1.2.3.4-ss.json",
  "transportConfig": '{"server": "203.0.113.5", "server_port": 8388, "local_port": 51821, "password": "secret", "method": "chacha20-ietf-poly1305"}\n',
}, open(path, "w"))
PY
[[ "$("${ENGINE[@]}" import-file "$BUNDLE")" == "Frankfurt" ]]

U2R="$WORKDIR/u2r.json"
python3 - "$U2R" "$PRIV" "$PUB" <<'PY'
import json, sys
path, priv, pub = sys.argv[1:]
json.dump({
  "label": "Raw exit",
  "countryCode": "jp",
  "detail": "WireGuard, with udp2raw",
  "source": "egress",
  "obfuscation": "udp2raw",
  "iface": "eg-aabbccddeeff",
  "wireGuardConfig": f"[Interface]\nPrivateKey = {priv}\nAddress = 10.8.0.2/32\nPreUp = ip route add 198.51.100.9/32 via 192.0.2.1\n[Peer]\nPublicKey = {pub}\nEndpoint = 127.0.0.1:51821\nAllowedIPs = 0.0.0.0/0\n",
  "transportBinary": "udp2raw",
  "transportFilename": "eg-aabbccddeeff-u2r.json",
  "transportConfig": json.dumps({
    "localHost": "127.0.0.1",
    "localPort": 51821,
    "remoteHost": "198.51.100.9",
    "remotePort": 4096,
    "password": "s3cret",
    "rawMode": "faketcp",
  }),
}, open(path, "w"))
PY
[[ "$("${ENGINE[@]}" import-file "$U2R")" == "Raw exit" ]]
if grep -q 'PreUp' "$CONTINUUM_VPN_CONFIG_DIR/profiles/eg-aabbccddeeff/wg.conf"; then
  echo "udp2raw hook was stored" >&2
  exit 1
fi

ROWS="$("${ENGINE[@]}" list)"
python3 - "$ROWS" <<'PY'
import json, sys
rows = {row["iface"]: row for row in json.loads(sys.argv[1])}
ss = rows["1.2.3.4"]
assert ss["label"] == "Frankfurt"
assert ss["countryCode"] == "DE"
assert ss["countryFlag"] == "🇩🇪"
assert "Shadowsocks" in ss["detail"]
assert ss["active"] is False
assert rows["eg-aabbccddeeff"]["obfuscation"] == "udp2raw"
PY

[[ "$("${ENGINE[@]}" up 1.2.3.4)" == "Frankfurt" ]]
python3 - "$("${ENGINE[@]}" list)" <<'PY'
import json, sys
rows = {row["iface"]: row for row in json.loads(sys.argv[1])}
assert rows["1.2.3.4"]["active"] is True
PY
grep -q '203.0.113.5/32' "$CONTINUUM_VPN_IP_LOG"

[[ "$("${ENGINE[@]}" up eg-aabbccddeeff)" == "Raw exit" ]]
python3 - "$("${ENGINE[@]}" list)" <<'PY'
import json, sys
rows = {row["iface"]: row for row in json.loads(sys.argv[1])}
assert rows["1.2.3.4"]["active"] is False
assert rows["eg-aabbccddeeff"]["active"] is True
PY
grep -q '198.51.100.9/32' "$CONTINUUM_VPN_IP_LOG"
if ps -ef | grep -q '[c]url evil'; then
  echo "a hook command was executed" >&2
  exit 1
fi

"${ENGINE[@]}" down eg-aabbccddeeff >/dev/null
"${ENGINE[@]}" down 1.2.3.4 >/dev/null
echo "ok"

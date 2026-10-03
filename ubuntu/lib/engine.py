#!/usr/bin/env python3
"""Continuum VPN widget engine.

Imports the same profile bundle as the Omarchy plugin. NetworkManager owns the
tunnel. Transport programs are the binaries shipped with this package.
Downloaded shell is never executed. WireGuard hook lines are removed before
import and are never run.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

IFACE_RE = re.compile(r"^[A-Za-z0-9_=+.\-]{1,15}$")
ALLOWED_INTERFACE = {
    "PrivateKey",
    "Address",
    "DNS",
    "ListenPort",
    "MTU",
    "FwMark",
    "Table",
}
ALLOWED_PEER = {
    "PublicKey",
    "PresharedKey",
    "AllowedIPs",
    "Endpoint",
    "PersistentKeepalive",
}
HOOKS = {"preup", "postup", "predown", "postdown"}
HOST_RE = re.compile(r"^[A-Za-z0-9.:-]{1,253}$")
RELEASE_API = "https://api.github.com/repos/ContinuumDAO/continuum-vpn-widgets/releases/latest"
DEB_ASSET = "continuum-vpn-widget_amd64.deb"
PKG_ASSET = "continuum-vpn-widget-x86_64.pkg.tar.zst"

LIB_DIR = os.path.dirname(os.path.realpath(__file__))


class EngineError(Exception):
    pass


def fail(message: str) -> None:
    raise EngineError(message)


def config_dir() -> str:
    override = os.environ.get("CONTINUUM_VPN_CONFIG_DIR")
    if override:
        return override
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "continuum-vpn")


def runtime_dir() -> str:
    override = os.environ.get("CONTINUUM_VPN_RUNTIME_DIR")
    if override:
        return override
    base = os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/continuum-vpn-{os.getuid()}"
    return os.path.join(base, "continuum-vpn")


def bin_dir() -> str:
    override = os.environ.get("CONTINUUM_VPN_BIN_DIR")
    if override:
        return override
    return os.path.join(LIB_DIR, "bin")


def helper_path() -> str:
    override = os.environ.get("CONTINUUM_VPN_HELPER")
    if override:
        return override
    return os.path.join(LIB_DIR, "priv-helper")


def installed_version() -> str:
    candidates = [
        os.path.join(LIB_DIR, "VERSION"),
        os.path.join(LIB_DIR, "..", "VERSION"),
    ]
    for path in candidates:
        try:
            with open(path, encoding="utf-8") as handle:
                text = handle.read().strip()
            if text:
                return text
        except OSError:
            continue
    return "0.0.0"


def ensure_dirs() -> tuple[str, str, str]:
    root = config_dir()
    profiles = os.path.join(root, "profiles")
    runtime = runtime_dir()
    for path in (root, profiles, runtime):
        if not os.path.isdir(path):
            os.makedirs(path, mode=0o700, exist_ok=True)
        # chmod changes the directory ctime. Doing that on every refresh makes
        # the desktop notice the widget several times a minute.
        if os.stat(path).st_mode & 0o777 != 0o700:
            os.chmod(path, 0o700)
    return root, profiles, runtime


def detail_text(value: Any) -> str:
    text = " ".join(str(value or "").split())
    return text[:180].rstrip()


def country_code(value: Any) -> str:
    if value is None or str(value).strip() == "":
        return ""
    code = str(value).strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", code):
        fail("countryCode must be an ISO 3166-1 alpha-2 code")
    return code


def flag_for(code: str) -> str:
    if len(code) != 2 or not code.isalpha():
        return ""
    return chr(0x1F1E6 + ord(code[0]) - ord("A")) + chr(0x1F1E6 + ord(code[1]) - ord("A"))


def wg_assignment(text: str, key: str) -> str:
    wanted = key.lower()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip().lower() == wanted:
            return value.strip()
    return ""


def rate_label(detail: str) -> str:
    match = re.search(r"limited to ([0-9]+(?:\.[0-9]+)?) Mbps", detail)
    if not match:
        return ""
    return f"{match.group(1)} Mbps"


def ad_block_label(detail: str) -> str:
    match = re.search(r"ad/tracking blocking with ([A-Za-z0-9.+-]+)", detail)
    if not match:
        return ""
    return match.group(1)


def check_private_key(key: str) -> None:
    try:
        subprocess.run(
            ["wg", "pubkey"],
            input=(key.strip() + "\n").encode(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=True,
        )
    except FileNotFoundError:
        fail("wireguard-tools (wg) is required to validate keys")
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode(errors="replace").strip()
        fail(detail or "private key was rejected by wg pubkey")


def check_public_key(key: str) -> None:
    try:
        raw = base64.b64decode(key.strip(), validate=True)
    except Exception:
        fail("peer key is not valid base64")
    if len(raw) != 32:
        fail("peer key is not a WireGuard key")


def parse_wg(text: str) -> dict[str, Any]:
    section = None
    interface: dict[str, str] = {}
    peers: list[dict[str, str]] = []
    kept: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            kept.append(raw)
            continue
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1].strip().lower()
            if name == "interface":
                if interface:
                    fail("config has more than one [Interface]")
                section = "interface"
            elif name == "peer":
                peers.append({})
                section = "peer"
            else:
                fail(f"unknown section [{line[1:-1].strip()}]")
            kept.append(raw)
            continue
        if "=" not in line or section is None:
            fail(f"invalid line: {line}")
        key, value = line.split("=", 1)
        key_stripped = key.strip()
        value = value.strip()
        if key_stripped.lower() in HOOKS:
            continue
        if section == "interface":
            if key_stripped not in ALLOWED_INTERFACE:
                fail(f"unknown interface key {key_stripped}")
            if key_stripped in interface:
                fail(f"duplicate interface key {key_stripped}")
            interface[key_stripped] = value
        else:
            if key_stripped not in ALLOWED_PEER:
                fail(f"unknown peer key {key_stripped}")
            peer = peers[-1]
            if key_stripped in peer:
                fail(f"duplicate peer key {key_stripped}")
            peer[key_stripped] = value
        kept.append(raw)
    if "PrivateKey" not in interface:
        fail("interface is missing PrivateKey")
    if not peers or any("PublicKey" not in peer for peer in peers):
        fail("a peer PublicKey is required")
    check_private_key(interface["PrivateKey"])
    for peer in peers:
        check_public_key(peer["PublicKey"])
        if "PresharedKey" in peer:
            check_public_key(peer["PresharedKey"])
    body = "\n".join(kept)
    if not body.endswith("\n"):
        body += "\n"
    return {"interface": interface, "peers": peers, "text": body}


def looks_like_shell(text: str, filename: str) -> bool:
    if text.lstrip().startswith("#!"):
        return True
    return filename.endswith(".sh")


def full_tunnel(parsed: dict[str, Any]) -> bool:
    for peer in parsed["peers"]:
        allowed = peer.get("AllowedIPs", "")
        parts = [item.strip() for item in allowed.split(",")]
        if "0.0.0.0/0" in parts or "::/0" in parts:
            return True
    return False


def bundled_binary(name: str) -> str:
    mapping = {
        "sslocal": "sslocal",
        "shadowsocks-rust.sslocal": "sslocal",
        "wg-obfuscator": "wg-obfuscator",
        "udp2raw": "udp2raw",
    }
    filename = mapping.get(name)
    if not filename:
        fail(f"transport binary {name or '(missing)'} is not allowed")
    path = os.path.join(bin_dir(), filename)
    if not os.path.isfile(path) or not os.access(path, os.X_OK):
        fail(f"{filename} is not installed with Continuum VPN")
    return path


def parse_udp2raw_transport(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        fail(f"udp2raw transport is not JSON: {exc.msg}")
    if not isinstance(data, dict):
        fail("udp2raw transport must be a JSON object")
    local_host = str(data.get("localHost") or "")
    remote_host = str(data.get("remoteHost") or "")
    password = data.get("password")
    raw_mode = str(data.get("rawMode") or "")
    try:
        local_port = int(data.get("localPort"))
        remote_port = int(data.get("remotePort"))
    except (TypeError, ValueError):
        fail("udp2raw ports must be integers")
    if local_host != "127.0.0.1":
        fail("udp2raw localHost must be 127.0.0.1")
    if raw_mode != "faketcp":
        fail("udp2raw rawMode must be faketcp")
    if not (1 <= local_port <= 65535 and 1 <= remote_port <= 65535):
        fail("udp2raw port is out of range")
    if not isinstance(password, str) or password == "" or "\n" in password or "\x00" in password:
        fail("udp2raw password is missing")
    if not HOST_RE.fullmatch(remote_host) or ".." in remote_host or remote_host.startswith("-"):
        fail("udp2raw remoteHost is not a host name or address")
    return {
        "localHost": local_host,
        "localPort": local_port,
        "remoteHost": remote_host,
        "remotePort": remote_port,
        "password": password,
        "rawMode": "faketcp",
    }


def shadowsocks_fields(text: str) -> tuple[str, int]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        fail(f"shadowsocks transport is not JSON: {exc.msg}")
    if not isinstance(data, dict):
        fail("shadowsocks transport must be a JSON object")
    server = str(data.get("server") or "")
    port = data.get("local_port")
    if port is None and isinstance(data.get("locals"), list) and data["locals"]:
        port = data["locals"][0].get("local_port")
    try:
        local_port = int(port)
    except (TypeError, ValueError):
        fail("shadowsocks config is missing local_port")
    if not server or not HOST_RE.fullmatch(server):
        fail("shadowsocks config is missing server")
    return server, local_port


def wg_obfuscator_fields(text: str) -> tuple[str, int]:
    source_port = None
    target = ""
    for raw in text.splitlines():
        line = raw.strip()
        if line.lower().startswith("source-lport"):
            source_port = line.split("=", 1)[1].strip()
        elif line.lower().startswith("target"):
            target = line.split("=", 1)[1].strip()
    try:
        local_port = int(source_port)
    except (TypeError, ValueError):
        fail("wg-obfuscator config is missing source-lport")
    host, sep, port = target.rpartition(":")
    if not sep:
        fail("wg-obfuscator config is missing target")
    host = host.strip().strip("[]")
    try:
        int(port)
    except ValueError:
        fail("wg-obfuscator target port is invalid")
    if not HOST_RE.fullmatch(host):
        fail("wg-obfuscator target host is invalid")
    return host, local_port


def bundle_from_json(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        fail(f"bundle is not valid JSON: {exc.msg}")
    if not isinstance(data, dict):
        fail("bundle must be a JSON object")
    obfuscation = str(data.get("obfuscation") or "none").strip().lower().replace("-", "_")
    if obfuscation == "lwo":
        fail("lwo is not started by this widget")
    if obfuscation not in {"none", "shadowsocks", "wg_obfuscator", "udp2raw"}:
        fail(f"unsupported obfuscation {obfuscation}")
    iface = str(data.get("iface") or "").strip()
    if not IFACE_RE.fullmatch(iface):
        fail("iface must be 1-15 characters from [A-Za-z0-9_=+.-]")
    label = str(data.get("label") or iface).replace("\n", " ").strip() or iface
    source = str(data.get("source") or "admin").strip()
    if source not in {"admin", "egress"}:
        fail("source must be admin or egress")
    wg_text = str(data.get("wireGuardConfig") or "")
    if not wg_text.strip():
        fail("bundle is missing wireGuardConfig")
    parsed = parse_wg(wg_text)
    transport_text = str(data.get("transportConfig") or "")
    transport_name = str(data.get("transportFilename") or "")
    transport_bin = str(data.get("transportBinary") or "").strip()
    remote_host = ""
    local_port = 0
    udp2raw: dict[str, Any] | None = None
    if looks_like_shell(transport_text, transport_name):
        fail("refusing to store a shell script")
    if obfuscation == "none":
        if transport_text.strip() or transport_bin:
            fail("plain profile includes a transport")
        transport_text = ""
        transport_bin = ""
        transport_name = ""
    elif obfuscation == "shadowsocks":
        if transport_bin not in {"sslocal", "shadowsocks-rust.sslocal"}:
            fail(f"transport binary {transport_bin or '(missing)'} is not allowed")
        if not transport_text.strip():
            fail("obfuscated profile is missing transportConfig")
        remote_host, local_port = shadowsocks_fields(transport_text)
        transport_name = f"{iface}-ss.json"
        transport_bin = "sslocal"
    elif obfuscation == "wg_obfuscator":
        if transport_bin != "wg-obfuscator":
            fail(f"transport binary {transport_bin or '(missing)'} is not allowed")
        if not transport_text.strip():
            fail("obfuscated profile is missing transportConfig")
        remote_host, local_port = wg_obfuscator_fields(transport_text)
        transport_name = f"{iface}-wgo.conf"
        transport_bin = "wg-obfuscator"
    else:
        if transport_bin != "udp2raw":
            fail(f"transport binary {transport_bin or '(missing)'} is not allowed")
        udp2raw = parse_udp2raw_transport(transport_text)
        remote_host = str(udp2raw["remoteHost"])
        local_port = int(udp2raw["localPort"])
        transport_name = f"{iface}-u2r.json"
        transport_text = json.dumps(udp2raw, indent=2) + "\n"
        transport_bin = "udp2raw"
    return {
        "label": label,
        "countryCode": country_code(data.get("countryCode")),
        "detail": detail_text(data.get("detail")),
        "source": source,
        "obfuscation": obfuscation,
        "iface": iface,
        "wireGuardConfig": parsed["text"],
        "fullTunnel": full_tunnel(parsed),
        "remoteHost": remote_host,
        "localPort": local_port,
        "transportBinary": transport_bin,
        "transportFilename": transport_name,
        "transportConfig": transport_text if transport_text.endswith("\n") or not transport_text else transport_text + "\n",
        "udp2raw": udp2raw,
    }


def iface_from_endpoint(parsed: dict[str, Any]) -> tuple[str, str]:
    endpoint = ""
    for peer in parsed["peers"]:
        if peer.get("Endpoint"):
            endpoint = str(peer["Endpoint"])
    host = endpoint.rsplit(":", 1)[0].strip().strip("[]")
    label = host or "WireGuard"
    cleaned = re.sub(r"[^A-Za-z0-9_=+.\-]", "", host)
    if IFACE_RE.fullmatch(cleaned) and cleaned[:1].isalnum():
        return cleaned, label
    digest = hashlib.sha256((host or endpoint or "wireguard").encode()).hexdigest()[:12]
    return f"wg-{digest}", label


def bundle_from_conf(text: str, filename: str) -> dict[str, Any]:
    if looks_like_shell(text, filename):
        fail("refusing to import a shell script")
    parsed = parse_wg(text)
    stem = os.path.splitext(os.path.basename(filename))[0]
    label = stem
    if stem in {"", "pasted"} or not IFACE_RE.fullmatch(stem):
        stem, label = iface_from_endpoint(parsed)
    if not IFACE_RE.fullmatch(stem):
        fail("config filename must be an interface name of 1-15 characters from [A-Za-z0-9_=+.-]")
    return {
        "label": label,
        "countryCode": "",
        "detail": "",
        "source": "admin",
        "obfuscation": "none",
        "iface": stem,
        "wireGuardConfig": parsed["text"],
        "fullTunnel": full_tunnel(parsed),
        "remoteHost": "",
        "localPort": 0,
        "transportBinary": "",
        "transportFilename": "",
        "transportConfig": "",
        "udp2raw": None,
    }


def write_profile(profile: dict[str, Any], profiles: str) -> str:
    iface = profile["iface"]
    final = os.path.join(profiles, iface)
    parent = os.path.dirname(final)
    os.makedirs(parent, mode=0o700, exist_ok=True)
    os.chmod(parent, 0o700)
    tmp = tempfile.mkdtemp(prefix=f".{iface}.", dir=parent)
    os.chmod(tmp, 0o700)
    try:
        wg_path = os.path.join(tmp, "wg.conf")
        with open(wg_path, "w", encoding="utf-8") as handle:
            handle.write(profile["wireGuardConfig"])
        os.chmod(wg_path, 0o600)
        if profile["transportConfig"]:
            transport_path = os.path.join(tmp, profile["transportFilename"])
            with open(transport_path, "w", encoding="utf-8") as handle:
                handle.write(profile["transportConfig"])
            os.chmod(transport_path, 0o600)
        meta = {
            "label": profile["label"],
            "countryCode": profile.get("countryCode") or "",
            "detail": profile.get("detail") or "",
            "source": profile["source"],
            "obfuscation": profile["obfuscation"],
            "iface": iface,
            "transportBinary": profile["transportBinary"],
            "transportFilename": profile["transportFilename"],
            "fullTunnel": bool(profile.get("fullTunnel")),
            "remoteHost": profile.get("remoteHost") or "",
            "localPort": profile.get("localPort") or 0,
            "nmUuid": "",
            "bypassHost": "",
        }
        meta_path = os.path.join(tmp, "meta.json")
        with open(meta_path, "w", encoding="utf-8") as handle:
            json.dump(meta, handle, indent=2)
            handle.write("\n")
        os.chmod(meta_path, 0o600)
        if os.path.isdir(final):
            shutil.rmtree(final)
        os.rename(tmp, final)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return final


def load_meta(profiles: str, iface: str) -> tuple[str, dict[str, Any]]:
    directory = os.path.join(profiles, iface)
    path = os.path.join(directory, "meta.json")
    if not os.path.isfile(path):
        fail(f"unknown profile {iface}")
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    return directory, data


def save_meta(directory: str, meta: dict[str, Any]) -> None:
    path = os.path.join(directory, "meta.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(meta, handle, indent=2)
        handle.write("\n")
    os.chmod(path, 0o600)


def nm(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    slow = len(args) >= 2 and args[0] == "connection" and args[1] in {"up", "down", "import", "delete", "modify"}
    try:
        return subprocess.run(
            ["nmcli", *args],
            check=check,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=45 if slow else 8,
        )
    except subprocess.TimeoutExpired:
        fail("NetworkManager did not respond")


def import_staged(profile_dir: str, meta: dict[str, Any]) -> str:
    iface = str(meta["iface"])
    label = str(meta["label"])
    old = str(meta.get("nmUuid") or "")
    if old:
        nm("connection", "delete", old, check=False)
    listed = nm("-t", "-f", "UUID,TYPE", "connection", "show", check=False)
    for line in listed.stdout.splitlines():
        uuid, _, typ = line.partition(":")
        if typ != "wireguard" or not uuid:
            continue
        ifn = nm("-g", "connection.interface-name", "connection", "show", uuid, check=False).stdout.strip()
        name = nm("-g", "connection.id", "connection", "show", uuid, check=False).stdout.strip()
        if ifn == iface or name == iface or name == label:
            nm("connection", "delete", uuid, check=False)
    _, _, runtime = ensure_dirs()
    stage = tempfile.mkdtemp(prefix="import.", dir=runtime)
    os.chmod(stage, 0o700)
    try:
        dest = os.path.join(stage, f"{iface}.conf")
        shutil.copyfile(os.path.join(profile_dir, "wg.conf"), dest)
        os.chmod(dest, 0o600)
        imported = nm("connection", "import", "type", "wireguard", "file", dest, check=False)
        if imported.returncode != 0:
            fail(imported.stderr.strip() or "NetworkManager did not import the tunnel")
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    shown = nm("-g", "connection.uuid", "connection", "show", iface, check=False)
    uuid = shown.stdout.strip()
    if not uuid:
        fail("NetworkManager did not return a connection uuid")
    modified = nm(
        "connection",
        "modify",
        uuid,
        "connection.id",
        label,
        "connection.interface-name",
        iface,
        "connection.autoconnect",
        "no",
        check=False,
    )
    if modified.returncode != 0:
        fail(modified.stderr.strip() or "NetworkManager did not update the connection")
    # Import brings a WireGuard profile up. Leave it saved until the user connects.
    nm("connection", "down", uuid, check=False)
    meta["nmUuid"] = uuid
    save_meta(profile_dir, meta)
    return label


def import_text(text: str, filename: str = "pasted.conf") -> str:
    text = text.lstrip("\ufeff")
    if not text.strip():
        fail("empty config")
    _, profiles, _ = ensure_dirs()
    if text.lstrip().startswith("{"):
        profile = bundle_from_json(text)
    else:
        profile = bundle_from_conf(text, filename)
    directory = write_profile(profile, profiles)
    meta_path = os.path.join(directory, "meta.json")
    with open(meta_path, encoding="utf-8") as handle:
        meta = json.load(handle)
    return import_staged(directory, meta)


def import_file(path: str) -> str:
    if not os.path.isfile(path):
        fail("file not found")
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    return import_text(text, os.path.basename(path))


def connection_active(uuid: str) -> bool:
    if not uuid:
        return False
    state = nm("-g", "GENERAL.STATE", "connection", "show", uuid, check=False)
    return state.returncode == 0 and state.stdout.startswith("activated")


def list_profiles() -> list[dict[str, Any]]:
    _, profiles, _ = ensure_dirs()
    rows = []
    if not os.path.isdir(profiles):
        return rows
    for name in sorted(os.listdir(profiles)):
        meta_path = os.path.join(profiles, name, "meta.json")
        if not os.path.isfile(meta_path):
            continue
        with open(meta_path, encoding="utf-8") as handle:
            meta = json.load(handle)
        code = str(meta.get("countryCode") or "")
        detail = str(meta.get("detail") or "").strip()
        wg_text = ""
        wg_path = os.path.join(profiles, name, "wg.conf")
        if os.path.isfile(wg_path):
            with open(wg_path, encoding="utf-8") as handle:
                wg_text = handle.read()
        rows.append(
            {
                "iface": meta.get("iface") or name,
                "label": meta.get("label") or name,
                "countryCode": code,
                "countryFlag": flag_for(code),
                "detail": detail,
                "obfuscation": meta.get("obfuscation") or "none",
                "adBlock": ad_block_label(detail),
                "rateLimit": rate_label(detail),
                "endpoint": wg_assignment(wg_text, "Endpoint"),
                "active": connection_active(str(meta.get("nmUuid") or "")),
            }
        )
    return rows


def port_listening(port: int) -> bool:
    probe = subprocess.run(
        ["ss", "-l", "-n", "-H", f"sport = :{port}"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return probe.returncode == 0 and bool(probe.stdout.strip())


def stop_proxy(iface: str) -> None:
    _, _, runtime = ensure_dirs()
    pidfile = os.path.join(runtime, f"{iface}.pid")
    if not os.path.isfile(pidfile):
        return
    try:
        pid = int(open(pidfile, encoding="utf-8").read().strip() or "0")
    except ValueError:
        pid = 0
    if pid > 0:
        try:
            os.kill(pid, 15)
        except OSError:
            pass
        for _ in range(20):
            try:
                os.kill(pid, 0)
            except OSError:
                break
            subprocess.run(["sleep", "0.1"], check=False)
        try:
            os.kill(pid, 9)
        except OSError:
            pass
    try:
        os.remove(pidfile)
    except OSError:
        pass


def start_user_proxy(iface: str, binary_name: str, transport: str, port: int) -> None:
    _, _, runtime = ensure_dirs()
    binary = bundled_binary(binary_name)
    log = os.path.join(runtime, f"{iface}.log")
    pidfile = os.path.join(runtime, f"{iface}.pid")
    if binary_name in {"sslocal", "shadowsocks-rust.sslocal"}:
        argv = [binary, "-c", transport]
    elif binary_name == "wg-obfuscator":
        argv = [binary, "--config", transport]
    else:
        fail(f"refusing to run {binary_name}")
    with open(log, "ab") as handle:
        proc = subprocess.Popen(
            argv,
            stdout=handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    with open(pidfile, "w", encoding="utf-8") as handle:
        handle.write(str(proc.pid))
    for _ in range(50):
        if port_listening(port):
            return
        if proc.poll() is not None:
            fail(f"{os.path.basename(binary)} exited before it listened on port {port}")
        subprocess.run(["sleep", "0.1"], check=False)
    stop_proxy(iface)
    fail(f"{os.path.basename(binary)} did not listen on port {port}")


def run_helper(command: str, payload: dict[str, Any]) -> None:
    _, _, runtime = ensure_dirs()
    fd, path = tempfile.mkstemp(prefix=f"{command}.", suffix=".json", dir=runtime)
    os.close(fd)
    os.chmod(path, 0o600)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
        handle.write("\n")
    os.chmod(path, 0o600)
    helper = helper_path()
    if not os.path.isfile(helper):
        fail("privileged helper is not installed")
    cmd = [helper, command, path]
    if os.environ.get("CONTINUUM_VPN_NO_PRIV") != "1":
        cmd = ["pkexec", *cmd]
    result = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        fail(detail or f"{command} failed")


def active_wg_uuids() -> list[str]:
    listed = nm("-t", "-f", "UUID,TYPE", "connection", "show", "--active", check=False)
    found = []
    for line in listed.stdout.splitlines():
        uuid, _, typ = line.partition(":")
        if typ == "wireguard" and uuid:
            found.append(uuid)
    return found


def down_profile(iface: str, *, missing_ok: bool = False) -> str:
    _, profiles, _ = ensure_dirs()
    directory = os.path.join(profiles, iface)
    meta_path = os.path.join(directory, "meta.json")
    if not os.path.isfile(meta_path):
        if missing_ok:
            return iface
        fail(f"unknown profile {iface}")
    with open(meta_path, encoding="utf-8") as handle:
        meta = json.load(handle)
    uuid = str(meta.get("nmUuid") or "")
    if uuid:
        nm("connection", "down", uuid, check=False)
    obfuscation = str(meta.get("obfuscation") or "none")
    if obfuscation == "udp2raw":
        run_helper("udp2raw-stop", {"pidFile": os.path.join(runtime_dir(), f"{iface}.udp2raw.pid")})
    else:
        stop_proxy(iface)
    host = str(meta.get("bypassHost") or "")
    if host:
        run_helper("route-del", {"host": host})
        meta["bypassHost"] = ""
        save_meta(directory, meta)
    return str(meta.get("label") or iface)


def delete_profile(iface: str) -> str:
    if not IFACE_RE.fullmatch(iface):
        fail(f"unknown profile {iface}")
    _, profiles, _ = ensure_dirs()
    directory, meta = load_meta(profiles, iface)
    label = str(meta.get("label") or iface)
    uuid = str(meta.get("nmUuid") or "")
    down_profile(iface, missing_ok=True)
    if uuid:
        nm("connection", "delete", uuid, check=False)
    listed = nm("-t", "-f", "UUID,TYPE", "connection", "show", check=False)
    for line in listed.stdout.splitlines():
        ident, _, typ = line.partition(":")
        if typ != "wireguard" or not ident:
            continue
        ifn = nm("-g", "connection.interface-name", "connection", "show", ident, check=False).stdout.strip()
        name = nm("-g", "connection.id", "connection", "show", ident, check=False).stdout.strip()
        if ifn == iface or name == iface or name == label:
            nm("connection", "delete", ident, check=False)
    shutil.rmtree(directory, ignore_errors=True)
    return label


def up_profile(iface: str) -> str:
    _, profiles, runtime = ensure_dirs()
    directory, meta = load_meta(profiles, iface)
    uuid = str(meta.get("nmUuid") or "")
    if not uuid:
        fail(f"profile {iface} has no NetworkManager connection")
    obfuscation = str(meta.get("obfuscation") or "none")
    if obfuscation == "lwo":
        fail("lwo is not started by this widget")
    for other in list_profiles():
        if other["iface"] != iface:
            down_profile(str(other["iface"]), missing_ok=True)
    for other in active_wg_uuids():
        if other != uuid:
            nm("connection", "down", other, check=False)
    if obfuscation == "udp2raw":
        transport_name = str(meta.get("transportFilename") or "")
        transport_path = os.path.join(directory, transport_name)
        with open(transport_path, encoding="utf-8") as handle:
            payload = parse_udp2raw_transport(handle.read())
        payload["pidFile"] = os.path.join(runtime, f"{iface}.udp2raw.pid")
        run_helper("udp2raw-stop", {"pidFile": payload["pidFile"]})
        run_helper("udp2raw-start", payload)
    elif obfuscation != "none":
        binary = str(meta.get("transportBinary") or "")
        transport_name = str(meta.get("transportFilename") or "")
        port = int(meta.get("localPort") or 0)
        transport_path = os.path.join(directory, transport_name)
        if port <= 0 or not os.path.isfile(transport_path):
            fail("missing transport file")
        stop_proxy(iface)
        start_user_proxy(iface, binary, transport_path, port)
    host = str(meta.get("remoteHost") or "")
    if host and meta.get("fullTunnel"):
        run_helper("route-add", {"host": host})
        meta["bypassHost"] = host
        save_meta(directory, meta)
    brought = nm("connection", "up", uuid, check=False)
    if brought.returncode != 0:
        down_profile(iface, missing_ok=True)
        fail(brought.stderr.strip() or f"NetworkManager did not activate {iface}")
    return str(meta.get("label") or iface)


def parse_version(value: str) -> tuple[int, ...]:
    numbers = [int(part) for part in re.findall(r"\d+", value)]
    return tuple(numbers or [0])


def package_format() -> str:
    """Arch and its derivatives install the pacman package. Other hosts use the deb."""
    if os.path.isfile("/etc/arch-release"):
        return "pacman"
    return "deb"


def release_asset_name() -> str:
    return PKG_ASSET if package_format() == "pacman" else DEB_ASSET


def choose_release_asset(assets: list[dict[str, Any]], name: str) -> str:
    for asset in assets:
        if asset.get("name") == name:
            url = str(asset.get("browser_download_url") or "")
            if url:
                return url
    return ""


def newer_release() -> dict[str, str] | None:
    """Return asset info when GitHub has a newer widget release."""
    try:
        import urllib.request

        request = urllib.request.Request(RELEASE_API, headers={"Accept": "application/vnd.github+json", "User-Agent": "continuum-vpn-widget"})
        with urllib.request.urlopen(request, timeout=8) as response:
            data = json.load(response)
    except Exception:
        return None
    tag = str(data.get("tag_name") or "")
    if parse_version(tag) <= parse_version(installed_version()):
        return None
    url = choose_release_asset(list(data.get("assets") or []), release_asset_name())
    if not url:
        return None
    return {"tag": tag, "url": url, "format": package_format()}


def main(argv: list[str]) -> int:
    try:
        command = argv[1] if len(argv) > 1 else ""
        if command == "list":
            print(json.dumps(list_profiles()))
        elif command == "import-file" and len(argv) == 3:
            print(import_file(argv[2]))
        elif command == "import-text":
            filename = argv[2] if len(argv) > 2 else "pasted.conf"
            print(import_text(sys.stdin.read(), filename))
        elif command == "up" and len(argv) == 3:
            print(up_profile(argv[2]))
        elif command == "down" and len(argv) == 3:
            print(down_profile(argv[2]))
        elif command == "delete" and len(argv) == 3:
            print(delete_profile(argv[2]))
        elif command == "check-update":
            found = newer_release()
            print(json.dumps(found or {}))
        else:
            fail("usage: engine.py list|up IFACE|down IFACE|delete IFACE|import-file PATH|import-text [NAME]|check-update")
    except EngineError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

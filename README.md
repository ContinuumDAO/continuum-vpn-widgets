# Continuum VPN widgets

Optional desktop packages for turning a Continuum VPN profile on or off. The packages do not call your node. You download or copy a profile bundle from the node VPN panel, then import or paste it.

Installing a package is optional. The VPN panel still explains how to download a WireGuard config and install WireGuard and the obfuscator tools yourself.

## Ubuntu 24.04 and 26.04

The package is `continuum-vpn-widget_amd64.deb` on [GitHub Releases](https://github.com/ContinuumDAO/continuum-vpn-widgets/releases/latest). It includes `sslocal`, `wg-obfuscator`, and `udp2raw`.

```bash
sudo apt install ./continuum-vpn-widget_amd64.deb
```

Open Continuum VPN from the app menu. Import the `continuum-vpn-*.json` bundle, or paste it. One profile is up at a time.

## Arch Linux

The same release also has `continuum-vpn-widget-<version>-1-x86_64.pkg.tar.zst`.

```bash
sudo pacman -U ./continuum-vpn-widget-x86_64.pkg.tar.zst
```

Pacman installs Python, GTK, NetworkManager, WireGuard tools, and the Ayatana tray library if they are missing. On GNOME, enable the AppIndicator extension so the tray icon appears. Import or paste a bundle the same way as on Ubuntu. Installing WireGuard and the obfuscators yourself still works.

```bash
bash arch/scripts/build-pkg.sh
```

## Fedora

The same release also has `continuum-vpn-widget-<version>-1.x86_64.rpm`.

```bash
sudo dnf install ./continuum-vpn-widget-x86_64.rpm
```

Dnf installs Python, GTK, NetworkManager, WireGuard tools, and the Ayatana tray library if they are missing. On GNOME, enable the AppIndicator extension so the tray icon appears. Import or paste a bundle the same way as on Ubuntu. Installing WireGuard and the obfuscators yourself still works. `shadowsocks-rust` is not in the Fedora repositories, so a manual Shadowsocks setup uses the upstream `sslocal` release. The optional package already includes `sslocal`.

```bash
bash fedora/scripts/build-rpm.sh
```

## openSUSE

The same release also has `continuum-vpn-widget-<version>-1.suse.x86_64.rpm`.

```bash
sudo zypper install --allow-unsigned-rpm ./continuum-vpn-widget-suse.x86_64.rpm
```

Zypper installs Python, GTK, NetworkManager, WireGuard tools, and the Ayatana tray library if they are missing. On GNOME, enable the AppIndicator extension so the tray icon appears. Import or paste a bundle the same way as on Ubuntu. Installing WireGuard and the obfuscators yourself still works. `shadowsocks-rust` is not in the official openSUSE repositories, so a manual Shadowsocks setup uses the upstream `sslocal` release. The optional package already includes `sslocal`.

```bash
bash opensuse/scripts/build-rpm.sh
```

## macOS

The same release also has `continuum-vpn-widget-<version>-macos-arm64.zip` and `continuum-vpn-widget-<version>-macos-x64.zip`. Unzip the one that matches the Mac and move `Continuum VPN.app` to Applications.

The app is unsigned. Gatekeeper blocks the first double-click. Control-click the app, choose Open, then choose Open again. If macOS still blocks it, use System Settings → Privacy & Security → Open Anyway.

The app includes `sslocal` and `wg-obfuscator`. It does not include `udp2raw`. Import or paste a bundle from the menu bar. Installing WireGuard and the obfuscators yourself still works.

```bash
bash macos/scripts/build-app.sh
```

## Windows

The same release also has `continuum-vpn-widget-<version>-windows-x64.zip`. Unzip it and run Continuum VPN. The app does not use WSL. It turns tunnels on and off with WireGuard for Windows, which needs to be installed from wireguard.com. The app includes `sslocal` and `wg-obfuscator`. It does not include `udp2raw`.

Windows SmartScreen may warn because the app is unsigned. Choose More info, then Run anyway. A virus checker may also remove or block `sslocal.exe` and `wg-obfuscator.exe`. If an obfuscated profile will not start, allow those files in the checker.

```bash
bash windows/scripts/build-app.sh
```

Profiles are stored under `~/.config/continuum-vpn/profiles/`. The widget checks GitHub Releases from its menu and can install a newer package.

udp2raw runs from the bundled binary. A downloaded shell script is refused.

## Development

```bash
bash ubuntu/tests/run.sh
bash ubuntu/scripts/build-deb.sh
```

`build-deb.sh` downloads the pinned obfuscator releases listed in `ubuntu/versions.env`.

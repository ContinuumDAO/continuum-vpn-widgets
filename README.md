# Continuum VPN widgets

Optional desktop packages for turning a Continuum VPN profile on or off. The packages do not call your node. You download or copy a profile bundle from the node VPN panel, then import or paste it.

Installing a package is optional. The VPN panel still explains how to download a WireGuard config and install WireGuard and the obfuscator tools yourself.

## Ubuntu 24.04 and 26.04

The package is `continuum-vpn-widget_amd64.deb` on [GitHub Releases](https://github.com/ContinuumDAO/continuum-vpn-widgets/releases/latest). It includes `sslocal`, `wg-obfuscator`, and `udp2raw`.

```bash
sudo apt install ./continuum-vpn-widget_amd64.deb
```

Open Continuum VPN from the app menu. Import the `continuum-vpn-*.json` bundle, or paste it. One profile is up at a time.

Profiles are stored under `~/.config/continuum-vpn/profiles/`. The widget checks GitHub Releases from its menu and can install a newer package.

udp2raw runs from the bundled binary. A downloaded shell script is refused.

## Development

```bash
bash ubuntu/tests/run.sh
bash ubuntu/scripts/build-deb.sh
```

`build-deb.sh` downloads the pinned obfuscator releases listed in `ubuntu/versions.env`.

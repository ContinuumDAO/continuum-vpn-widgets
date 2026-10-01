#!/usr/bin/env python3
"""Tray widget for Continuum VPN on Ubuntu."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

import engine


def asset(name: str) -> str:
    here = os.path.dirname(os.path.realpath(__file__))
    for path in (
        os.path.join(here, name),
        os.path.join(here, "..", "icons", name),
    ):
        if os.path.isfile(path):
            return os.path.realpath(path)
    return ""


WIDGET_BUS_NAME = "com.continuumdao.VpnWidget"
WIDGET_BUS_PATH = "/com/continuumdao/VpnWidget"
WIDGET_BUS_XML = """
<node>
  <interface name="com.continuumdao.VpnWidget">
    <method name="Present"/>
  </interface>
</node>
"""


def _present_existing(bus) -> bool:
    from gi.repository import Gio

    try:
        bus.call_sync(
            WIDGET_BUS_NAME,
            WIDGET_BUS_PATH,
            WIDGET_BUS_NAME,
            "Present",
            None,
            None,
            Gio.DBusCallFlags.NONE,
            300,
            None,
        )
    except Exception:
        return False
    return True


def _export_present(bus, present_window) -> None:
    from gi.repository import Gio, GLib

    node = Gio.DBusNodeInfo.new_for_xml(WIDGET_BUS_XML)

    def handle_method(_connection, _sender, _path, _interface, method, _params, invocation):
        if method == "Present":
            GLib.idle_add(present_window)
        invocation.return_value(None)

    bus.register_object(WIDGET_BUS_PATH, node.interfaces[0], handle_method, None, None)
    Gio.bus_own_name_on_connection(
        bus,
        WIDGET_BUS_NAME,
        Gio.BusNameOwnerFlags.NONE,
        None,
        None,
    )


def run_tray() -> int:
    try:
        import gi

        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk, GLib

        # Match the desktop file. Otherwise GNOME tracks this as an unknown
        # Python window and pulses a generic status icon beside the tray.
        GLib.set_prgname("continuum-vpn-widget")
        Gdk.set_program_class("continuum-vpn-widget")
        gi.require_version("Gtk", "3.0")
        gi.require_version("GdkPixbuf", "2.0")
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import AyatanaAppIndicator3, GdkPixbuf, Gio, Gtk
    except (ImportError, ValueError) as exc:
        print(f"Continuum VPN needs GTK and AppIndicator: {exc}", file=sys.stderr)
        return 1

    logo = asset("continuum-logo.png")
    # Theme icon name only. An absolute image path is cached by the shell in a
    # way that makes other tray icons, such as Cursor's, reload and fade.
    indicator = AyatanaAppIndicator3.Indicator.new(
        "continuum-vpn",
        "continuum-vpn",
        AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS,
    )
    indicator.set_icon_full("continuum-vpn", "Continuum VPN")
    indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)
    indicator.set_title("Continuum VPN")

    # Leave the window unbuilt until the user asks for it. Building it at
    # startup, or opening it when the panel merely reads the menu, makes
    # GNOME refresh other status icons.
    ui: dict = {"window": None, "profile_box": None}

    def ensure_window():
        if ui["window"] is not None:
            return ui["window"]
        window = Gtk.Window(title="Continuum VPN")
        window.set_default_size(380, 560)
        window.set_resizable(True)
        window.set_position(Gtk.WindowPosition.NONE)
        window.set_skip_taskbar_hint(True)
        window.set_skip_pager_hint(True)
        window.set_icon_name("continuum-vpn")
        window.connect("delete-event", lambda *_: window.hide() or True)

        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        hero.set_margin_top(18)
        hero.set_margin_bottom(6)
        hero.set_margin_start(18)
        hero.set_margin_end(18)
        if logo:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(logo, 148, 148, True)
            image = Gtk.Image.new_from_pixbuf(pixbuf)
            image.set_halign(Gtk.Align.CENTER)
            hero.pack_start(image, False, False, 0)
        title = Gtk.Label()
        title.set_markup("<span weight='bold' size='large'>Continuum VPN</span>")
        title.set_halign(Gtk.Align.CENTER)
        hero.pack_start(title, False, False, 0)

        profile_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        profile_box.set_margin_start(18)
        profile_box.set_margin_end(18)
        profile_box.set_margin_top(8)
        profile_box.set_margin_bottom(8)

        status = Gtk.Label(label="Disconnected")
        status.set_halign(Gtk.Align.START)
        status.set_line_wrap(True)
        status.set_max_width_chars(36)
        status.set_margin_start(18)
        status.set_margin_end(18)
        status.set_margin_top(4)

        connect = Gtk.Button.new_with_label("Connect")
        connect.set_halign(Gtk.Align.START)
        connect.set_margin_start(18)
        connect.set_margin_end(18)
        connect.set_margin_bottom(4)
        connect.connect("clicked", on_connect)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(180)
        scrolled.add(profile_box)

        actions = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        actions.set_margin_start(18)
        actions.set_margin_end(18)
        actions.set_margin_bottom(18)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        root.pack_start(hero, False, False, 0)
        root.pack_start(status, False, False, 0)
        root.pack_start(connect, False, False, 0)
        root.pack_start(scrolled, True, True, 0)
        root.pack_start(actions, False, False, 0)
        window.add(root)
        add_button(actions, "Import bundle…", on_import)
        add_button(actions, "Paste bundle", on_paste)
        add_button(actions, "Check for updates", on_update)
        add_button(actions, "Quit", lambda *_: Gtk.main_quit())
        ui["window"] = window
        ui["profile_box"] = profile_box
        ui["status_label"] = status
        ui["connect_button"] = connect
        rebuild.signature = None
        rebuild()
        return window

    def place_window() -> None:
        window = ensure_window()
        window.show_all()
        width, height = window.get_size()
        display = window.get_display()
        monitor = display.get_primary_monitor()
        if monitor is None and display.get_n_monitors() > 0:
            monitor = display.get_monitor(0)
        if monitor is not None:
            area = monitor.get_workarea()
            window.move(area.x + area.width - width - 12, area.y + 8)

    def present_window() -> None:
        place_window()
        ui["window"].present()

    def alert(message: str) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=ensure_window(),
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE,
            text="Continuum VPN",
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()

    def call(action, *args):
        try:
            return action(*args)
        except engine.EngineError as exc:
            alert(str(exc))
            return None

    def clear(box: Gtk.Box) -> None:
        for child in box.get_children():
            box.remove(child)

    def add_button(box: Gtk.Box, label: str, handler) -> None:
        button = Gtk.Button.new_with_label(label)
        button.connect("clicked", handler)
        button.set_halign(Gtk.Align.FILL)
        box.pack_start(button, False, False, 0)

    def profile_caption(row: dict) -> str:
        label = str(row.get("label") or row.get("iface") or "")
        code = str(row.get("countryCode") or "")
        if not code:
            return label
        flag = str(row.get("countryFlag") or "")
        return f"{flag} {code}  {label}".strip()

    def profile_detail(row: dict) -> str:
        stored = str(row.get("detail") or "").strip()
        if stored:
            return stored
        obfuscation = str(row.get("obfuscation") or "none")
        names = {
            "shadowsocks": "WireGuard, with Shadowsocks",
            "wg_obfuscator": "WireGuard, with wg-obfuscator",
            "lwo": "WireGuard, with LWO",
            "udp2raw": "WireGuard, with udp2raw",
        }
        return names.get(obfuscation, "WireGuard")

    def selected_row() -> dict | None:
        iface = ui.get("selected")
        for row in ui.get("rows") or []:
            if row.get("iface") == iface:
                return row
        return None

    def refresh_connection_controls() -> None:
        row = selected_row()
        button = ui.get("connect_button")
        status = ui.get("status_label")
        active = next((item for item in ui.get("rows") or [] if item.get("active")), None)
        if status is not None:
            if active:
                status.set_text(f"Connected to {profile_caption(active)}")
            else:
                status.set_text("Disconnected")
        if button is None:
            return
        if row is None:
            button.set_label("Connect")
            button.set_sensitive(False)
            return
        button.set_sensitive(True)
        caption = profile_caption(row)
        button.set_label(("Disconnect " if row.get("active") else "Connect ") + caption)

    def choose_profile(button, iface: str) -> None:
        if button.get_active():
            ui["selected"] = iface
            refresh_connection_controls()

    def on_connect(*_args) -> None:
        row = selected_row()
        if row is None:
            alert("Choose a profile first.")
            return
        iface = str(row["iface"])
        if row.get("active"):
            call(engine.down_profile, iface)
        else:
            call(engine.up_profile, iface)
        rebuild.signature = None
        rebuild()

    def toggle_profile(iface: str, active: bool):
        ui["selected"] = iface
        if active:
            call(engine.down_profile, iface)
        else:
            call(engine.up_profile, iface)
        rebuild.signature = None
        rebuild()

    def rebuild(*_args) -> bool:
        try:
            rows = engine.list_profiles()
        except engine.EngineError as exc:
            rows = [{"error": str(exc)}]
        signature = json.dumps(rows, sort_keys=True, default=str)
        if signature == getattr(rebuild, "signature", None):
            return True
        rebuild.signature = signature

        failed = bool(rows and isinstance(rows[0], dict) and rows[0].get("error") and "label" not in rows[0])
        error_text = rows[0]["error"] if failed else ""
        shown = [] if failed else rows
        ui["rows"] = shown
        available = {str(row.get("iface")) for row in shown}
        if ui.get("selected") not in available:
            active_iface = next((str(row["iface"]) for row in shown if row.get("active")), "")
            ui["selected"] = active_iface or (str(shown[0]["iface"]) if shown else None)
        profile_box = ui["profile_box"]
        if profile_box is not None:
            clear(profile_box)
            if failed:
                label = Gtk.Label(label=error_text)
                label.set_line_wrap(True)
                label.set_max_width_chars(32)
                profile_box.pack_start(label, False, False, 0)
            elif not shown:
                label = Gtk.Label(
                    label=(
                        "No profiles yet. On the node VPN panel, save one "
                        "continuum-vpn-….json file per exit and import it here."
                    )
                )
                label.set_line_wrap(True)
                label.set_max_width_chars(36)
                label.set_halign(Gtk.Align.START)
                profile_box.pack_start(label, False, False, 0)
            group = None
            for row in shown:
                iface = row["iface"]
                block = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                caption = profile_caption(row)
                if row.get("active"):
                    caption = f"{caption}  ·  connected"
                radio = Gtk.RadioButton.new_with_label_from_widget(group, caption)
                if group is None:
                    group = radio
                radio.set_halign(Gtk.Align.START)
                radio.set_active(iface == ui.get("selected"))
                radio.connect("toggled", lambda button, iface=iface: choose_profile(button, iface))
                detail = Gtk.Label(label=profile_detail(row))
                detail.set_line_wrap(True)
                detail.set_max_width_chars(38)
                detail.set_xalign(0)
                detail.set_margin_start(24)
                detail.get_style_context().add_class("dim-label")
                block.pack_start(radio, False, False, 0)
                block.pack_start(detail, False, False, 0)
                profile_box.pack_start(block, False, False, 0)
            refresh_connection_controls()

        menu = Gtk.Menu()

        def menu_item(text: str, handler) -> None:
            item = Gtk.MenuItem.new_with_label(text)
            item.connect("activate", handler)
            item.show()
            menu.append(item)

        def sep() -> None:
            item = Gtk.SeparatorMenuItem()
            item.show()
            menu.append(item)

        if failed:
            item = Gtk.MenuItem.new_with_label(error_text)
            item.set_sensitive(False)
            item.show()
            menu.append(item)
        elif not shown:
            item = Gtk.MenuItem.new_with_label("No profiles yet")
            item.set_sensitive(False)
            item.show()
            menu.append(item)
        else:
            for row in shown:
                iface = row["iface"]
                active = bool(row.get("active"))
                verb = "Disconnect" if active else "Connect"
                menu_item(
                    f"{verb} {profile_caption(row)}",
                    lambda _item, iface=iface, active=active: toggle_profile(iface, active),
                )
        sep()
        menu_item("Import bundle…", on_import)
        menu_item("Paste bundle", on_paste)
        menu_item("Check for updates", on_update)
        sep()
        menu_item("Quit", lambda *_: Gtk.main_quit())

        header = Gtk.MenuItem.new_with_label("Open Continuum VPN")
        header.connect("activate", lambda *_: present_window())
        header.show()
        menu.prepend(header)
        indicator.set_menu(menu)
        window = ui["window"]
        if window is not None and window.get_visible():
            window.show_all()
        return True

    def read_chosen_file(chooser) -> tuple[str, str] | None:
        gfile = chooser.get_file()
        path = chooser.get_filename()
        name = "bundle.json"
        if gfile is not None:
            name = gfile.get_basename() or name
            path = gfile.get_path() or path
            if not path or not os.path.isfile(path):
                try:
                    ok, data, _etag = gfile.load_contents()
                except Exception as exc:
                    alert(f"Could not read {name}: {exc}")
                    return None
                if not ok:
                    alert(f"Could not read {name}.")
                    return None
                return name, bytes(data).decode("utf-8-sig")
        if not path:
            alert("No file selected.")
            return None
        try:
            with open(path, encoding="utf-8-sig") as handle:
                return os.path.basename(path) or name, handle.read()
        except OSError as exc:
            alert(f"Could not read the selected file: {exc}")
            return None

    def on_import(*_args) -> None:
        present_window()
        chooser = Gtk.FileChooserDialog(
            title="Import Continuum VPN bundle",
            transient_for=ui["window"],
            action=Gtk.FileChooserAction.OPEN,
        )
        chooser.add_button("Cancel", Gtk.ResponseType.CANCEL)
        chooser.add_button("Import", Gtk.ResponseType.ACCEPT)
        bundle_filter = Gtk.FileFilter()
        bundle_filter.set_name("Continuum VPN bundle")
        for pattern in (
            "continuum-vpn-*.json",
            "cont-full.conf",
            "cont-split.conf",
            "cont-egress.conf",
            "*.json",
            "*.conf",
        ):
            bundle_filter.add_pattern(pattern)
        chooser.add_filter(bundle_filter)
        any_filter = Gtk.FileFilter()
        any_filter.set_name("All files")
        any_filter.add_pattern("*")
        chooser.add_filter(any_filter)
        downloads = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
        if downloads:
            chooser.set_current_folder(downloads)
        if chooser.run() == Gtk.ResponseType.ACCEPT:
            chosen = read_chosen_file(chooser)
            if chosen is not None and call(engine.import_text, chosen[1], chosen[0]) is not None:
                rebuild.signature = None
                rebuild()
        chooser.destroy()

    def on_paste(*_args) -> None:
        present_window()
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        text = clipboard.wait_for_text() or ""
        if call(engine.import_text, text, "pasted.conf") is not None:
            rebuild.signature = None
            rebuild()

    def on_update(*_args) -> None:
        present_window()
        found = engine.newer_release()
        if not found:
            dialog = Gtk.MessageDialog(
                transient_for=ui["window"],
                text="Continuum VPN is up to date",
                buttons=Gtk.ButtonsType.CLOSE,
            )
            dialog.run()
            dialog.destroy()
            return
        dialog = Gtk.MessageDialog(
            transient_for=ui["window"],
            text=f"Install Continuum VPN {found['tag']}?",
            buttons=Gtk.ButtonsType.NONE,
        )
        dialog.format_secondary_text("This replaces the optional Ubuntu package. Your saved profiles stay on this computer.")
        dialog.add_button("Not now", Gtk.ResponseType.CANCEL)
        dialog.add_button("Install", Gtk.ResponseType.ACCEPT)
        if dialog.run() != Gtk.ResponseType.ACCEPT:
            dialog.destroy()
            return
        dialog.destroy()
        try:
            dest = os.path.join(engine.runtime_dir(), "continuum-vpn-widget_amd64.deb")
            urllib.request.urlretrieve(found["url"], dest)
        except Exception as exc:
            alert(f"Could not download the update: {exc}")
            return
        result = os.spawnvp(os.P_WAIT, "pkexec", ["pkexec", "apt-get", "install", "-y", dest])
        if result != 0:
            alert("The package was not installed.")

    started = time.monotonic()

    def on_bus_message(_connection, message, incoming, _data):
        # A click on the tray icon asks the menu to open. The panel also
        # sends that once while attaching the icon, which is not a click.
        if not incoming or message.get_interface() != "com.canonical.dbusmenu":
            return message
        if message.get_member() == "AboutToShow" and time.monotonic() - started > 1.5:
            GLib.idle_add(present_window)
        return message

    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    if _present_existing(bus):
        return 0
    _export_present(bus, present_window)
    bus.add_filter(on_bus_message, None)
    rebuild()
    present_window()
    GLib.timeout_add_seconds(3, rebuild)
    Gtk.main()
    return 0


def main() -> int:
    argv = sys.argv
    if len(argv) == 1 or argv[1] == "tray":
        return run_tray()
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())

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
        window.set_default_size(340, 460)
        window.set_resizable(False)
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

        profile_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        profile_box.set_margin_start(18)
        profile_box.set_margin_end(18)
        profile_box.set_margin_top(8)
        profile_box.set_margin_bottom(8)

        actions = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        actions.set_margin_start(18)
        actions.set_margin_end(18)
        actions.set_margin_bottom(18)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        root.pack_start(hero, False, False, 0)
        root.pack_start(profile_box, True, True, 0)
        root.pack_start(actions, False, False, 0)
        window.add(root)
        add_button(actions, "Import bundle…", on_import)
        add_button(actions, "Paste bundle", on_paste)
        add_button(actions, "Check for updates", on_update)
        add_button(actions, "Quit", lambda *_: Gtk.main_quit())
        ui["window"] = window
        ui["profile_box"] = profile_box
        rebuild.signature = None
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

    def profile_text(row: dict) -> str:
        text = row["label"]
        if row.get("countryFlag"):
            text = f"{row['countryFlag']} {text}"
        if row.get("detail"):
            text = f"{text} — {row['detail']}"
        if row.get("active"):
            text = f"● {text}"
        return text

    def toggle_profile(iface: str, active: bool):
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
        profile_box = ui["profile_box"]
        if profile_box is not None:
            clear(profile_box)
            if failed:
                label = Gtk.Label(label=error_text)
                label.set_line_wrap(True)
                label.set_max_width_chars(32)
                profile_box.pack_start(label, False, False, 0)
            elif not shown:
                label = Gtk.Label(label="No profiles yet")
                label.set_halign(Gtk.Align.CENTER)
                profile_box.pack_start(label, False, False, 0)
            for row in shown:
                iface = row["iface"]
                active = bool(row.get("active"))
                add_button(
                    profile_box,
                    profile_text(row),
                    lambda _button, iface=iface, active=active: toggle_profile(iface, active),
                )

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
                menu_item(
                    profile_text(row),
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

    def on_import(*_args) -> None:
        present_window()
        chooser = Gtk.FileChooserDialog(
            title="Import Continuum VPN bundle",
            transient_for=ui["window"],
            action=Gtk.FileChooserAction.OPEN,
        )
        chooser.add_button("Cancel", Gtk.ResponseType.CANCEL)
        chooser.add_button("Import", Gtk.ResponseType.ACCEPT)
        if chooser.run() == Gtk.ResponseType.ACCEPT:
            call(engine.import_file, chooser.get_filename())
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

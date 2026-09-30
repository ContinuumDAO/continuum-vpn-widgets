#!/usr/bin/env python3
"""Tray widget for Continuum VPN on Ubuntu."""

from __future__ import annotations

import json
import os
import sys
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


def run_tray() -> int:
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("GdkPixbuf", "2.0")
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import AyatanaAppIndicator3, Gdk, GdkPixbuf, Gio, GLib, Gtk
    except (ImportError, ValueError) as exc:
        print(f"Continuum VPN needs GTK and AppIndicator: {exc}", file=sys.stderr)
        return 1

    tray_icon = asset("continuum-vpn.png")
    logo = asset("continuum-logo.png")
    # A full-color file, not a symbolic status name, so the shell draws this
    # as its own panel icon instead of folding it into the system status icons.
    indicator = AyatanaAppIndicator3.Indicator.new(
        "continuum-vpn",
        tray_icon or "continuum-vpn",
        AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS,
    )
    if tray_icon:
        indicator.set_icon_full(tray_icon, "Continuum VPN")
    indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)
    indicator.set_title("Continuum VPN")
    if logo:
        Gtk.Window.set_default_icon_from_file(logo)

    window = Gtk.Window(title="Continuum VPN")
    window.set_default_size(340, 460)
    window.set_resizable(False)
    window.set_position(Gtk.WindowPosition.NONE)
    window.set_keep_above(True)
    window.set_type_hint(Gdk.WindowTypeHint.DIALOG)
    if logo:
        window.set_icon_from_file(logo)
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

    def place_window() -> None:
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
        window.present()

    def alert(message: str) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=window,
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

    def rebuild(*_args) -> bool:
        try:
            rows = engine.list_profiles()
        except engine.EngineError as exc:
            rows = [{"error": str(exc)}]
        signature = json.dumps(rows, sort_keys=True, default=str)
        if signature == getattr(rebuild, "signature", None):
            return True
        rebuild.signature = signature

        clear(profile_box)
        failed = bool(rows and isinstance(rows[0], dict) and rows[0].get("error") and "label" not in rows[0])
        if failed:
            label = Gtk.Label(label=rows[0]["error"])
            label.set_line_wrap(True)
            label.set_max_width_chars(32)
            profile_box.pack_start(label, False, False, 0)
            rows = []
        elif not rows:
            label = Gtk.Label(label="No profiles yet")
            label.set_halign(Gtk.Align.CENTER)
            profile_box.pack_start(label, False, False, 0)
        for row in rows:
            text = row["label"]
            if row.get("countryFlag"):
                text = f"{row['countryFlag']} {text}"
            if row.get("detail"):
                text = f"{text} — {row['detail']}"
            if row.get("active"):
                text = f"● {text}"
            iface = row["iface"]
            active = bool(row.get("active"))

            def toggle(_button, iface=iface, active=active):
                if active:
                    call(engine.down_profile, iface)
                else:
                    call(engine.up_profile, iface)
                rebuild.signature = None
                rebuild()

            add_button(profile_box, text, toggle)

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
            item = Gtk.MenuItem.new_with_label(profile_box.get_children()[0].get_text())
            item.set_sensitive(False)
            item.show()
            menu.append(item)
        elif not rows:
            item = Gtk.MenuItem.new_with_label("No profiles yet")
            item.set_sensitive(False)
            item.show()
            menu.append(item)
        else:
            for child in profile_box.get_children():
                if isinstance(child, Gtk.Button):
                    menu_item(child.get_label(), lambda _item, button=child: button.clicked())
        sep()
        menu_item("Import bundle…", on_import)
        menu_item("Paste bundle", on_paste)
        menu_item("Check for updates", on_update)
        sep()
        menu_item("Quit", lambda *_: Gtk.main_quit())

        if logo:
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                header = Gtk.ImageMenuItem.new_with_label("Continuum VPN")
                header.set_image(Gtk.Image.new_from_pixbuf(
                    GdkPixbuf.Pixbuf.new_from_file_at_scale(logo, 64, 64, True)
                ))
                header.set_always_show_image(True)
            header.connect("activate", lambda *_: present_window())
            header.show()
            menu.prepend(header)
        indicator.set_menu(menu)
        if window.get_visible():
            window.show_all()
        return True

    def on_import(*_args) -> None:
        present_window()
        chooser = Gtk.FileChooserDialog(
            title="Import Continuum VPN bundle",
            transient_for=window,
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
                transient_for=window,
                text="Continuum VPN is up to date",
                buttons=Gtk.ButtonsType.CLOSE,
            )
            dialog.run()
            dialog.destroy()
            return
        dialog = Gtk.MessageDialog(
            transient_for=window,
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

    add_button(actions, "Import bundle…", on_import)
    add_button(actions, "Paste bundle", on_paste)
    add_button(actions, "Check for updates", on_update)
    add_button(actions, "Quit", lambda *_: Gtk.main_quit())

    def on_bus_message(_connection, message, incoming, _data):
        # The panel draws the menu itself. Opening it calls the menu bus,
        # which is the moment the widget window should appear.
        if not incoming or message.get_interface() != "com.canonical.dbusmenu":
            return message
        if message.get_member() == "AboutToShow":
            GLib.idle_add(present_window)
        return message

    Gio.bus_get_sync(Gio.BusType.SESSION, None).add_filter(on_bus_message, None)
    rebuild()
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

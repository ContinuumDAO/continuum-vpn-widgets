#!/usr/bin/env python3
"""Tray widget for Continuum VPN on Ubuntu."""

from __future__ import annotations

import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

import engine


def run_tray() -> int:
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import AyatanaAppIndicator3, GLib, Gtk
    except (ImportError, ValueError) as exc:
        print(f"Continuum VPN needs GTK and AppIndicator: {exc}", file=sys.stderr)
        return 1

    indicator = AyatanaAppIndicator3.Indicator.new(
        "continuum-vpn",
        "network-vpn-symbolic",
        AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS,
    )
    indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)
    indicator.set_title("Continuum VPN")

    def alert(message: str) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=None,
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

    def rebuild(*_args) -> bool:
        menu = Gtk.Menu()
        try:
            rows = engine.list_profiles()
        except engine.EngineError as exc:
            item = Gtk.MenuItem.new_with_label(str(exc))
            item.set_sensitive(False)
            item.show()
            menu.append(item)
            rows = []
        if not rows:
            empty = Gtk.MenuItem.new_with_label("No profiles yet")
            empty.set_sensitive(False)
            empty.show()
            menu.append(empty)
        for row in rows:
            title = row["label"]
            if row.get("countryFlag"):
                title = f"{row['countryFlag']} {title}"
            if row.get("detail"):
                title = f"{title} — {row['detail']}"
            if row.get("active"):
                title = f"● {title}"
            item = Gtk.MenuItem.new_with_label(title)
            iface = row["iface"]
            active = bool(row.get("active"))

            def toggle(_item, iface=iface, active=active):
                if active:
                    call(engine.down_profile, iface)
                else:
                    call(engine.up_profile, iface)
                rebuild()

            item.connect("activate", toggle)
            item.show()
            menu.append(item)

        menu.append(separator())
        import_item = Gtk.MenuItem.new_with_label("Import bundle…")
        import_item.connect("activate", on_import)
        import_item.show()
        menu.append(import_item)
        paste_item = Gtk.MenuItem.new_with_label("Paste bundle")
        paste_item.connect("activate", on_paste)
        paste_item.show()
        menu.append(paste_item)
        update_item = Gtk.MenuItem.new_with_label("Check for updates")
        update_item.connect("activate", on_update)
        update_item.show()
        menu.append(update_item)
        menu.append(separator())
        quit_item = Gtk.MenuItem.new_with_label("Quit")
        quit_item.connect("activate", lambda *_: Gtk.main_quit())
        quit_item.show()
        menu.append(quit_item)
        indicator.set_menu(menu)
        return True

    def separator() -> Gtk.SeparatorMenuItem:
        item = Gtk.SeparatorMenuItem()
        item.show()
        return item

    def on_import(*_args) -> None:
        chooser = Gtk.FileChooserDialog(
            title="Import Continuum VPN bundle",
            action=Gtk.FileChooserAction.OPEN,
        )
        chooser.add_button("Cancel", Gtk.ResponseType.CANCEL)
        chooser.add_button("Import", Gtk.ResponseType.ACCEPT)
        if chooser.run() == Gtk.ResponseType.ACCEPT:
            call(engine.import_file, chooser.get_filename())
            rebuild()
        chooser.destroy()

    def on_paste(*_args) -> None:
        clipboard = Gtk.Clipboard.get(Gdk_selection())
        text = clipboard.wait_for_text() or ""
        if call(engine.import_text, text, "pasted.conf") is not None:
            rebuild()

    def on_update(*_args) -> None:
        found = engine.newer_release()
        if not found:
            dialog = Gtk.MessageDialog(
                text="Continuum VPN is up to date",
                buttons=Gtk.ButtonsType.CLOSE,
            )
            dialog.run()
            dialog.destroy()
            return
        dialog = Gtk.MessageDialog(
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

    def Gdk_selection():
        from gi.repository import Gdk

        return Gdk.SELECTION_CLIPBOARD

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

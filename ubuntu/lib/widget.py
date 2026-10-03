#!/usr/bin/env python3
"""Tray widget for Continuum VPN on Ubuntu."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.parse
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
        window.set_default_size(560, 680)
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

        status = Gtk.Button.new_with_label("Disconnected")
        status.set_halign(Gtk.Align.END)
        status.set_valign(Gtk.Align.CENTER)
        status.get_style_context().add_class("status-badge")
        status.get_style_context().add_class("status-off")
        status.set_tooltip_text("Connect")
        status.connect("clicked", lambda *_: toggle_connection())

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        header.set_margin_top(12)
        header.set_margin_bottom(2)
        header.set_margin_start(18)
        header.set_margin_end(18)
        header.pack_end(status, False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_propagate_natural_height(False)
        scrolled.set_min_content_height(180)
        scrolled.set_overlay_scrolling(False)
        scrolled.set_shadow_type(Gtk.ShadowType.IN)
        scrolled.add(profile_box)

        actions = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        actions.set_margin_start(18)
        actions.set_margin_end(18)
        actions.set_margin_bottom(18)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        root.pack_start(header, False, False, 0)
        root.pack_start(hero, False, False, 0)
        root.pack_start(scrolled, True, True, 0)
        root.pack_start(actions, False, False, 0)
        window.add(root)
        add_button(actions, "Import bundle…", on_import)
        add_button(actions, "Paste bundle", on_paste)
        add_button(actions, "Check for updates", on_update)
        add_button(actions, "Quit", lambda *_: Gtk.main_quit())
        style = Gtk.CssProvider()
        style.load_from_data(
            b"""
            button.on-button, button.on-button:disabled {
              background-image: none;
              background-color: #1e8e3e;
              color: #ffffff;
              border-color: #146c2e;
              font-weight: bold;
              opacity: 1;
            }
            button.off-button, button.off-button:disabled {
              background-image: none;
              background-color: #c5221f;
              color: #ffffff;
              border-color: #8c1d18;
              font-weight: bold;
              opacity: 1;
            }
            button.on-button label, button.off-button label,
            button.on-button:disabled label, button.off-button:disabled label {
              color: #ffffff;
              font-weight: bold;
            }
            button.on-button.is-current, button.off-button.is-current {
              border-width: 3px;
              border-color: #ffffff;
            }
            button.status-badge {
              background-image: none;
              border-radius: 999px;
              padding: 2px 16px;
              min-height: 34px;
            }
            button.status-badge label {
              color: #ffffff;
              font-weight: bold;
            }
            button.status-badge.status-on,
            button.status-badge.status-on:hover,
            button.status-badge.status-on:active {
              background-color: #1e8e3e;
              color: #ffffff;
              border-color: #146c2e;
            }
            button.status-badge.status-off,
            button.status-badge.status-off:hover,
            button.status-badge.status-off:active {
              background-color: #c5221f;
              color: #ffffff;
              border-color: #8c1d18;
            }
            button.status-badge.status-busy,
            button.status-badge.status-busy:disabled {
              background-image: none;
              background-color: #5f6368;
              color: #ffffff;
              border-color: #3c4043;
              opacity: 1;
            }
            """
        )
        Gtk.StyleContext.add_provider_for_screen(
            window.get_screen(),
            style,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
        ui["window"] = window
        ui["profile_box"] = profile_box
        ui["status_label"] = status
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
            limit = max(520, area.height - 16)
            if height > limit:
                window.resize(width, limit)
                width, height = window.get_size()
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
        return str(row.get("label") or row.get("iface") or "")

    def obfuscation_label(row: dict) -> str:
        names = {
            "none": "None",
            "shadowsocks": "Shadowsocks",
            "wg_obfuscator": "wg-obfuscator",
            "lwo": "LWO",
            "udp2raw": "udp2raw",
        }
        return names.get(str(row.get("obfuscation") or "none"), str(row.get("obfuscation") or "None"))

    def blank(value: str) -> str:
        text = str(value or "").strip()
        return text or "—"

    def set_profile(iface: str, turn_on: bool) -> None:
        ui["selected"] = iface
        row = next((item for item in ui.get("rows") or [] if item.get("iface") == iface), None)
        if row is None:
            return
        if bool(row.get("active")) == turn_on:
            return
        if turn_on:
            call(engine.up_profile, iface)
        else:
            call(engine.down_profile, iface)
        rebuild.signature = None
        rebuild()

    def paint_status(text: str, kind: str, tip: str, sensitive: bool = True) -> None:
        status = ui.get("status_label")
        if status is None:
            return
        status.set_label(text)
        status.set_tooltip_text(tip)
        status.set_sensitive(sensitive)
        context = status.get_style_context()
        for name in ("status-on", "status-off", "status-busy"):
            context.remove_class(name)
        context.add_class(f"status-{kind}")

    def connection_target() -> dict | None:
        rows = [item for item in ui.get("rows") or [] if item.get("iface")]
        selected = str(ui.get("selected") or "")
        match = next((item for item in rows if str(item.get("iface")) == selected), None)
        return match or (rows[0] if rows else None)

    def refresh_connection_controls() -> None:
        rows = [item for item in ui.get("rows") or [] if item.get("iface")]
        active = next((item for item in rows if item.get("active")), None)
        if active:
            label = profile_caption(active)
            paint_status(f"Connected to {label}", "on", f"Disconnect {label}")
            return
        target = connection_target()
        if target:
            paint_status("Disconnected", "off", f"Connect {profile_caption(target)}")
            return
        paint_status("Disconnected", "off", "Import a VPN to connect", sensitive=False)

    def toggle_connection() -> None:
        if ui.get("busy"):
            return
        rows = [item for item in ui.get("rows") or [] if item.get("iface")]
        active = next((item for item in rows if item.get("active")), None)
        if active:
            set_profile(str(active["iface"]), False)
            return
        target = connection_target()
        if target:
            set_profile(str(target["iface"]), True)

    def add_param(grid: Gtk.Grid, row_index: int, name: str, value: str) -> None:
        key = Gtk.Label(label=name)
        key.set_halign(Gtk.Align.START)
        key.set_xalign(0)
        key.get_style_context().add_class("dim-label")
        shown = Gtk.Label(label=blank(value))
        shown.set_halign(Gtk.Align.START)
        shown.set_xalign(0)
        shown.set_selectable(True)
        grid.attach(key, 1, row_index, 1, 1)
        grid.attach(shown, 2, row_index, 1, 1)

    def add_profile_card(box: Gtk.Box, row: dict) -> None:
        iface = str(row["iface"])
        active = bool(row.get("active"))
        card = Gtk.Frame()
        grid = Gtk.Grid()
        grid.set_column_spacing(16)
        grid.set_row_spacing(4)
        grid.set_margin_top(10)
        grid.set_margin_bottom(10)
        grid.set_margin_start(10)
        grid.set_margin_end(10)
        flag = Gtk.Label()
        mark = str(row.get("countryFlag") or "—")
        flag.set_markup(f"<span size='xx-large'>{mark}</span>")
        flag.set_valign(Gtk.Align.CENTER)
        flag.set_halign(Gtk.Align.CENTER)
        flag.set_size_request(64, -1)
        grid.attach(flag, 0, 0, 1, 6)
        add_param(grid, 0, "Name", str(row.get("label") or iface))
        add_param(grid, 1, "Country", str(row.get("countryCode") or ""))
        add_param(grid, 2, "Obfuscation", obfuscation_label(row))
        add_param(grid, 3, "Ad blocking", str(row.get("adBlock") or ""))
        add_param(grid, 4, "Rate limit", str(row.get("rateLimit") or ""))
        add_param(grid, 5, "Endpoint", str(row.get("endpoint") or ""))
        buttons = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        buttons.set_valign(Gtk.Align.CENTER)
        buttons.set_margin_start(8)
        on_button = Gtk.Button.new_with_label("ON")
        off_button = Gtk.Button.new_with_label("OFF")
        for button, css in ((on_button, "on-button"), (off_button, "off-button")):
            button.set_size_request(88, 42)
            button.get_style_context().add_class(css)
        if active:
            on_button.get_style_context().add_class("is-current")
        else:
            off_button.get_style_context().add_class("is-current")
        on_button.connect("clicked", lambda *_b, iface=iface: set_profile(iface, True))
        off_button.connect("clicked", lambda *_b, iface=iface: set_profile(iface, False))
        buttons.pack_start(on_button, False, False, 0)
        buttons.pack_start(off_button, False, False, 0)
        grid.attach(buttons, 3, 0, 1, 6)
        trash = Gtk.Button()
        trash.set_image(Gtk.Image.new_from_icon_name("user-trash-symbolic", Gtk.IconSize.BUTTON))
        trash.set_tooltip_text("Delete")
        trash.set_relief(Gtk.ReliefStyle.NONE)
        trash.set_valign(Gtk.Align.CENTER)
        trash.connect("clicked", lambda *_b, row=row: ask_delete(row))
        grid.attach(trash, 4, 0, 1, 6)
        card.add(grid)
        box.pack_start(card, False, False, 0)

    def ask_delete(row: dict) -> None:
        label = str(row.get("label") or row.get("iface") or "this VPN")
        dialog = Gtk.MessageDialog(
            transient_for=ensure_window(),
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text=f"Delete {label}?",
        )
        dialog.format_secondary_text("This removes the saved VPN from this computer.")
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Delete", Gtk.ResponseType.ACCEPT)
        accepted = dialog.run() == Gtk.ResponseType.ACCEPT
        dialog.destroy()
        if not accepted:
            return
        iface = str(row["iface"])
        ui["busy"] = True

        def work() -> None:
            error = ""
            try:
                engine.delete_profile(iface)
            except engine.EngineError as exc:
                error = str(exc)

            def done() -> bool:
                ui["busy"] = False
                if error:
                    alert(error)
                rebuild.signature = None
                rebuild()
                return False

            GLib.idle_add(done)

        threading.Thread(target=work, daemon=True).start()

    def start_import(text: str, name: str) -> None:
        ui["busy"] = True
        paint_status("Importing…", "busy", "Importing", sensitive=False)

        def work() -> None:
            error = ""
            try:
                engine.import_text(text, name)
            except engine.EngineError as exc:
                error = str(exc)

            def done() -> bool:
                ui["busy"] = False
                if error:
                    alert(error)
                rebuild.signature = None
                rebuild()
                return False

            GLib.idle_add(done)

        threading.Thread(target=work, daemon=True).start()

    def rebuild(*_args) -> bool:
        if ui.get("busy"):
            return True
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
            for row in shown:
                add_profile_card(profile_box, row)
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
                verb = "OFF" if active else "ON"
                menu_item(
                    f"{verb} {profile_caption(row)}",
                    lambda _item, iface=iface, turn_on=not active: set_profile(iface, turn_on),
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
        # A blocking file dialog stops the window answering the desktop, so
        # GNOME reports that Continuum VPN is not responding.
        present_window()
        chooser = Gtk.FileChooserNative.new(
            "Import Continuum VPN bundle",
            ui["window"],
            Gtk.FileChooserAction.OPEN,
            "Import",
            "Cancel",
        )
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

        def on_response(_native, response) -> None:
            if response == Gtk.ResponseType.ACCEPT:
                chosen = read_chosen_file(chooser)
                if chosen is not None:
                    start_import(chosen[1], chosen[0])
            chooser.destroy()

        chooser.connect("response", on_response)
        chooser.show()

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
        dialog.format_secondary_text("This replaces the optional package. Your saved profiles stay on this computer.")
        dialog.add_button("Not now", Gtk.ResponseType.CANCEL)
        dialog.add_button("Install", Gtk.ResponseType.ACCEPT)
        if dialog.run() != Gtk.ResponseType.ACCEPT:
            dialog.destroy()
            return
        dialog.destroy()
        try:
            filename = os.path.basename(urllib.parse.urlparse(found["url"]).path) or engine.release_asset_name()
            dest = os.path.join(engine.runtime_dir(), filename)
            urllib.request.urlretrieve(found["url"], dest)
        except Exception as exc:
            alert(f"Could not download the update: {exc}")
            return
        if found.get("format") == "pacman":
            install = ["pkexec", "pacman", "-U", "--noconfirm", dest]
        elif found.get("format") == "rpm":
            install = ["pkexec", "dnf", "install", "-y", dest]
        elif found.get("format") == "zypper":
            install = ["pkexec", "zypper", "--non-interactive", "install", "--allow-unsigned-rpm", dest]
        else:
            install = ["pkexec", "apt-get", "install", "-y", dest]
        result = os.spawnvp(os.P_WAIT, "pkexec", install)
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

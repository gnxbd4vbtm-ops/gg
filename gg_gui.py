#!/usr/bin/env python3

"""A Noctalia-launcher-style GTK4 frontend for the gg keybind assistant."""

import importlib.util
import pathlib
import re
import sys
import threading
import urllib.error
from dataclasses import dataclass

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

PROJECT_DIR = pathlib.Path(__file__).resolve().parent
STYLE_PATH = PROJECT_DIR / "style.css"
GTK4_DIR = pathlib.Path.home() / ".config" / "gtk-4.0"
NOCTALIA_CSS = GTK4_DIR / "noctalia.css"
APP_ID = "dev.local.gg.Gui"

# Noctalia rewrites these files when the desktop theme changes.
WATCHED_THEME_FILES = {"noctalia.css", "gtk.css", "settings.ini"}
COLOR_DEF_RE = re.compile(r"^\s*(@define-color\s+[^;]+;)", re.MULTILINE)


def load_core():
    source = PROJECT_DIR / "gg-ai.py"
    compiled = PROJECT_DIR / "gg-ai.pyc"
    path = source
    if compiled.is_file() and (
        not source.is_file()
        or compiled.stat().st_mtime >= source.stat().st_mtime
    ):
        path = compiled

    spec = importlib.util.spec_from_file_location("gg_core", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gg = load_core()

@dataclass(frozen=True)
class QuickAction:
    label: str
    action_id: str
    target: str
    shortcut: str
    action: str
    icon: str
    query: str


QUICK_ACTIONS = [
    QuickAction(
        "Open Firefox", "open_app", "firefox", "launch", "Open Firefox",
        "firefox", "open firefox",
    ),
    QuickAction(
        "Toggle floating", "toggle_floating", "",
        "super + alt + space", "Toggle floating mode for the focused window",
        "window-restore-symbolic", "toggle floating",
    ),
    QuickAction(
        "Fullscreen", "toggle_fullscreen", "", "super + f",
        "Toggle fullscreen for the focused window",
        "view-fullscreen-symbolic", "toggle fullscreen",
    ),
    QuickAction(
        "Next workspace", "workspace_next", "", "super + control + right",
        "Switch to the next workspace on the current monitor",
        "go-next-symbolic", "switch to next workspace",
    ),
    QuickAction(
        "Close Firefox", "close_app", "firefox", "super + q", "Close Firefox",
        "window-close-symbolic", "close firefox",
    ),
    QuickAction(
        "Screenshot", "screenshot_region", "", "print",
        "Take a region screenshot",
        "camera-photo-symbolic", "screenshot region",
    ),
    QuickAction(
        "Volume up", "volume_up", "", "xf86audioraisevolume",
        "Increase speaker volume",
        "audio-volume-high-symbolic", "volume up",
    ),
    QuickAction(
        "Lock screen", "session_lock", "", "super + l", "Lock the session",
        "system-lock-screen-symbolic", "lock the session",
    ),
]


class GGWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title("gg")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_default_size(860, 640)
        self.set_hide_on_close(False)
        self.set_opacity(0.98)
        self.add_css_class("gg-window")

        self.current = None
        self.busy = False
        self.api_key = ""
        self.binds = ""
        self.startup_error = None

        self._load_data()
        self._build_ui()
        self._setup_theme()

        key_controller = Gtk.EventControllerKey()
        key_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_controller)
        self.connect("map", self._on_map)
        self.connect("close-request", self._on_close_request)

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------
    def _load_data(self):
        try:
            self.api_key = gg.KEY_FILE.read_text().strip()
            self.binds = gg.CONFIG.read_text()
        except OSError as error:
            self.startup_error = f"Could not load gg configuration: {error}"
            return

        if not self.api_key:
            self.startup_error = "Groq API key is empty."
        elif not self.binds:
            self.startup_error = "Hyprland keybind configuration is empty."

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        root.add_css_class("gg-shell")
        root.set_margin_top(18)
        root.set_margin_bottom(18)
        root.set_margin_start(18)
        root.set_margin_end(18)
        self.set_child(root)

        root.append(self._build_header())
        root.append(self._build_search())
        root.append(self._build_result_card())
        root.append(self._build_quick_actions())
        root.append(self._build_footer())

    def _build_header(self):
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)

        logo = Gtk.Label(label="gg")
        logo.add_css_class("gg-logo")
        logo.set_size_request(46, 46)
        logo.set_halign(Gtk.Align.CENTER)
        logo.set_valign(Gtk.Align.CENTER)
        header.append(logo)

        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        title = Gtk.Label(label="Hyprland keybinds", xalign=0)
        title.add_css_class("gg-title")
        subtitle = Gtk.Label(
            label="Ask for an action or search a shortcut", xalign=0
        )
        subtitle.add_css_class("gg-subtitle")
        titles.append(title)
        titles.append(subtitle)
        header.append(titles)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        header.append(spacer)

        close_button = Gtk.Button.new_from_icon_name("window-close-symbolic")
        close_button.add_css_class("gg-icon-button")
        close_button.set_tooltip_text("Close")
        close_button.connect("clicked", lambda *_: self.close())
        header.append(close_button)

        return header

    def _build_search(self):
        search = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        search.add_css_class("gg-search")

        search_icon = Gtk.Image.new_from_icon_name("system-search-symbolic")
        search_icon.set_pixel_size(18)
        search.append(search_icon)

        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("What do you want to do?")
        self.entry.set_hexpand(True)
        self.entry.add_css_class("gg-entry")
        self.entry.connect("activate", self._on_lookup)
        search.append(self.entry)

        self.lookup_button = Gtk.Button(label="Run")
        self.lookup_button.add_css_class("gg-secondary")
        self.lookup_button.connect("clicked", self._on_lookup)
        search.append(self.lookup_button)

        return search

    def _build_result_card(self):
        self.result_card = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=8
        )
        self.result_card.add_css_class("gg-result")
        self.result_card.set_visible(False)

        self.shortcut_label = Gtk.Label(label="")
        self.shortcut_label.set_xalign(0)
        self.shortcut_label.set_wrap(True)
        self.shortcut_label.add_css_class("gg-shortcut")
        self.result_card.append(self.shortcut_label)

        self.action_label = Gtk.Label(label="")
        self.action_label.set_xalign(0)
        self.action_label.set_wrap(True)
        self.action_label.add_css_class("gg-action")
        self.result_card.append(self.action_label)

        self.status_label = Gtk.Label(label="")
        self.status_label.set_xalign(0)
        self.status_label.set_wrap(True)
        self.status_label.add_css_class("gg-status")
        self.result_card.append(self.status_label)

        return self.result_card

    def _build_quick_actions(self):
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        container.set_vexpand(True)

        section = Gtk.Label(label="Quick actions", xalign=0)
        section.add_css_class("gg-section")
        container.append(section)

        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_homogeneous(True)
        flow.set_column_spacing(10)
        flow.set_row_spacing(10)
        flow.set_max_children_per_line(4)
        flow.set_min_children_per_line(2)
        flow.set_hexpand(True)
        flow.set_valign(Gtk.Align.START)

        for action in QUICK_ACTIONS:
            button = Gtk.Button()
            button.add_css_class("gg-quick")
            button.set_tooltip_text(action.query)

            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=9)
            icon = Gtk.Image.new_from_icon_name(action.icon)
            icon.set_pixel_size(18)
            row.append(icon)

            text = Gtk.Label(label=action.label, xalign=0)
            text.set_ellipsize(Pango.EllipsizeMode.END)
            row.append(text)

            button.set_child(row)
            button.connect(
                "clicked", lambda _button, a=action: self._on_quick_action(a)
            )
            flow.append(button)

        container.append(flow)
        return container

    def _build_footer(self):
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        footer.add_css_class("gg-footer")

        hint = Gtk.Label(
            label="Enter to run  ·  Esc to close",
            xalign=0,
        )
        hint.add_css_class("gg-footer-text")
        footer.append(hint)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        footer.append(spacer)

        model = Gtk.Label(label=gg.MODEL, xalign=1)
        model.add_css_class("gg-footer-text")
        footer.append(model)

        self.spinner = Gtk.Spinner()
        footer.append(self.spinner)

        return footer

    def _setup_theme(self):
        """Load the stylesheet and keep it in sync with Noctalia's theme."""
        self.css_provider = None
        self._reload_source = 0
        self._theme_monitor = None
        self._settings_signals = []

        self._install_css()

        try:
            directory = Gio.File.new_for_path(str(GTK4_DIR))
            self._theme_monitor = directory.monitor_directory(
                Gio.FileMonitorFlags.NONE, None
            )
            self._theme_monitor.connect(
                "changed", self._on_theme_file_changed
            )
        except GLib.Error as error:
            print(
                f"gg: could not watch {GTK4_DIR}: {error.message}",
                file=sys.stderr,
            )

        settings = Gtk.Settings.get_default()
        if settings is not None:
            for prop in (
                "gtk-theme-name",
                "gtk-application-prefer-dark-theme",
            ):
                self._settings_signals.append(
                    (
                        settings,
                        settings.connect(
                            f"notify::{prop}",
                            self._schedule_theme_reload,
                        ),
                    )
                )

        self.connect("destroy", self._teardown_theme)

    def _compose_css(self):
        """Prepend Noctalia's GTK colors to the GUI stylesheet."""
        try:
            style = STYLE_PATH.read_text(encoding="utf-8")
        except OSError:
            return None

        try:
            noctalia = NOCTALIA_CSS.read_text(encoding="utf-8")
        except OSError:
            noctalia = ""

        colors = COLOR_DEF_RE.findall(noctalia)
        if not colors:
            return style

        return "\n".join(colors) + "\n\n" + style

    def _install_css(self):
        css = self._compose_css()
        if css is None:
            return

        provider = Gtk.CssProvider()
        try:
            provider.load_from_data(css.encode("utf-8"), -1)
        except GLib.Error as error:
            print(
                f"gg: could not load stylesheet: {error.message}",
                file=sys.stderr,
            )
            return

        display = Gdk.Display.get_default()
        if display is None:
            return

        if self.css_provider is not None:
            Gtk.StyleContext.remove_provider_for_display(
                display, self.css_provider
            )

        Gtk.StyleContext.add_provider_for_display(
            display,
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
        self.css_provider = provider

    def _on_theme_file_changed(
        self, _monitor, file, _other_file, event_type
    ):
        if file is None:
            return
        if file.get_basename() not in WATCHED_THEME_FILES:
            return

        if event_type in (
            Gio.FileMonitorEvent.CHANGED,
            Gio.FileMonitorEvent.CHANGES_DONE_HINT,
            Gio.FileMonitorEvent.CREATED,
            Gio.FileMonitorEvent.DELETED,
            Gio.FileMonitorEvent.MOVED_IN,
            Gio.FileMonitorEvent.MOVED_OUT,
            Gio.FileMonitorEvent.RENAMED,
        ):
            self._schedule_theme_reload()

    def _schedule_theme_reload(self, *_args):
        # Theme switches write several files in quick succession.
        if self._reload_source:
            GLib.source_remove(self._reload_source)
        self._reload_source = GLib.timeout_add(150, self._reload_theme)

    def _reload_theme(self):
        self._reload_source = 0
        self._install_css()
        return GLib.SOURCE_REMOVE

    def _teardown_theme(self, *_args):
        if self._reload_source:
            GLib.source_remove(self._reload_source)
            self._reload_source = 0

        if self._theme_monitor is not None:
            self._theme_monitor.cancel()
            self._theme_monitor = None

        for settings, handler_id in self._settings_signals:
            settings.disconnect(handler_id)
        self._settings_signals = []

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------
    def _on_close_request(self, *_args):
        # Closing the launcher exits the whole process; nothing stays resident.
        self.get_application().quit()
        return False

    def _on_map(self, *_args):
        self.entry.grab_focus()
        self.entry.select_region(0, -1)
        self.spinner.stop()

    def _on_quick_action(self, action):
        # Quick actions use known allowlisted IDs directly; no AI round-trip.
        self.entry.set_text(action.query)
        self._apply_lookup(
            action.query,
            action.shortcut,
            action.action,
            action.action_id,
            action.target,
        )

    def _on_lookup(self, *_args):
        if self.busy:
            return

        query = self.entry.get_text().strip()
        if not query:
            return

        if self.startup_error is not None:
            self._show_error(self.startup_error)
            return

        self.busy = True
        self.lookup_button.set_sensitive(False)
        self.spinner.start()
        self.result_card.set_visible(True)
        self.shortcut_label.set_text("…")
        self.action_label.set_text(query)
        self.status_label.set_text("Thinking…")

        threading.Thread(
            target=self._lookup_worker, args=(query,), daemon=True
        ).start()

    def _lookup_worker(self, query):
        try:
            content = gg.fetch_ai_response(self.api_key, query, self.binds)
            shortcut, action, action_id, target = gg.parse_ai_content(content)
        except urllib.error.HTTPError as error:
            try:
                detail = error.read().decode(errors="replace").strip()
            except Exception:
                detail = ""
            message = f"Groq API error ({error.code})"
            if detail:
                message = f"{message}: {detail}"
            GLib.idle_add(self._show_error, message)
            return
        except urllib.error.URLError as error:
            GLib.idle_add(self._show_error, f"Network error: {error.reason}")
            return
        except Exception as error:
            GLib.idle_add(
                self._show_error, f"Invalid response from Groq: {error}"
            )
            return

        GLib.idle_add(
            self._apply_lookup,
            query,
            shortcut,
            action,
            action_id,
            target,
        )

    def _apply_lookup(self, query, shortcut, action, action_id, target):
        self.busy = False
        self.spinner.stop()
        self.lookup_button.set_sensitive(True)
        self.current = (query, shortcut, action, action_id, target)

        self.shortcut_label.set_text(shortcut or "No shortcut")
        self.action_label.set_text(action or "No matching keybind found")

        reason = self._refusal_reason(
            query, shortcut, action, action_id, target
        )
        if reason is not None:
            self.status_label.set_text(f"Not executed: {reason}.")
            return

        self._start_execution(action_id, target)

    def _show_error(self, message):
        self.busy = False
        self.spinner.stop()
        self.lookup_button.set_sensitive(True)
        self.current = None
        self.result_card.set_visible(True)
        self.shortcut_label.set_text("!")
        self.action_label.set_text(message)
        self.status_label.set_text("")

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def _refusal_reason(self, query, shortcut, action, action_id, target):
        dangerous = gg.dangerous_query_reason(query)
        if dangerous is not None:
            return dangerous

        if action_id in {"close_window", "close_app"} and any(
            term in query.lower() for term in gg.FORCE_KILL_TERMS
        ):
            return "force-killing windows is not supported"

        return gg.execution_refusal_reason(
            shortcut, action, action_id, target
        )

    def _start_execution(self, action_id, target):
        self.busy = True
        self.lookup_button.set_sensitive(False)
        self.spinner.start()
        self.status_label.set_text("Running…")

        # Hide first so focus-dependent actions affect the previous window and
        # so the launcher does not cover the app it opens.
        self.hide()
        GLib.timeout_add(180, self._execute_after_hide, action_id, target)

    def _execute_after_hide(self, action_id, target):
        threading.Thread(
            target=self._execute_worker, args=(action_id, target), daemon=True
        ).start()
        return GLib.SOURCE_REMOVE

    def _execute_worker(self, action_id, target):
        try:
            ok, message = gg.execute_action(action_id, target)
        except Exception as error:
            ok, message = False, str(error)
        GLib.idle_add(self._apply_execution, ok, message)

    def _apply_execution(self, ok, message):
        self.busy = False
        self.spinner.stop()
        if ok:
            # The launcher's job is done; do not stay resident.
            self.get_application().quit()
            return

        self.status_label.set_text(f"Execution failed: {message}")
        self.lookup_button.set_sensitive(True)
        self.present()

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------
    def _on_key_pressed(self, _controller, keyval, _keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True

        if keyval == Gdk.KEY_q and (state & Gdk.ModifierType.CONTROL_MASK):
            self.get_application().quit()
            return True

        return False


class GGApplication(Gtk.Application):
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.window = None

    def do_activate(self):
        if self.window is None:
            self.window = GGWindow(self)

        # Closing the window quits the app.  A second launch while it is open
        # just focuses the existing window.
        self.window.present()


def main():
    GLib.set_prgname("gg-gui")
    GLib.set_application_name("gg")
    app = GGApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())

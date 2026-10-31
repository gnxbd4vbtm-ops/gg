# gg

A Hyprland keybind assistant with a CLI and a Noctalia-launcher-style GTK4 GUI.

## CLI

```fish
gg "toggle floating"
gg -d "toggle floating"
gg --execute "switch to next workspace"
gg -d "close firefox"
gg -d "open firefox"
```

Without an execution flag, `gg` only looks up the matching keybind.

## GUI

Press `SUPER + H`, or run:

```sh
~/Projects/gg/gg-gui
```

Type what you want and press `Enter`. Valid allowlisted actions run
immediately; there is no command preview or Execute button. The launcher hides
before running so window actions affect the window you were using, then exits
completely on success. If something fails, the window comes back with the error.

The quick-action buttons use fixed allowlisted action IDs directly, so things
like **Close Firefox** and **Open Firefox** do not depend on the AI service.

Keyboard:

- `Enter` — look up and run the action
- `Esc` — close the launcher and exit the process
- `Ctrl+Q` — quit the GUI process

The GUI does not stay resident in the background. Closing the window or
pressing `Esc` terminates the process completely; it starts again the next time
you press `SUPER + H`.

The GUI follows Noctalia theme changes while it is open. It watches
`~/.config/gtk-4.0/noctalia.css`, `gtk.css`, and `settings.ini`, plus GTK theme
notifications, and reloads its stylesheet automatically without a restart.

## Building

```sh
cd ~/Projects/gg
./build.sh
```

`build.sh` precompiles `gg-ai.py` and `gg_gui.py` to `.pyc` bytecode and
compiles `launcher.c` into `gg-gui-bin`, a native ELF entrypoint that embeds
the system CPython. `gg-gui` uses the native binary when present and falls back
to `python3` otherwise. This is not a fully standalone bundle: it still uses
the system Python, GTK4, and PyGObject.

## Safety

- The AI returns only `shortcut`, `action`, `action_id`, and `target`.
- Only `action_id` values in the Python allowlist can execute.
- Commands are fixed argv tuples executed without a shell.
- `close_app` resolves the app name against live Hyprland windows and validates
  the window address before inserting it into a fixed dispatcher template.
- `open_app` maps the app name to a fixed launch command from a small allowlist;
  unknown apps are refused. Existing windows are focused instead of duplicated.
- `hyprctl kill`, kill mode, and force-kill requests are never executed.
- Ambiguous, missing, or unsupported actions are refused.

## Files

- `gg-ai.py` — CLI, API client, allowlist, and execution engine
- `gg_gui.py` — GTK4 launcher-style GUI
- `gg-gui` — GUI launcher script
- `launcher.c` — native CPython-embedding entrypoint
- `build.sh` — compiles bytecode and the native launcher
- `style.css` — GUI styling using the active Noctalia GTK colors

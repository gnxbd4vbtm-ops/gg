#!/bin/sh
# Precompile the Python sources to bytecode and build the native entrypoint.
# Run this after editing gg-ai.py, gg_gui.py, or launcher.c.
set -eu

DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$DIR"

python3 -m compileall -q -b -f gg-ai.py gg_gui.py
printf 'Compiled bytecode:\n  %s\n  %s\n' "$DIR/gg-ai.pyc" "$DIR/gg_gui.pyc"

if command -v gcc >/dev/null 2>&1 && command -v python3-config >/dev/null 2>&1; then
    if gcc -O2 -o gg-gui-bin launcher.c $(python3-config --embed --cflags --ldflags); then
        printf 'Compiled native launcher:\n  %s\n' "$DIR/gg-gui-bin"
    else
        printf 'Warning: could not build gg-gui-bin; gg-gui will use Python.\n' >&2
    fi
else
    printf 'Warning: gcc or python3-config missing; skipping native launcher.\n' >&2
fi

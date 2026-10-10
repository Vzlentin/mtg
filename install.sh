#!/bin/sh
# Installs mtg into $PREFIX/bin, ~/.local/bin by default.
# From a clone it links bin/mtg, so git pull updates it. Piped from curl it downloads bin/mtg.
set -eu

PREFIX=${PREFIX:-"$HOME/.local"}
BIN_DIR="$PREFIX/bin"
RAW_URL=${MTG_RAW_URL:-https://raw.githubusercontent.com/Vzlentin/mtg/main/bin/mtg}

if ! command -v python3 >/dev/null 2>&1; then
    echo "mtg needs python3 (3.9 or newer)" >&2
    exit 1
fi

python3 - <<'EOF'
import sqlite3
import sys

if sys.version_info < (3, 9):
    sys.exit("mtg needs Python 3.9 or newer")
try:
    sqlite3.connect(":memory:").execute("SELECT json_extract('{}', '$')")
except sqlite3.Error:
    sys.exit("mtg needs SQLite with JSON support in Python's sqlite3")
EOF

mkdir -p "$BIN_DIR"
source_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" 2>/dev/null && pwd) || source_dir=""

if [ -n "$source_dir" ] && [ -f "$source_dir/bin/mtg" ]; then
    ln -sfn "$source_dir/bin/mtg" "$BIN_DIR/mtg"
    echo "linked $BIN_DIR/mtg -> $source_dir/bin/mtg"
else
    curl -fsSL "$RAW_URL" -o "$BIN_DIR/mtg.download"
    chmod +x "$BIN_DIR/mtg.download"
    mv "$BIN_DIR/mtg.download" "$BIN_DIR/mtg"
    echo "downloaded $BIN_DIR/mtg"
fi

case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo "add $BIN_DIR to your PATH" ;;
esac
echo "next: run mtg upgrade to download the card data (about 90 MB)"

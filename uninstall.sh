#!/usr/bin/env bash
# Remove everything install.sh created. Snapshots are kept unless --purge.
set -euo pipefail

APP="gnome-terminal-restore"
PREFIX="${PREFIX:-$HOME/.local}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
BASHRC="${BASHRC:-$HOME/.bashrc}"
PURGE=0

while [ $# -gt 0 ]; do
    case "$1" in
        --prefix) PREFIX="$2"; shift 2 ;;
        --prefix=*) PREFIX="${1#*=}"; shift ;;
        --purge) PURGE=1; shift ;;
        -h|--help)
            echo "Usage: ./uninstall.sh [--prefix DIR] [--purge]"
            echo "  --purge  also delete saved snapshots in $DATA_HOME/$APP"
            exit 0 ;;
        *) echo "uninstall.sh: unknown option: $1" >&2; exit 2 ;;
    esac
done

if command -v systemctl >/dev/null 2>&1; then
    systemctl --user disable --now gt-save.timer gt-save-shutdown.service 2>/dev/null || true
fi
rm -f "$CONFIG_HOME/systemd/user/gt-save.service" \
      "$CONFIG_HOME/systemd/user/gt-save.timer" \
      "$CONFIG_HOME/systemd/user/gt-save-shutdown.service"
if command -v systemctl >/dev/null 2>&1; then
    systemctl --user daemon-reload || true
fi

rm -f "$CONFIG_HOME/autostart/gt-restore.desktop"
rm -f "$PREFIX/bin/gt-save" "$PREFIX/bin/gt-restore"
rm -rf "${PREFIX:?}/lib/$APP"

if [ -f "$BASHRC" ] && grep -qF ">>> $APP >>>" "$BASHRC"; then
    tmp="$(mktemp)"
    sed "/>>> $APP >>>/,/<<< $APP <<</d" "$BASHRC" > "$tmp"
    cat "$tmp" > "$BASHRC"
    rm -f "$tmp"
    echo "removed the shell hook from $BASHRC"
fi

if [ "$PURGE" -eq 1 ]; then
    rm -rf "${DATA_HOME:?}/$APP"
    echo "deleted snapshots in $DATA_HOME/$APP"
else
    echo "snapshots kept in $DATA_HOME/$APP (use --purge to delete them)"
fi

echo "$APP removed."

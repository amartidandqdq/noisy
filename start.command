#!/usr/bin/env bash
# start.command - macOS double-clickable launcher
# Finder peut lancer les .command directement; delegue a start.sh.

cd "$(dirname "$0")"
exec ./start.sh "$@"

#!/usr/bin/env bash
# Quick entrypoint to run the Nuitka macOS build pipeline.
exec "$(dirname "$0")/tools/build_nuitka_all.sh" "$@"

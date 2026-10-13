#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copy igz_steel into the per-user IngeTrazo plugins folder on Windows.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${APPDATA}/ingetrazo/plugins/igz_steel"
mkdir -p "${DEST}"
rm -rf "${DEST:?}"/*
cp -r "${ROOT}/igz_steel/." "${DEST}/"
find "${DEST}" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
echo "installed to ${DEST} — restart IngeTrazo"

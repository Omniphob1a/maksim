#!/usr/bin/env bash
set -euo pipefail
export UV_CACHE_DIR=/workspace/.cache/uv
export MPLCONFIGDIR=/workspace/.cache/matplotlib
export XDG_CACHE_HOME=/workspace/.cache
mkdir -p "$UV_CACHE_DIR" "$MPLCONFIGDIR" "$XDG_CACHE_HOME"
cd /workspace/maksim
uv sync --frozen --extra dev

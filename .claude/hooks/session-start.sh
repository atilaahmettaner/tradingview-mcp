#!/bin/bash
set -euo pipefail

# Only run in remote Claude Code environments
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

echo '{"async": true, "asyncTimeout": 300000}'

cd "$CLAUDE_PROJECT_DIR"

echo "Installing Python dependencies with uv..."
uv sync

echo "Setting PYTHONPATH..."
echo 'export PYTHONPATH="src"' >> "$CLAUDE_ENV_FILE"

echo "Session start hook complete."

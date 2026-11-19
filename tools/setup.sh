#!/usr/bin/env bash
# Install or update claude-settings into ~/.claude.
#
#   curl -fsSL https://raw.githubusercontent.com/flysangel/claude-settings/main/tools/setup.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/flysangel/claude-settings/main/tools/setup.sh | bash -s -- --replace
#   curl -fsSL https://raw.githubusercontent.com/flysangel/claude-settings/main/tools/setup.sh | bash -s -- remove
#
# Exit codes: those of tools/deploy.py, plus 3 when a required command is missing.
set -eu

# The public repository this script installs from.
DEFAULT_REPO_URL="https://github.com/flysangel/claude-settings.git"

REPO_URL="${CLAUDE_SETTINGS_REPO:-$DEFAULT_REPO_URL}"
CLONE_DIR="$HOME/.claude-settings"

missing=0
for cmd in git uv; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    printf '%-9s %s\n' missing "$cmd"
    missing=1
  fi
done
if [ "$missing" -ne 0 ]; then
  echo "Install the missing commands and run this again. Nothing was written."
  exit 3
fi

if [ -z "$REPO_URL" ]; then
  echo "error: the repository URL is not configured in setup.sh" >&2
  exit 1
fi

if [ -d "$CLONE_DIR/.git" ]; then
  if ! git -C "$CLONE_DIR" pull --ff-only --quiet; then
    echo "error: could not update $CLONE_DIR" >&2
    exit 1
  fi
elif [ -e "$CLONE_DIR" ]; then
  echo "error: $CLONE_DIR exists and is not a clone made by this tool" >&2
  exit 1
else
  if ! git clone --quiet "$REPO_URL" "$CLONE_DIR"; then
    echo "error: could not clone $REPO_URL" >&2
    exit 1
  fi
fi

exec uv run --quiet "$CLONE_DIR/tools/deploy.py" "$@"

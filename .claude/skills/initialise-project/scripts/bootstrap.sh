#!/usr/bin/env bash
# Bootstrap a new project with the standard Claude Code folder structure.
# Usage: bootstrap.sh <target_path>

TEMPLATE_SRC="c:/Users/luidpv/OneDrive - Henkel/Documents/GitHub_personal/CDV_2"

TARGET="$1"

if [ -z "$TARGET" ]; then
  echo "Usage: bootstrap.sh <target_path>"
  exit 1
fi

# Create target if it doesn't exist
mkdir -p "$TARGET"

ITEMS=(
  ".claude"
  ".claude-flow"
  ".swarm"
  ".cursor"
  "CLAUDE.md"
  ".mcp.json"
  ".gitignore"
)

COPIED=()
SKIPPED=()

for ITEM in "${ITEMS[@]}"; do
  SRC="$TEMPLATE_SRC/$ITEM"
  DST="$TARGET/$ITEM"

  if [ ! -e "$SRC" ]; then
    echo "  [WARN] Source not found, skipping: $ITEM"
    continue
  fi

  if [ -e "$DST" ]; then
    SKIPPED+=("$ITEM")
    continue
  fi

  if [ -d "$SRC" ]; then
    cp -r "$SRC" "$DST"
  else
    cp "$SRC" "$DST"
  fi
  COPIED+=("$ITEM")
done

echo ""
echo "Bootstrap complete: $TARGET"
echo ""

if [ ${#COPIED[@]} -gt 0 ]; then
  echo "Copied:"
  for ITEM in "${COPIED[@]}"; do
    echo "  + $ITEM"
  done
fi

if [ ${#SKIPPED[@]} -gt 0 ]; then
  echo ""
  echo "Skipped (already exist):"
  for ITEM in "${SKIPPED[@]}"; do
    echo "  ~ $ITEM"
  done
fi

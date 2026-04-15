#!/usr/bin/env bash
# Install upbeat Claude Code skills
#
# Usage:
#   ./install.sh                  install all skills globally (~/.claude/commands/)
#   ./install.sh mcu              install only the mcu skill globally
#   ./install.sh --project        install all skills into current project (.claude/commands/)
#   ./install.sh mcu --project    install mcu skill into current project

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="$SCRIPT_DIR/skills"

# ── parse args ──────────────────────────────────────────────────────────────
SKILL_FILTER=""
PROJECT_MODE=false

for arg in "$@"; do
    case "$arg" in
        --project) PROJECT_MODE=true ;;
        --help|-h)
            echo "Usage: $0 [skill_name] [--project]"
            echo ""
            echo "  skill_name   Install only this skill (default: all)"
            echo "  --project    Install to current project's .claude/commands/"
            echo "               (default: ~/.claude/commands/)"
            exit 0
            ;;
        *) SKILL_FILTER="$arg" ;;
    esac
done

if $PROJECT_MODE; then
    DEST="$(pwd)/.claude/commands"
    echo "Installing to project: $DEST"
else
    DEST="$HOME/.claude/commands"
    echo "Installing globally: $DEST"
fi

mkdir -p "$DEST"

# ── install one skill ───────────────────────────────────────────────────────
# skills/ mirrors .claude/commands/ exactly:
#   skills/mcu.md        → commands/mcu.md
#   skills/mcu/          → commands/mcu/
install_skill() {
    local name="$1"

    if [ ! -f "$SKILLS_DIR/$name.md" ]; then
        echo "Error: skill '$name' not found (missing $SKILLS_DIR/$name.md)" >&2
        exit 1
    fi

    echo "  Installing: $name"
    cp "$SKILLS_DIR/$name.md" "$DEST/$name.md"

    if [ -d "$SKILLS_DIR/$name" ]; then
        mkdir -p "$DEST/$name"
        cp -r "$SKILLS_DIR/$name/." "$DEST/$name/"
    fi

    echo "  -> /$name skill ready"
}

# ── run ─────────────────────────────────────────────────────────────────────
if [ -n "$SKILL_FILTER" ]; then
    install_skill "$SKILL_FILTER"
else
    for md in "$SKILLS_DIR"/*.md; do
        [ -f "$md" ] || continue
        install_skill "$(basename "$md" .md)"
    done
fi

echo ""
echo "Done. Restart Claude Code to pick up new skills."

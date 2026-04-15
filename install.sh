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

# ── install one skill ───────────────────────────────────────────────────────
install_skill() {
    local name="$1"
    local skill_dir="$SKILLS_DIR/$name"

    if [ ! -d "$skill_dir" ]; then
        echo "Error: skill '$name' not found in $SKILLS_DIR" >&2
        exit 1
    fi

    echo "  Installing: $name"
    mkdir -p "$DEST/$name"

    # copy skill markdown (e.g. mcu.md → commands/mcu.md)
    if [ -f "$skill_dir/$name.md" ]; then
        cp "$skill_dir/$name.md" "$DEST/$name.md"
    fi

    # copy all companion files into commands/<name>/
    for f in "$skill_dir"/*; do
        fname="$(basename "$f")"
        if [ "$fname" != "$name.md" ]; then
            cp "$f" "$DEST/$name/$fname"
        fi
    done

    echo "  -> /$name skill ready"
}

# ── run ─────────────────────────────────────────────────────────────────────
if [ -n "$SKILL_FILTER" ]; then
    install_skill "$SKILL_FILTER"
else
    for skill_dir in "$SKILLS_DIR"/*/; do
        [ -d "$skill_dir" ] || continue
        install_skill "$(basename "$skill_dir")"
    done
fi

echo ""
echo "Done. Restart Claude Code to pick up new skills."

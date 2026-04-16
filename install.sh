#!/usr/bin/env bash
# Install upbeat agent skills (Claude Code or Gemini CLI)
#
# Usage:
#   ./install.sh                  install all skills for Claude to current project (.claude/commands/)
#   ./install.sh --agent gemini   install all skills for Gemini to current project (.agents/skills/)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="$SCRIPT_DIR/skills"

# ── parse args ──────────────────────────────────────────────────────────────
AGENT="claude"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --agent|-a) AGENT="$2"; shift 2 ;;
        --help|-h)
            echo "Usage: $0 [--agent claude|gemini]"
            echo ""
            echo "  --agent, -a  Target agent: 'claude' (default) or 'gemini'"
            exit 0
            ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

# ── set destination (always local project) ──────────────────────────────────
if [ "$AGENT" == "claude" ]; then
    DEST="$(pwd)/.claude/commands"
elif [ "$AGENT" == "gemini" ]; then
    DEST="$(pwd)/.agents/skills"
else
    echo "Error: unsupported agent '$AGENT'. Use 'claude' or 'gemini'." >&2
    exit 1
fi

echo "Installing for $AGENT to local project: $DEST"
mkdir -p "$DEST"

# ── install logic ───────────────────────────────────────────────────────────
install_skill() {
    local name="$1"
    local md_source="$SKILLS_DIR/$name.md"
    local dir_source="$SKILLS_DIR/$name"

    echo "  Installing: $name"

    if [ "$AGENT" == "claude" ]; then
        cp "$md_source" "$DEST/$name.md"
        if [ -d "$dir_source" ]; then
            mkdir -p "$DEST/$name"
            cp -r "$dir_source/." "$DEST/$name/"
        fi
    elif [ "$AGENT" == "gemini" ]; then
        mkdir -p "$DEST/$name"
        cp "$md_source" "$DEST/$name/SKILL.md"
        if [ -d "$dir_source" ]; then
            cp -r "$dir_source/." "$DEST/$name/"
        fi
    fi
}

# ── run ─────────────────────────────────────────────────────────────────────
for md in "$SKILLS_DIR"/*.md; do
    [ -f "$md" ] || continue
    install_skill "$(basename "$md" .md)"
done

echo ""
echo "Done. Restart your agent to pick up new skills."

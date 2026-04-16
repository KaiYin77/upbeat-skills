#!/usr/bin/env bash
# Install upbeat agent skills (Claude Code or Gemini CLI)
#
# One-liner (interactive — picks agent):
#   curl -fsSL https://raw.githubusercontent.com/KaiYin77/upbeat-skills/main/install.sh | bash
#
# One-liner (specific agent, non-interactive):
#   curl -fsSL https://raw.githubusercontent.com/KaiYin77/upbeat-skills/main/install.sh | bash -s -- --agent gemini
#   curl -fsSL https://raw.githubusercontent.com/KaiYin77/upbeat-skills/main/install.sh | bash -s -- --agent claude
#
# Local usage:
#   ./install.sh                  interactive agent picker, installs all skills
#   ./install.sh --agent gemini   install all skills for Gemini (non-interactive)
#   ./install.sh --agent claude   install all skills for Claude Code (non-interactive)

set -euo pipefail

REPO_TARBALL="https://github.com/KaiYin77/upbeat-skills/archive/refs/heads/main.tar.gz"
AGENT=""
_TMP=""

# ── parse args ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --agent|-a) AGENT="$2"; shift 2 ;;
        --help|-h)
            echo "Usage: $0 [--agent claude|gemini]"
            echo ""
            echo "  --agent, -a  Target agent: 'claude' or 'gemini'"
            echo "               Omit to use the interactive agent picker."
            echo ""
            echo "All skills are always installed."
            exit 0 ;;
        *) echo "Error: unknown argument '$1'" >&2; exit 1 ;;
    esac
done

if [ -n "$AGENT" ] && [ "$AGENT" != "claude" ] && [ "$AGENT" != "gemini" ]; then
    echo "Error: unsupported agent '$AGENT'. Use 'claude' or 'gemini'." >&2
    exit 1
fi

# ── locate skills dir (local vs piped) ───────────────────────────────────────
# When piped via curl, BASH_SOURCE[0] is unset/empty — fall through to download.
_SCRIPT_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ]; then
    _SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || true
fi
SKILLS_DIR="$_SCRIPT_DIR/skills"

if [ ! -d "$SKILLS_DIR" ]; then
    echo "Downloading upbeat-skills from GitHub..."
    _TMP="$(mktemp -d)"
    trap 'rm -rf "$_TMP"' EXIT
    curl -fsSL "$REPO_TARBALL" | tar -xz -C "$_TMP" --strip-components=1
    SKILLS_DIR="$_TMP/skills"
fi

# ── collect available skills ──────────────────────────────────────────────────
SKILL_NAMES=()
for md in "$SKILLS_DIR"/*.md; do
    [ -f "$md" ] || continue
    SKILL_NAMES+=("$(basename "$md" .md)")
done

if [ "${#SKILL_NAMES[@]}" -eq 0 ]; then
    echo "Error: no skills found in $SKILLS_DIR" >&2
    exit 1
fi

# ── interactive agent picker (only when --agent not supplied) ─────────────────
_pick_agent() {
    local tty_fd="$1"
    echo ""
    echo "  Which agent are you using?"
    echo ""
    echo "    [1] Claude Code  (.claude/commands/)"
    echo "    [2] Gemini CLI   (.agents/skills/)"
    echo ""
    printf "  Choice [1/2]: "
    local choice
    read -r choice <&"$tty_fd"
    case "$choice" in
        2) AGENT="gemini" ;;
        *)  AGENT="claude" ;;   # default to claude on Enter or '1'
    esac
}

if [ -z "$AGENT" ]; then
    if [ -t 0 ]; then
        _pick_agent 0
    elif [ -e /dev/tty ]; then
        exec 3</dev/tty
        _pick_agent 3
        exec 3<&-
    else
        echo "Non-interactive shell — defaulting to Claude Code." >&2
        AGENT="claude"
    fi
fi

# ── destination ───────────────────────────────────────────────────────────────
if [ "$AGENT" = "claude" ]; then
    DEST="$(pwd)/.claude/commands"
else
    DEST="$(pwd)/.agents/skills"
fi

# ── install ───────────────────────────────────────────────────────────────────
echo ""
echo "Installing for $AGENT → $DEST"
mkdir -p "$DEST"

_install_skill() {
    local name="$1"
    local md_src="$SKILLS_DIR/$name.md"
    local dir_src="$SKILLS_DIR/$name"

    echo "  + $name"

    if [ "$AGENT" = "claude" ]; then
        cp "$md_src" "$DEST/$name.md"
        if [ -d "$dir_src" ]; then
            mkdir -p "$DEST/$name"
            cp -r "$dir_src/." "$DEST/$name/"
        fi
    else  # gemini
        mkdir -p "$DEST/$name"
        cp "$md_src" "$DEST/$name/SKILL.md"
        if [ -d "$dir_src" ]; then
            cp -r "$dir_src/." "$DEST/$name/"
        fi
    fi
}

for skill in "${SKILL_NAMES[@]}"; do
    _install_skill "$skill"
done

echo ""
echo "Done. Restart your agent to pick up the new skills."

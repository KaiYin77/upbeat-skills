#!/usr/bin/env bash
# Install upbeat agent skills (Claude Code or Gemini CLI)
#
# One-liner (interactive):
#   curl -fsSL https://raw.githubusercontent.com/KaiYin77/upbeat-skills/master/install.sh | bash
#
# One-liner (all skills, specific agent):
#   curl -fsSL https://raw.githubusercontent.com/KaiYin77/upbeat-skills/master/install.sh | bash -s -- --all --agent gemini
#
# Local usage:
#   ./install.sh                  interactive for Claude
#   ./install.sh --all            install all for Claude
#   ./install.sh --agent gemini   interactive for Gemini

set -euo pipefail

REPO_TARBALL="https://github.com/KaiYin77/upbeat-skills/archive/refs/heads/master.tar.gz"
AGENT="claude"
INSTALL_ALL=false
_TMP=""

# ── parse args ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --agent|-a) AGENT="$2"; shift 2 ;;
        --all)      INSTALL_ALL=true; shift ;;
        --help|-h)
            echo "Usage: $0 [--agent claude|gemini] [--all]"
            echo ""
            echo "  --agent, -a  Target agent: 'claude' (default) or 'gemini'"
            echo "  --all        Install all skills without prompting"
            exit 0 ;;
        *) echo "Error: unknown argument '$1'" >&2; exit 1 ;;
    esac
done

if [ "$AGENT" != "claude" ] && [ "$AGENT" != "gemini" ]; then
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

# ── destination ───────────────────────────────────────────────────────────────
if [ "$AGENT" = "claude" ]; then
    DEST="$(pwd)/.claude/commands"
else
    DEST="$(pwd)/.agents/skills"
fi

# ── collect available skills with descriptions ────────────────────────────────
SKILL_NAMES=()
SKILL_DESCS=()
for md in "$SKILLS_DIR"/*.md; do
    [ -f "$md" ] || continue
    name="$(basename "$md" .md)"
    desc="$(grep -m1 '^description:' "$md" 2>/dev/null | sed 's/^description:[[:space:]]*//' || echo "")"
    SKILL_NAMES+=("$name")
    SKILL_DESCS+=("$desc")
done

if [ "${#SKILL_NAMES[@]}" -eq 0 ]; then
    echo "Error: no skills found in $SKILLS_DIR" >&2
    exit 1
fi

# ── interactive selection ─────────────────────────────────────────────────────
SELECTED=()

_pick_skills() {
    local tty_fd="$1"
    echo ""
    echo "  Available skills:"
    echo ""
    for i in "${!SKILL_NAMES[@]}"; do
        printf "    [%d] %-12s  %s\n" "$((i+1))" "${SKILL_NAMES[$i]}" "${SKILL_DESCS[$i]}"
    done
    echo ""
    echo "    [a] All skills"
    echo ""
    printf "  Which skills to install? (e.g. 1 2  or  a): "
    local choice
    read -r choice <&"$tty_fd"

    if [[ "$choice" == "a" || "$choice" == "A" || -z "$choice" ]]; then
        SELECTED=("${SKILL_NAMES[@]}")
    else
        for tok in $choice; do
            if [[ "$tok" =~ ^[0-9]+$ ]] && [ "$tok" -ge 1 ] && [ "$tok" -le "${#SKILL_NAMES[@]}" ]; then
                SELECTED+=("${SKILL_NAMES[$((tok-1))]}")
            else
                echo "  Warning: invalid selection '$tok', skipping." >&2
            fi
        done
    fi
}

if [ "$INSTALL_ALL" = true ]; then
    SELECTED=("${SKILL_NAMES[@]}")
elif [ -t 0 ]; then
    # stdin is a terminal — read directly
    _pick_skills 0
elif [ -e /dev/tty ]; then
    # stdin is a pipe (curl) — open controlling terminal explicitly
    exec 3</dev/tty
    _pick_skills 3
    exec 3<&-
else
    echo "Non-interactive shell detected — installing all skills."
    SELECTED=("${SKILL_NAMES[@]}")
fi

if [ "${#SELECTED[@]}" -eq 0 ]; then
    echo "No skills selected. Nothing to install."
    exit 0
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

for skill in "${SELECTED[@]}"; do
    _install_skill "$skill"
done

echo ""
echo "Done. Restart your agent to pick up the new skills."

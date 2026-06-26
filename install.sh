#!/usr/bin/env bash
#
# install.sh — install Pensieve for Claude Code.
#
#   git clone … && cd pensieve && ./install.sh
#
# What it does (idempotent — safe to re-run anytime to pick up changes):
#   1. checks all prerequisites up front (changes NOTHING if any are missing)
#   2. ensures pipx
#   3. pipx-installs Pensieve (editable -> your code changes are picked up)
#   4. installs the Claude skill to ~/.claude/skills/pensieve/
#   5. registers the MCP server (user scope) -> available in every Claude session
#
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_SRC="$REPO_DIR/adapters/claude/SKILL.md"
SKILL_DIR="$HOME/.claude/skills/pensieve"
MIN_PY_MINOR=12  # require Python 3.12+

bold() { printf "\n\033[1m%s\033[0m\n" "$1"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$1"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$1"; }
err()  { printf "  \033[31m✗\033[0m %s\n" "$1"; }

# ---------------------------------------------------------------------------
# 1. Preflight — check everything BEFORE touching anything
# ---------------------------------------------------------------------------
bold "Pensieve installer — checking prerequisites"
missing=0

PY=""
for cand in python3.12 python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
  err "Python not found. Install Python 3.${MIN_PY_MINOR}+ and re-run."
  missing=1
else
  pyver="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "0.0")"
  if [ "${pyver%%.*}" -ne 3 ] || [ "${pyver##*.}" -lt "$MIN_PY_MINOR" ]; then
    err "Python 3.${MIN_PY_MINOR}+ required, found $pyver ($PY)."
    missing=1
  else
    ok "Python $pyver ($PY)"
  fi
fi

if [ -f "$REPO_DIR/pyproject.toml" ]; then ok "Project found"; else
  err "pyproject.toml not found in $REPO_DIR — run this from the repo root."; missing=1
fi

if [ -f "$SKILL_SRC" ]; then ok "Skill file present"; else
  err "Skill file missing: $SKILL_SRC"; missing=1
fi

HAVE_CLAUDE=1
if command -v claude >/dev/null 2>&1; then
  ok "Claude Code CLI"
else
  HAVE_CLAUDE=0
  warn "Claude Code CLI ('claude') not found — will install the tool + skill, but"
  warn "  you'll need to register the MCP server manually (shown at the end)."
fi

if [ "$missing" -ne 0 ]; then
  err "Missing prerequisites above. Nothing was changed — fix them and re-run."
  exit 1
fi

# ---------------------------------------------------------------------------
# 2. Ensure pipx
# ---------------------------------------------------------------------------
bold "Ensuring pipx"
if command -v pipx >/dev/null 2>&1; then
  ok "pipx already installed"
else
  warn "pipx not found — installing it"
  if command -v brew >/dev/null 2>&1; then
    if ! out="$(brew install pipx 2>&1)"; then err "brew install pipx failed:"; echo "$out"; exit 1; fi
  elif ! out="$("$PY" -m pip install --user pipx 2>&1)"; then
    err "Could not install pipx automatically:"; echo "$out"
    err "Install it manually (https://pipx.pypa.io) and re-run."; exit 1
  fi
  "$PY" -m pipx ensurepath >/dev/null 2>&1 || true
  hash -r 2>/dev/null || true
  command -v pipx >/dev/null 2>&1 || { err "pipx installed but not on PATH — open a new shell and re-run."; exit 1; }
  ok "pipx installed"
fi
PIPX_BIN="$(pipx environment --value PIPX_BIN_DIR 2>/dev/null || echo "$HOME/.local/bin")"

# ---------------------------------------------------------------------------
# 3. Install / update Pensieve (editable -> picks up code changes on re-run)
# ---------------------------------------------------------------------------
bold "Installing Pensieve (pipx, editable)"
VENVS="$(pipx environment --value PIPX_LOCAL_VENVS 2>/dev/null || echo "$HOME/.local/pipx/venvs")"
want="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
cur=""
[ -x "$VENVS/pensieve/bin/python" ] && \
  cur="$("$VENVS/pensieve/bin/python" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
if [ "$cur" = "$want" ]; then
  ok "already installed on Python $cur (editable — code changes are already live)"
else
  [ -n "$cur" ] && { pipx uninstall pensieve >/dev/null 2>&1 || true; }  # recreate on the right Python
  if ! out="$(pipx install --python "$PY" --editable "$REPO_DIR" 2>&1)"; then
    err "pipx install failed:"; echo "$out"; exit 1
  fi
  ok "pensieve + pensieve-mcp (Python $want) -> $PIPX_BIN"
fi

# ---------------------------------------------------------------------------
# 4. Install the Claude skill
# ---------------------------------------------------------------------------
bold "Installing the Claude skill"
mkdir -p "$SKILL_DIR" && cp -f "$SKILL_SRC" "$SKILL_DIR/SKILL.md"
ok "skill -> $SKILL_DIR/SKILL.md"

# ---------------------------------------------------------------------------
# 5. Register the MCP server (user scope)
# ---------------------------------------------------------------------------
bold "Registering the Pensieve MCP server (user scope)"
# No pinned store — the server is cwd-aware: it reads PENSIEVE_HOME from the .env of
# wherever Claude Code is launched, else defaults to ~/.pensieve. So launching in this
# repo uses the dev store (.local/manual, via .env) for testing; anywhere else uses
# your real ~/.pensieve.
if [ "$HAVE_CLAUDE" -eq 1 ]; then
  claude mcp remove pensieve --scope user >/dev/null 2>&1 || true
  if claude mcp add pensieve --scope user -- "$PIPX_BIN/pensieve-mcp" >/dev/null 2>&1; then
    ok "registered 'pensieve' -> $PIPX_BIN/pensieve-mcp  (store: ~/.pensieve; repo .env when launched in-repo)"
  else
    err "Failed to register. Run manually:"
    err "  claude mcp add pensieve --scope user -- $PIPX_BIN/pensieve-mcp"; exit 1
  fi
else
  warn "Skipped MCP registration. To finish, run:"
  warn "  claude mcp add pensieve --scope user -- $PIPX_BIN/pensieve-mcp"
fi

# ---------------------------------------------------------------------------
bold "✅ Pensieve installed."
echo "   Restart Claude Code, then from any directory try:"
echo "     \"what streams do I have? check pensieve\""
echo "   CLI:   pensieve ls   |   pensieve create --stream \"Travel\" --purpose \"…\""
echo "   Store: ~/.pensieve"

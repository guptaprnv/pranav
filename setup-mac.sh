#!/bin/bash
set -e

echo "==> Checking dependencies..."

# Install Homebrew if missing
if ! command -v brew &>/dev/null; then
  echo "==> Installing Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

# Install tmux if missing
if ! command -v tmux &>/dev/null; then
  echo "==> Installing tmux..."
  brew install tmux
fi

# Install node if missing
if ! command -v node &>/dev/null; then
  echo "==> Installing node..."
  brew install node
fi

# Install Claude Code if missing
if ! command -v claude &>/dev/null; then
  echo "==> Installing Claude Code..."
  npm install -g @anthropic-ai/claude-code
fi

echo "==> Cloning / updating repo..."
REPO_DIR="$HOME/pranav"

if [ -d "$REPO_DIR/.git" ]; then
  cd "$REPO_DIR"
  git fetch origin
else
  git clone https://github.com/guptaprnv/pranav.git "$REPO_DIR"
  cd "$REPO_DIR"
fi

git checkout -B claude/setup-parallel-reading-ZH6hD origin/claude/setup-parallel-reading-ZH6hD

echo "==> Starting tmux sessions..."

# Kill old sessions if they exist
tmux kill-session -t reader 2>/dev/null || true
tmux kill-session -t coder  2>/dev/null || true

# Session 1: read/browse
tmux new-session -d -s reader -c "$REPO_DIR"
tmux send-keys -t reader "claude" Enter

# Session 2: coding
tmux new-session -d -s coder -c "$REPO_DIR"
tmux send-keys -t coder "claude" Enter

echo ""
echo "==> Done! Two Claude sessions are running:"
echo "    tmux attach -t reader   (browsing/reading)"
echo "    tmux attach -t coder    (coding)"
echo ""
echo "==> Attaching to 'coder' session now..."
sleep 1
tmux attach -t coder

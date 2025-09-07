#!/bin/bash

# === CONFIG ===
REMOTE_USER="root"
REMOTE_HOST="159.223.104.254"
REMOTE_DIR="/srv/br-portal"
TMUX_SESSION="br_portal"
START_CMD="cd clarity_dx_portal && source ../.venv/bin/activate && python manage.py runserver 0.0.0.0:5002"

# === STEP 1: Push local changes ===
echo "🚀 Pushing local changes to GitHub..."
git add .

# Prompt for commit message
echo "📝 Enter your commit message (or press Enter for default):"
read commit_message

# Use default message if none provided
if [ -z "$commit_message" ]; then
    commit_message="Auto-deploy at $(TZ='America/New_York' date '+%Y-%m-%d %H:%M:%S %Z')"
else
    # Add timestamp in EST to custom message
    commit_message="$commit_message - $(TZ='America/New_York' date '+%Y-%m-%d %H:%M:%S %Z')"
fi

git commit -m "$commit_message" || echo "📝 Nothing to commit"
CURRENT_BRANCH=$(git branch --show-current)
git push origin $CURRENT_BRANCH

# === STEP 2: SSH into VM, pull latest, restart app ===
echo "🔗 Connecting to $REMOTE_HOST and deploying..."

ssh $REMOTE_USER@$REMOTE_HOST << EOF
  echo "📁 Switching to project directory..."
  cd $REMOTE_DIR

  echo "📥 Pulling latest code from Git..."
  # Check if remote is HTTPS and switch to SSH if needed
  CURRENT_REMOTE=\$(git remote get-url origin)
  if [[ \$CURRENT_REMOTE == https://* ]]; then
    echo "🔧 Switching remote from HTTPS to SSH..."
    git remote set-url origin git@github.com:\$(echo \$CURRENT_REMOTE | sed 's|https://github.com/||' | sed 's|\.git||').git
  fi
  
  # Add GitHub to known hosts if not already present
  if ! grep -q "github.com" ~/.ssh/known_hosts 2>/dev/null; then
    echo "🔑 Adding GitHub to known hosts..."
    ssh-keyscan -H github.com >> ~/.ssh/known_hosts 2>/dev/null || true
  fi
  
  git reset --hard HEAD
  CURRENT_BRANCH=\$(git branch --show-current)
  if ! git pull origin \$CURRENT_BRANCH; then
    echo "⚠️  Git pull failed - continuing with existing code..."
    echo "💡 Tip: Set up SSH keys or configure Git credentials on the server"
  fi
  
  # Update dependencies with uv if requirements.txt changed
  echo "📦 Checking for dependency updates..."
  if command -v uv &> /dev/null; then
    echo "🔄 Updating dependencies with uv..."
    uv pip install -r requirements.txt
  else
    echo "⚠️  uv not found, skipping dependency update"
  fi

  echo "🔄 Restarting app in tmux session '$TMUX_SESSION'..."
  tmux kill-session -t $TMUX_SESSION 2>/dev/null || echo "🧼 No existing tmux session"
  tmux new-session -d -s $TMUX_SESSION "$START_CMD"
  echo "✅ App restarted and running in tmux."
EOF

echo "🌐 Done! Check your app at https://cdx-billreview.ngrok.io"

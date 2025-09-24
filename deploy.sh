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

# === STEP 2: Copy .env file to VM ===
echo "📄 Copying .env file to VM..."
if [ -f ".env" ]; then
    scp .env $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/.env
    echo "✅ .env file copied successfully"
else
    echo "⚠️  No .env file found locally - skipping copy"
fi

# === STEP 3: SSH into VM, pull latest, restart app ===
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
  
  # Configure git to handle divergent branches by merging
  git config pull.rebase false
  
  # Reset to clean state and pull latest changes
  git reset --hard HEAD
  CURRENT_BRANCH=\$(git branch --show-current)
  
  # Force pull to overwrite local changes with remote
  if ! git pull origin \$CURRENT_BRANCH --force; then
    echo "⚠️  Git pull failed - trying alternative approach..."
    # If pull fails, reset to remote branch
    git fetch origin \$CURRENT_BRANCH
    git reset --hard origin/\$CURRENT_BRANCH
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

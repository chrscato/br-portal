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

# === STEP 2: Copy configuration files to VM ===
echo "📄 Copying configuration files to VM..."

# Copy root .env file
if [ -f ".env" ]; then
    scp .env $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/.env
    echo "✅ Root .env file copied successfully"
else
    echo "⚠️  No root .env file found locally - skipping copy"
fi

# Copy Django project .env file
if [ -f "clarity_dx_portal/.env" ]; then
    scp clarity_dx_portal/.env $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/clarity_dx_portal/.env
    echo "✅ Django .env file copied successfully"
else
    echo "⚠️  No Django .env file found locally - skipping copy"
fi

# Copy critical shell scripts that might be needed
echo "📜 Copying critical shell scripts..."
if [ -f "startup.sh" ]; then
    scp startup.sh $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/startup.sh
    echo "✅ startup.sh copied successfully"
fi

if [ -f "manual_startup.sh" ]; then
    scp manual_startup.sh $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/manual_startup.sh
    echo "✅ manual_startup.sh copied successfully"
fi

if [ -f "startup_uv.sh" ]; then
    scp startup_uv.sh $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/startup_uv.sh
    echo "✅ startup_uv.sh copied successfully"
fi

# Copy any other critical config files
if [ -f "pyproject.toml" ]; then
    scp pyproject.toml $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/pyproject.toml
    echo "✅ pyproject.toml copied successfully"
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
  
  # Update dependencies
  echo "📦 Updating dependencies..."
  
  # Ensure uv is in PATH
  export PATH="\$HOME/.local/bin:\$PATH"
  
  # Check for virtual environment
  echo "🔍 Checking for virtual environment..."
  if [ -f ".venv/bin/activate" ]; then
    echo "🐍 Found .venv virtual environment, activating..."
    source .venv/bin/activate
    echo "✅ Virtual environment activated"
    python --version
  elif [ -d ".venv" ]; then
    echo "⚠️  .venv directory exists but activate script not found"
    ls -la .venv/bin/
  else
    echo "❌ No .venv virtual environment found"
    echo "📁 Creating virtual environment with uv..."
    if command -v uv &> /dev/null; then
      uv venv --python 3.11
      source .venv/bin/activate
      echo "✅ Virtual environment created and activated"
    else
      echo "❌ uv not available, cannot create virtual environment"
    fi
  fi
  
  if command -v uv &> /dev/null; then
    echo "🔄 Syncing dependencies with uv..."
    if ! uv sync; then
      echo "❌ uv sync failed, falling back to pip install in virtual environment"
      if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
        pip install --upgrade pip
        pip install -r requirements.txt
      else
        echo "❌ No virtual environment found, cannot install packages safely"
        echo "⚠️  Please run ./startup_uv.sh first to set up the environment"
      fi
    else
      echo "✅ uv sync completed successfully"
    fi
  else
    echo "⚠️  uv not found, falling back to pip install"
    if [ -f ".venv/bin/activate" ]; then
      source .venv/bin/activate
      pip install --upgrade pip
      pip install -r requirements.txt
    else
      echo "❌ No virtual environment found, cannot install packages safely"
      echo "⚠️  Please run ./startup_uv.sh first to set up the environment"
    fi
  fi

  echo "🔄 Restarting app in tmux session '$TMUX_SESSION'..."
  tmux kill-session -t $TMUX_SESSION 2>/dev/null || echo "🧼 No existing tmux session"
  tmux new-session -d -s $TMUX_SESSION "$START_CMD"
  echo "✅ App restarted and running in tmux."
EOF

echo "🌐 Done! Check your app at https://cdx-billreview.ngrok.io"

#!/bin/bash

# Enhanced startup script using uv for optimal Python environment setup
echo "🚀 Starting br-portal deployment with uv to production VM..."

# === CONFIG ===
REMOTE_USER="root"
REMOTE_HOST="159.223.104.254"
REMOTE_DIR="/srv/br-portal"
TMUX_SESSION="br_portal"

# === STEP 1: Create remote directory structure ===
echo "📁 Creating remote directory structure..."
ssh $REMOTE_USER@$REMOTE_HOST << EOF
  # Create main directory
  mkdir -p $REMOTE_DIR
  cd $REMOTE_DIR
  
  # Create subdirectories
  mkdir -p db_backups/local_backups
  mkdir -p db_backups/vm_backups
  mkdir -p logs
  
  echo "✅ Directory structure created"
EOF

# === STEP 2: Copy all project files to VM ===
echo "📤 Copying project files to VM..."
scp -r . $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/

# === STEP 3: Set up Python environment with uv ===
echo "🐍 Setting up Python environment on VM with uv..."
ssh $REMOTE_USER@$REMOTE_HOST << EOF
  cd $REMOTE_DIR
  
  # Install uv if not already installed
  if ! command -v uv &> /dev/null; then
    echo "📦 Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Add uv to PATH for this session
    export PATH="\$HOME/.local/bin:\$PATH"
    echo "✅ uv installed successfully"
  else
    echo "✅ uv already installed"
  fi
  
  # Ensure uv is in PATH
  export PATH="\$HOME/.local/bin:\$PATH"
  
  # Create virtual environment with uv (Python 3.11)
  echo "📦 Creating Python virtual environment with uv..."
  uv venv --python 3.11
  
  # Install dependencies using pyproject.toml if available, otherwise requirements.txt
  echo "📦 Installing Python dependencies with uv..."
  if [ -f "pyproject.toml" ]; then
    echo "📋 Using pyproject.toml for dependencies..."
    uv pip install -e .
  else
    echo "📋 Using requirements.txt for dependencies..."
    uv pip install -r requirements.txt
  fi
  
  # Set proper permissions on scripts
  chmod +x *.sh
  
  echo "✅ Python environment setup complete with uv"
EOF

# === STEP 4: Initialize git repository on VM ===
echo "🔧 Setting up git repository on VM..."
ssh $REMOTE_USER@$REMOTE_HOST << EOF
  cd $REMOTE_DIR
  
  # Initialize git if not already done
  if [ ! -d ".git" ]; then
    echo "🔧 Initializing git repository..."
    git init
    git remote add origin https://github.com/chrscato/br-portal.git
  fi
  
  # Add all files and make initial commit
  git add .
  git commit -m "Initial deployment setup with uv - $(date '+%Y-%m-%d %H:%M:%S')" || echo "📝 Nothing new to commit"
  
  echo "✅ Git repository setup complete"
EOF

# === STEP 5: Start the application ===
echo "🔄 Starting application..."
ssh $REMOTE_USER@$REMOTE_HOST << EOF
  cd $REMOTE_DIR
  
  # Kill any existing tmux session
  tmux kill-session -t $TMUX_SESSION 2>/dev/null || echo "🧼 No existing tmux session"
  
  # Start the application in tmux
  echo "🚀 Starting Django application..."
  tmux new-session -d -s $TMUX_SESSION "cd clarity_dx_portal && source ../.venv/bin/activate && python manage.py runserver 0.0.0.0:5002"
  
  # Wait a moment for the app to start
  sleep 3
  
  # Check if the app is running
  if tmux has-session -t $TMUX_SESSION 2>/dev/null; then
    echo "✅ Application started successfully in tmux session '$TMUX_SESSION'"
  else
    echo "❌ Failed to start application"
    exit 1
  fi
EOF

# === STEP 6: Verify deployment ===
echo "🔍 Verifying deployment..."
ssh $REMOTE_USER@$REMOTE_HOST << EOF
  cd $REMOTE_DIR
  
  # Check if tmux session is running
  if tmux has-session -t $TMUX_SESSION 2>/dev/null; then
    echo "✅ Tmux session '$TMUX_SESSION' is running"
    
    # Check if Django process is running
    if pgrep -f "manage.py runserver" > /dev/null; then
      echo "✅ Django application is running"
    else
      echo "⚠️  Django process not found, checking tmux logs..."
      tmux capture-pane -t $TMUX_SESSION -p
    fi
  else
    echo "❌ Tmux session not found"
  fi
  
  # Show Python environment info
  echo "🐍 Python environment info:"
  if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate && python --version && pip list | head -10
  else
    echo "⚠️  Virtual environment not found at .venv/"
    echo "📁 Checking for other virtual environments:"
    ls -la | grep -E "(venv|env|\.venv)"
  fi
  
  # Show directory structure
  echo "📁 Final directory structure:"
  ls -la
EOF

echo ""
echo "🎉 Deployment complete with uv!"
echo "🌐 Your application should be running at: https://cdx-billreview.ngrok.io"
echo "📋 To check logs: ssh $REMOTE_USER@$REMOTE_HOST 'tmux attach -t $TMUX_SESSION'"
echo "🔄 To restart: ssh $REMOTE_USER@$REMOTE_HOST 'cd $REMOTE_DIR && tmux kill-session -t $TMUX_SESSION && tmux new-session -d -s $TMUX_SESSION \"cd clarity_dx_portal && source ../.venv/bin/activate && python manage.py runserver 0.0.0.0:5002\"'"
echo ""
echo "💡 Next time, you can use ./deploy.sh for quick updates!"
echo "🚀 uv provides faster dependency resolution and installation!"

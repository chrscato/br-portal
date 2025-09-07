#!/bin/bash

# Quick fix script to set up the Python environment on the VM
echo "🔧 Fixing Python environment on VM..."

# === CONFIG ===
REMOTE_USER="root"
REMOTE_HOST="159.223.104.254"
REMOTE_DIR="/srv/br-portal"

# === Fix the environment ===
ssh $REMOTE_USER@$REMOTE_HOST << EOF
  cd $REMOTE_DIR
  
  echo "🔧 Adding uv to PATH..."
  export PATH="\$HOME/.local/bin:\$PATH"
  
  echo "📦 Creating virtual environment with uv..."
  uv venv --python 3.11
  
  echo "📦 Installing dependencies..."
  uv pip install -r requirements.txt
  
  echo "🔍 Verifying installation..."
  if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    echo "✅ Virtual environment created successfully"
    echo "🐍 Python version: \$(python --version)"
    echo "📦 Installed packages:"
    pip list
  else
    echo "❌ Virtual environment creation failed"
  fi
  
  echo "🚀 Starting Django application..."
  tmux kill-session -t br_portal 2>/dev/null || echo "🧼 No existing tmux session"
  tmux new-session -d -s br_portal "cd clarity_dx_portal && source ../.venv/bin/activate && python manage.py runserver 0.0.0.0:5002"
  
  sleep 3
  
  if tmux has-session -t br_portal 2>/dev/null; then
    echo "✅ Application started successfully"
  else
    echo "❌ Failed to start application"
    echo "📋 Checking tmux logs:"
    tmux capture-pane -t br_portal -p 2>/dev/null || echo "No tmux session found"
  fi
EOF

echo "🎉 VM environment fix complete!"

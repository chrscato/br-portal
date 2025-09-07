#!/bin/bash

# Setup script for production VM to prepare for br-portal deployment
echo "🚀 Setting up production VM for br-portal deployment..."

# === CONFIG ===
REMOTE_USER="root"
REMOTE_HOST="159.223.104.254"
REMOTE_DIR="/srv/br-portal"
GITHUB_REPO="https://github.com/chrscato/br-portal.git"

# === STEP 1: Create directory and clone repository ===
echo "📁 Creating directory and cloning repository..."
ssh $REMOTE_USER@$REMOTE_HOST << EOF
  # Create directory if it doesn't exist
  mkdir -p $REMOTE_DIR
  cd $REMOTE_DIR
  
  # Clone the repository if it doesn't exist
  if [ ! -d ".git" ]; then
    echo "📥 Cloning repository..."
    git clone $GITHUB_REPO .
  else
    echo "📁 Repository already exists, updating..."
    git pull origin main
  fi
  
  # Create virtual environment if it doesn't exist
  if [ ! -d "venv" ]; then
    echo "🐍 Creating Python virtual environment..."
    python3 -m venv venv
  fi
  
  # Activate virtual environment and install requirements
  echo "📦 Installing Python dependencies..."
  source venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
  
  # Create necessary directories
  echo "📁 Creating necessary directories..."
  mkdir -p db_backups/local_backups
  mkdir -p db_backups/vm_backups
  
  # Set proper permissions
  chmod +x *.sh
  
  echo "✅ VM setup complete!"
EOF

echo "🌐 Production VM is ready for deployment!"
echo "💡 You can now use ./deploy.sh to deploy your application"

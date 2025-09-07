#!/bin/bash

# Quick fix for Django installation on VM
echo "🔧 Fixing Django installation on VM..."

# === CONFIG ===
REMOTE_USER="root"
REMOTE_HOST="159.223.104.254"
REMOTE_DIR="/srv/br-portal"

ssh $REMOTE_USER@$REMOTE_HOST << 'EOF'
    cd /srv/br-portal
    
    echo "🔍 Checking current environment..."
    echo "Current directory: $(pwd)"
    echo "Python version: $(python --version)"
    echo "Virtual environment: $VIRTUAL_ENV"
    
    # Add uv to PATH
    export PATH=$HOME/.local/bin:$PATH
    
    echo "📦 Installing dependencies with uv..."
    uv pip install -r requirements.txt
    
    echo "🔍 Verifying Django installation..."
    source .venv/bin/activate
    python -c "import django; print('Django version:', django.get_version())" || echo "❌ Django not found"
    
    echo "📋 Installed packages:"
    pip list | grep -E "(Django|pandas|boto3|python-dotenv)"
    
    echo "🚀 Starting Django application..."
    cd clarity_dx_portal
    python manage.py runserver 0.0.0.0:5002
EOF

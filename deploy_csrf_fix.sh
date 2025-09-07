#!/bin/bash

# Quick deployment script to fix CSRF issue
echo "🔧 Deploying CSRF fix to VM..."

# === CONFIG ===
REMOTE_USER="root"
REMOTE_HOST="159.223.104.254"
REMOTE_DIR="/srv/br-portal"

# Push the updated settings file
echo "📤 Uploading updated Django settings..."
scp clarity_dx_portal/clarity_dx_portal/settings.py $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/clarity_dx_portal/clarity_dx_portal/settings.py

# Restart Django application
echo "🔄 Restarting Django application..."
ssh $REMOTE_USER@$REMOTE_HOST << EOF
    cd $REMOTE_DIR
    
    # Kill existing tmux session
    tmux kill-session -t br_portal 2>/dev/null || echo "🧼 No existing session"
    
    # Start new session
    tmux new-session -d -s br_portal
    tmux send-keys -t br_portal 'cd clarity_dx_portal' Enter
    tmux send-keys -t br_portal 'source ../.venv/bin/activate' Enter
    tmux send-keys -t br_portal 'python manage.py runserver 0.0.0.0:5002' Enter
    
    sleep 3
    
    if tmux has-session -t br_portal 2>/dev/null; then
        echo "✅ Django restarted successfully"
    else
        echo "❌ Failed to restart Django"
    fi
EOF

echo "🎉 CSRF fix deployed!"
echo "🌐 Test your app at: https://cdx-billreview.ngrok.io"
echo "📋 Check logs: ssh $REMOTE_USER@$REMOTE_HOST 'tmux attach -t br_portal'"

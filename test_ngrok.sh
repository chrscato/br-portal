#!/bin/bash

# Test script to verify ngrok connection with the Django app
echo "🧪 Testing ngrok connection with Django app..."

# === CONFIG ===
REMOTE_USER="root"
REMOTE_HOST="159.223.104.254"
REMOTE_DIR="/srv/br-portal"
NGROK_URL="https://cdx-billreview.ngrok.io"

echo "🔍 Testing connection to: $NGROK_URL"

# Test if the ngrok URL is accessible
echo "📡 Testing ngrok URL accessibility..."
if curl -s --head "$NGROK_URL" | head -n 1 | grep -q "200 OK"; then
    echo "✅ ngrok URL is accessible"
else
    echo "❌ ngrok URL is not accessible"
    echo "💡 Make sure ngrok is running on your local machine"
    echo "💡 Check that ngrok is forwarding to localhost:5002"
fi

# Test Django app on the VM
echo "🔍 Testing Django app on VM..."
ssh $REMOTE_USER@$REMOTE_HOST << EOF
    cd $REMOTE_DIR
    
    # Check if Django is running
    if pgrep -f "manage.py runserver" > /dev/null; then
        echo "✅ Django process is running"
        
        # Check if it's listening on port 5002
        if netstat -tlnp | grep -q ":5002"; then
            echo "✅ Django is listening on port 5002"
        else
            echo "❌ Django is not listening on port 5002"
        fi
    else
        echo "❌ Django process is not running"
        echo "💡 Start Django with: cd clarity_dx_portal && source ../.venv/bin/activate && python manage.py runserver 0.0.0.0:5002"
    fi
    
    # Check tmux session
    if tmux has-session -t br_portal 2>/dev/null; then
        echo "✅ tmux session 'br_portal' is running"
    else
        echo "❌ tmux session 'br_portal' is not running"
    fi
EOF

echo ""
echo "🌐 Your app should be accessible at: $NGROK_URL"
echo "📋 To check Django logs: ssh $REMOTE_USER@$REMOTE_HOST 'tmux attach -t br_portal'"
echo "🔄 To restart Django: ssh $REMOTE_USER@$REMOTE_HOST 'cd $REMOTE_DIR && tmux kill-session -t br_portal && tmux new-session -d -s br_portal \"cd clarity_dx_portal && source ../.venv/bin/activate && python manage.py runserver 0.0.0.0:5002\"'"

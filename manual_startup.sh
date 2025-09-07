#!/bin/bash

# Manual startup script for br-portal on VM
echo "🔧 Manual startup script for br-portal..."

# === CONFIG ===
REMOTE_USER="root"
REMOTE_HOST="159.223.104.254"
REMOTE_DIR="/srv/br-portal"

echo "📋 Step-by-step manual setup:"
echo ""
echo "1. First, create the .env file on the VM:"
echo "   ssh $REMOTE_USER@$REMOTE_HOST"
echo "   cd $REMOTE_DIR"
echo "   nano .env"
echo ""
echo "2. Add this content to the .env file:"
echo "   AWS_ACCESS_KEY_ID=your_aws_access_key_here"
echo "   AWS_SECRET_ACCESS_KEY=your_aws_secret_key_here"
echo "   AWS_STORAGE_BUCKET_NAME=your_bucket_name_here"
echo "   AWS_S3_REGION_NAME=us-east-1"
echo "   DEBUG=True"
echo "   SECRET_KEY=django-insecure-bziordhq02fvz89ch4y2+lvqwy#2#p5m7z8y_@@n@g5eer)h=1"
echo "   ALLOWED_HOSTS=localhost,127.0.0.1,159.223.104.254,cdx-billreview.ngrok.io"
echo ""
echo "3. Set up the Python environment:"
echo "   export PATH=\$HOME/.local/bin:\$PATH"
echo "   uv venv --python 3.11"
echo "   uv pip install -r requirements.txt"
echo ""
echo "4. Start the Django application:"
echo "   tmux new-session -d -s br_portal"
echo "   tmux send-keys -t br_portal 'cd clarity_dx_portal' Enter"
echo "   tmux send-keys -t br_portal 'source ../.venv/bin/activate' Enter"
echo "   tmux send-keys -t br_portal 'python manage.py runserver 0.0.0.0:5002' Enter"
echo ""
echo "5. Check if it's running:"
echo "   tmux attach -t br_portal"
echo ""
echo "Or run this automated version:"
echo ""

# Automated version
read -p "🤖 Run automated setup? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🚀 Running automated setup..."
    
    ssh $REMOTE_USER@$REMOTE_HOST << 'EOF'
        cd /srv/br-portal
        
        # Create .env file if it doesn't exist
        if [ ! -f ".env" ]; then
            echo "📝 Creating .env file..."
            cat > .env << 'ENVEOF'
AWS_ACCESS_KEY_ID=your_aws_access_key_here
AWS_SECRET_ACCESS_KEY=your_aws_secret_key_here
AWS_STORAGE_BUCKET_NAME=your_bucket_name_here
AWS_S3_REGION_NAME=us-east-1
DEBUG=True
SECRET_KEY=django-insecure-bziordhq02fvz89ch4y2+lvqwy#2#p5m7z8y_@@n@g5eer)h=1
ALLOWED_HOSTS=localhost,127.0.0.1,159.223.104.254,cdx-billreview.ngrok.io
ENVEOF
            echo "✅ .env file created (you'll need to update the AWS credentials)"
        else
            echo "✅ .env file already exists"
        fi
        
        # Set up Python environment
        echo "🐍 Setting up Python environment..."
        export PATH=$HOME/.local/bin:$PATH
        
        if [ ! -d ".venv" ]; then
            echo "📦 Creating virtual environment..."
            uv venv --python 3.11
        else
            echo "✅ Virtual environment already exists"
        fi
        
        echo "📦 Installing dependencies..."
        uv pip install -r requirements.txt
        
        # Start the application
        echo "🚀 Starting Django application..."
        tmux kill-session -t br_portal 2>/dev/null || echo "🧼 No existing session"
        
        # Create new tmux session and start Django
        tmux new-session -d -s br_portal
        tmux send-keys -t br_portal 'cd clarity_dx_portal' Enter
        tmux send-keys -t br_portal 'source ../.venv/bin/activate' Enter
        tmux send-keys -t br_portal 'python manage.py runserver 0.0.0.0:5002' Enter
        
        sleep 3
        
        # Check if it's running
        if tmux has-session -t br_portal 2>/dev/null; then
            echo "✅ Application started successfully!"
            echo "📋 To check logs: tmux attach -t br_portal"
        else
            echo "❌ Failed to start application"
        fi
EOF
    
    echo ""
    echo "🎉 Setup complete!"
    echo "📋 To check the application: ssh $REMOTE_USER@$REMOTE_HOST 'tmux attach -t br_portal'"
    echo "🌐 Your app should be running at: https://cdx-billreview.ngrok.io"
    echo ""
    echo "⚠️  Don't forget to update the AWS credentials in the .env file!"
fi

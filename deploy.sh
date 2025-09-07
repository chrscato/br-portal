#!/bin/bash

# === CONFIG ===
REMOTE_USER="root"
REMOTE_HOST="root@ubuntu-s-1vcpu-512mb-10gb-nyc1-01:/# # Check the biggest directories again
du -h --max-depth=2 | sort -rh | head -20

# Check what's in the largest directories
du -sh /root/*
du -sh /usr/*
du -sh /var/*
du -sh /opt/*
du: cannot access './proc/2361140/task/2361141/fd/33': No such file or directory
du: cannot access './proc/2361140/task/2361141/fd/35': No such file or directory
du: cannot access './proc/2361140/task/2361141/fd/36': No such file or directory
du: cannot access './proc/2368390/task/2368390/fd/4': No such file or directory
du: cannot access './proc/2368390/task/2368390/fdinfo/4': No such file or directory
du: cannot access './proc/2368390/fd/3': No such file or directory
du: cannot access './proc/2368390/fdinfo/3': No such file or directory
du: cannot access './proc/2368660': No such file or directory
38G     .
22G     ./root/.pm2
22G     ./root
5.7G    ./usr
5.1G    ./var
3.5G    ./var/lib
3.3G    ./usr/lib
2.6G    ./opt
2.2G    ./opt/bph_lookup
1.5G    ./var/log
1.1G    ./usr/share
1.1G    ./srv
849M    ./snap
609M    ./usr/bin
556M    ./srv/bill_review
496M    ./snap/core22
408M    ./opt/bill_review
318M    ./usr/src
308M    ./root/.cache
306M    ./snap/snapd
94M     /root/net_dev_portal
4.0K    /root/setup_vm.sh
44K     /root/snap
47M     /root/venv
609M    /usr/bin
4.0K    /usr/games
61M     /usr/include
3.3G    /usr/lib
4.0K    /usr/lib64
143M    /usr/libexec
249M    /usr/local
49M     /usr/sbin
1.1G    /usr/share
318M    /usr/src
3.4M    /var/backups
112M    /var/cache
4.0K    /var/crash
3.5G    /var/lib
4.0K    /var/local
0       /var/lock
1.5G    /var/log
4.0K    /var/mail
4.0K    /var/opt
0       /var/run
52K     /var/snap
32K     /var/spool
56K     /var/tmp
12K     /var/www
408M    /opt/bill_review
2.2G    /opt/bph_lookup
12K     /opt/containerd
7.4M    /opt/digitalocean
1.5M    /opt/intake-crm
root@ubuntu-s-1vcpu-512mb-10gb-nyc1-01:/#"
REMOTE_DIR="/srv/monolith"
TMUX_SESSION="bill_review"
START_CMD="source venv/bin/activate && python billing/webapp/manage.py runserver 0.0.0.0:5002"

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
git push origin master

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
  if ! git pull origin master; then
    echo "⚠️  Git pull failed - continuing with existing code..."
    echo "💡 Tip: Set up SSH keys or configure Git credentials on the server"
  fi

  echo "🔄 Restarting app in tmux session '$TMUX_SESSION'..."
  tmux kill-session -t $TMUX_SESSION 2>/dev/null || echo "🧼 No existing tmux session"
  tmux new-session -d -s $TMUX_SESSION "$START_CMD"
  echo "✅ App restarted and running in tmux."
EOF

echo "🌐 Done! Check your app at https://cdx-billreview.ngrok.io"

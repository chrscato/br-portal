#!/bin/bash

# Simple script to upload users.db to production
echo "Uploading users.db to production..."

# Configuration
REMOTE_USER="root"
REMOTE_HOST="159.223.104.254"
REMOTE_DIR="/srv/br-portal"
LOCAL_USERS_DB="./clarity_dx_portal/users.db"

# Check if local users.db exists
if [ ! -f "$LOCAL_USERS_DB" ]; then
    echo "❌ Error: $LOCAL_USERS_DB not found!"
    echo "Make sure you're in the project root directory."
    exit 1
fi

# Create backup of current production users.db first
echo "📦 Creating backup of current production users.db..."
timestamp=$(date +"%Y%m%d_%H%M%S")
backup_path="./db_backups/prod_users_backup_${timestamp}.db"

# Create backup directory if it doesn't exist
mkdir -p ./db_backups

# Download current production users.db as backup
scp "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/clarity_dx_portal/users.db" "$backup_path"

if [ $? -eq 0 ]; then
    echo "✅ Production backup created: $backup_path"
else
    echo "⚠️  Warning: Could not create production backup, but continuing..."
fi

# Upload local users.db to production
echo "📤 Uploading users.db to production..."
scp "$LOCAL_USERS_DB" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/clarity_dx_portal/users.db"

if [ $? -eq 0 ]; then
    echo "✅ Successfully uploaded users.db to production!"
    echo "🔄 You may want to restart the Django application on production."
else
    echo "❌ Failed to upload users.db to production"
    exit 1
fi

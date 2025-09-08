#!/bin/bash

# Production User Management Script for BR Portal
# This script downloads users.db from production, allows you to add a new user,
# and uploads the updated database back to production.

set -e  # Exit on any error

# === CONFIG ===
REMOTE_USER="root"
REMOTE_HOST="159.223.104.254"
REMOTE_DIR="/srv/br-portal"
LOCAL_USERS_DB="./clarity_dx_portal/users.db"
BACKUP_DIR="./db_backups/user_backups"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to create backup directory
create_backup_dir() {
    if [ ! -d "$BACKUP_DIR" ]; then
        mkdir -p "$BACKUP_DIR"
        print_status "Created backup directory: $BACKUP_DIR"
    fi
}

# Function to create timestamped backup
create_backup() {
    local file_path="$1"
    local backup_type="$2"
    
    if [ -f "$file_path" ]; then
        timestamp=$(date +"%Y%m%d_%H%M%S")
        backup_filename="${backup_type}_backup_${timestamp}.db"
        backup_path="$BACKUP_DIR/$backup_filename"
        
        cp "$file_path" "$backup_path"
        print_success "Created backup: $backup_path"
        return 0
    else
        print_warning "No existing $backup_type database found, skipping backup"
        return 1
    fi
}

# Function to download users.db from production
download_users_db() {
    print_status "Downloading users.db from production..."
    
    # Create backup of local users.db if it exists
    create_backup "$LOCAL_USERS_DB" "local_users"
    
    # Download from production
    scp "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/clarity_dx_portal/users.db" "$LOCAL_USERS_DB"
    
    if [ $? -eq 0 ]; then
        print_success "Successfully downloaded users.db from production"
    else
        print_error "Failed to download users.db from production"
        exit 1
    fi
}

# Function to create a new user
create_new_user() {
    print_status "Creating new user..."
    
    # Check if users.db exists
    if [ ! -f "$LOCAL_USERS_DB" ]; then
        print_error "users.db not found. Please download it first."
        exit 1
    fi
    
    # Get user details
    echo ""
    echo "=== New User Creation ==="
    read -p "Enter username: " username
    read -p "Enter email: " email
    read -s -p "Enter password: " password
    echo ""
    read -p "Enter first name: " first_name
    read -p "Enter last name: " last_name
    
    # Validate inputs
    if [ -z "$username" ] || [ -z "$email" ] || [ -z "$password" ]; then
        print_error "Username, email, and password are required"
        exit 1
    fi
    
    # Create backup before making changes
    create_backup "$LOCAL_USERS_DB" "users_before_new_user"
    
    # Use Django management command to create user
    print_status "Creating user '$username'..."
    
    cd clarity_dx_portal
    
    # Create the user using Django's createsuperuser command (non-interactive)
    python manage.py shell << EOF
from django.contrib.auth.models import User
import sys

try:
    # Check if user already exists
    if User.objects.filter(username='$username').exists():
        print(f"User '$username' already exists!")
        sys.exit(1)
    
    if User.objects.filter(email='$email').exists():
        print(f"User with email '$email' already exists!")
        sys.exit(1)
    
    # Create the user
    user = User.objects.create_user(
        username='$username',
        email='$email',
        password='$password',
        first_name='$first_name',
        last_name='$last_name',
        is_staff=True,  # Allow access to admin
        is_active=True
    )
    
    print(f"Successfully created user: {user.username} ({user.email})")
    
except Exception as e:
    print(f"Error creating user: {e}")
    sys.exit(1)
EOF

    if [ $? -eq 0 ]; then
        print_success "User '$username' created successfully"
        cd ..
    else
        print_error "Failed to create user"
        cd ..
        exit 1
    fi
}

# Function to list existing users
list_users() {
    print_status "Listing existing users..."
    
    if [ ! -f "$LOCAL_USERS_DB" ]; then
        print_error "users.db not found. Please download it first."
        exit 1
    fi
    
    cd clarity_dx_portal
    
    python manage.py shell << EOF
from django.contrib.auth.models import User

print("\n=== Existing Users ===")
users = User.objects.all().order_by('username')
for user in users:
    status = "Active" if user.is_active else "Inactive"
    staff = "Staff" if user.is_staff else "Regular"
    superuser = "Superuser" if user.is_superuser else ""
    print(f"Username: {user.username:<20} | Email: {user.email:<30} | Status: {status} | {staff} {superuser}")

print(f"\nTotal users: {users.count()}")
EOF

    cd ..
}

# Function to upload users.db back to production
upload_users_db() {
    print_status "Uploading updated users.db to production..."
    
    # Create backup of current production users.db
    print_status "Creating backup of current production users.db..."
    timestamp=$(date +"%Y%m%d_%H%M%S")
    prod_backup_path="$BACKUP_DIR/prod_users_backup_${timestamp}.db"
    
    scp "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/clarity_dx_portal/users.db" "$prod_backup_path"
    
    if [ $? -eq 0 ]; then
        print_success "Production backup created: $prod_backup_path"
    else
        print_warning "Failed to create production backup, but continuing with upload..."
    fi
    
    # Check if local users.db exists
    if [ ! -f "$LOCAL_USERS_DB" ]; then
        print_error "Local users.db not found, cannot upload"
        exit 1
    fi
    
    # Upload to production
    scp "$LOCAL_USERS_DB" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/clarity_dx_portal/users.db"
    
    if [ $? -eq 0 ]; then
        print_success "Successfully uploaded users.db to production"
    else
        print_error "Failed to upload users.db to production"
        exit 1
    fi
}

# Function to restart Django application on production
restart_django() {
    print_status "Restarting Django application on production..."
    
    ssh "$REMOTE_USER@$REMOTE_HOST" << EOF
        cd $REMOTE_DIR
        
        # Kill existing tmux session
        tmux kill-session -t br_portal 2>/dev/null || echo "No existing session to kill"
        
        # Start Django in tmux
        tmux new-session -d -s br_portal "cd clarity_dx_portal && source ../.venv/bin/activate && python manage.py runserver 0.0.0.0:5002"
        
        # Wait a moment
        sleep 3
        
        # Check if it's running
        if tmux has-session -t br_portal 2>/dev/null; then
            echo "✅ Django application restarted successfully"
        else
            echo "❌ Failed to restart Django application"
            exit 1
        fi
EOF

    if [ $? -eq 0 ]; then
        print_success "Django application restarted successfully"
    else
        print_error "Failed to restart Django application"
        exit 1
    fi
}

# Function to show help
show_help() {
    echo "Production User Management Script for BR Portal"
    echo ""
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  download     Download users.db from production"
    echo "  create       Create a new user (interactive)"
    echo "  list         List all existing users"
    echo "  upload       Upload users.db to production"
    echo "  restart      Restart Django application on production"
    echo "  full         Complete workflow: download -> create -> upload -> restart"
    echo "  help         Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 full                    # Complete workflow"
    echo "  $0 download                # Just download the database"
    echo "  $0 create                  # Just create a user (requires local users.db)"
    echo "  $0 list                    # List existing users"
    echo ""
    echo "Backups are automatically created in: $BACKUP_DIR"
}

# Main script logic
main() {
    create_backup_dir
    
    case "${1:-help}" in
        "download")
            download_users_db
            ;;
        "create")
            create_new_user
            ;;
        "list")
            list_users
            ;;
        "upload")
            upload_users_db
            ;;
        "restart")
            restart_django
            ;;
        "full")
            print_status "Starting complete user management workflow..."
            download_users_db
            create_new_user
            upload_users_db
            restart_django
            print_success "Complete workflow finished successfully!"
            ;;
        "help"|*)
            show_help
            ;;
    esac
}

# Run main function with all arguments
main "$@"


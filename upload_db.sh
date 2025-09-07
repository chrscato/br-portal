#!/bin/bash

# Script to upload the monolith database to the remote server
echo "Uploading monolith.db to remote server..."

# First, create a backup of the current VM database before overwriting it
echo "Creating backup of current VM database..."
timestamp=$(date +"%Y%m%d_%H%M%S")
backup_path="./db_backups/vm_backups/monolith_vm_backup_${timestamp}.db"

# Download current VM database as backup
scp root@159.223.104.254:/srv/br-portal/monolith.db "${backup_path}"

if [ $? -eq 0 ]; then
    echo "VM backup created successfully: ${backup_path}"
else
    echo "Failed to create VM backup, but continuing with upload..."
fi

# Check if local database exists before uploading
if [ ! -f "./monolith.db" ]; then
    echo "No local monolith.db found, cannot upload"
    exit 1
fi

# Upload the local database to remote server
echo "Uploading local monolith.db to VM..."
scp ./monolith.db root@159.223.104.254:/srv/br-portal/monolith.db

if [ $? -eq 0 ]; then
    echo "Successfully uploaded monolith.db"
else
    echo "Failed to upload monolith.db"
    exit 1
fi 
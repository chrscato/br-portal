#!/bin/bash

# Script to fetch the monolith database from the remote server
echo "Fetching monolith.db from remote server..."

# Create a dated backup of the current local database (if it exists)
if [ -f "./monolith.db" ]; then
    timestamp=$(date +"%Y%m%d_%H%M%S")
    backup_path="./db_backups/local_backups/monolith_backup_${timestamp}.db"
    echo "Creating local backup: ${backup_path}"
    cp ./monolith.db "${backup_path}"
    echo "Local backup created successfully"
else
    echo "No existing local monolith.db found, skipping backup"
fi

# Download the database from remote server
# Use a temporary filename to avoid issues with locked files
scp root@159.223.104.254:/srv/br-portal/monolith.db ./monolith_new.db

if [ $? -eq 0 ]; then
    # Remove old database and rename new one
    rm -f ./monolith.db
    mv ./monolith_new.db ./monolith.db
    echo "Successfully downloaded and replaced monolith.db"
else
    echo "Failed to download monolith.db"
    exit 1
fi 
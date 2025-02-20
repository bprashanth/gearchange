#!/bin/bash

set -e  # Exit immediately if a command exits with a non-zero status

usage() {
    echo "Usage: $0 --src_dir <source_directory> --dst_dir <destination_directory> --log_dir <log_directory>"
    exit 1
}

# Parse command-line arguments
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --src_dir)
            SRC_DIR="$2"
            shift 2
            ;;
        --dst_dir)
            DST_DIR="$2"
            shift 2
            ;;
        --log_dir)
            LOG_DIR="$2"
            shift 2
            ;;
        *)
            usage
            ;;
    esac
done

# Ensure required arguments are provided
if [[ -z "$SRC_DIR" || -z "$DST_DIR" || -z "$LOG_DIR" ]]; then
    usage
fi

# Fail if the dst dir already exists 
if [[ -d "$DST_DIR" ]]; then
    echo "Error: Destination directory $DST_DIR already exists. Aborting."
    exit 1
fi

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/mongo_repair.log"

# Copy the MongoDB data directory
echo "Copying data from $SRC_DIR to $DST_DIR..."
rsync -a "$SRC_DIR" "$DST_DIR"

# Remove lock file if it exists
LOCK_FILE="$DST_DIR/mongod.lock"
if [[ -f "$LOCK_FILE" ]]; then
    echo "Removing lock file: $LOCK_FILE"
    sudo rm "$LOCK_FILE"
fi

# Run MongoDB repair
echo "Running MongoDB repair on $DST_DIR..."
sudo mongod --dbpath "$DST_DIR" --repair &>> "$LOG_FILE"

# Set correct ownership and permissions
echo "Setting permissions for $DST_DIR..."
sudo chown -R mongodb:mongodb "$DST_DIR"
sudo chmod -R 755 "$DST_DIR"

# Start MongoDB
echo "Starting MongoDB on $DST_DIR..."
echo "Logs are being written to: $LOG_FILE"
echo "To access MongoDB, run: mongosh --host 127.0.0.1 --port 27017"

sudo mongod --dbpath "$DST_DIR" --bind_ip 0.0.0.0 --port 27017 &>> "$LOG_FILE"


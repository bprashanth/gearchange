#!/bin/bash
# Usage: 
#   docker-entrypoint.sh mongod --config /etc/mongo/mongod.conf  --dbpath /data/db/test

set -e

# Function to extract the --config value from the command arguments
get_config_path() {
  for arg in "$@"; do
    if [[ $arg == "--config" ]]; then
      echo "$2"
      return
    fi
    shift
  done
}

# Function to extract the --dbpath value from the command arguments
get_dbpath() {
  for arg in "$@"; do
    if [[ $arg == "--dbpath" ]]; then
      echo "$2"
      return
    fi
    shift
  done
}

# Define the config file path from --config
CONFIG_PATH=$(get_config_path "$@")
DEFAULT_CONFIG_PATH="/etc/mongo/mongod_default.conf"

if [ -z "$CONFIG_PATH" ]; then
  echo "Warning: --config argument not set. Falling back to default configuration path: $DEFAULT_CONFIG_PATH"
  CONFIG_PATH="$DEFAULT_CONFIG_PATH"
 
  # Append --config $DEFAULT_CONFIG_PATH to the list of command arguments
  set -- "$@" --config "$DEFAULT_CONFIG_PATH"
fi

# Define the data directory path from --dbpath
MONGO_DATA_DIR=$(get_dbpath "$@")

if [ -z "$MONGO_DATA_DIR" ]; then
  echo "Error: --dbpath argument is required."
  exit 1
fi

# Log file path (optional: read from config as well if configurable)
MONGO_LOG_DIR="/var/log/mongodb"

echo "Detected MongoDB data path: $MONGO_DATA_DIR"
mkdir -p "$MONGO_DATA_DIR"

echo "Detected MongoDB log path: $MONGO_LOG_DIR"
mkdir -p "$MONGO_LOG_DIR"

echo "Setting ownership for $MONGO_DATA_DIR"
chown -R mongodb:mongodb "$MONGO_DATA_DIR"

echo "Setting ownership for $MONGO_LOG_DIR"
chown -R mongodb:mongodb "$MONGO_LOG_DIR"

# Run the original MongoDB entrypoint (or the command passed)
exec "$@"


#!/bin/bash

# Script to run Python scripts based on config in bootfs
# Save this as /usr/local/bin/bootconfig_runner.sh

# Log startup
echo "Bootconfig runner started at $(date)" > /var/log/bootconfig.log

# Possible config locations
CONFIG_FILES=(
  "/boot/firmware/autorun.conf"
  "/boot/firmware/autorun.conf.txt"
  "/boot/autorun.conf"           
  "/boot/autorun.conf.txt"       
  "/media/pi/bootfs/autorun.conf" 
  "/media/pi/bootfs/autorun.conf.txt"
)

# Function to find the config file
find_config() {
  for config in "${CONFIG_FILES[@]}"; do
    if [ -f "$config" ]; then
      echo "$config"
      return 0
    fi
  done
  return 1
}

# Try to find the config
CONFIG_FILE=$(find_config)
if [ -z "$CONFIG_FILE" ]; then
  echo "No config file found in any of the expected locations" >> /var/log/bootconfig.log
  exit 1
fi

echo "Found config file at $CONFIG_FILE" >> /var/log/bootconfig.log

# Source the config file to get variables
source "$CONFIG_FILE"

# Log config details
echo "Config loaded with SCRIPT_PATH=$SCRIPT_PATH" >> /var/log/bootconfig.log

# Set default Python command if not specified
PYTHON_CMD=${PYTHON_CMD:-python3}
echo "Using Python command: $PYTHON_CMD" >> /var/log/bootconfig.log

# Check if script path is defined and file exists
if [ -z "$SCRIPT_PATH" ]; then
  echo "SCRIPT_PATH not defined in config file" >> /var/log/bootconfig.log
  exit 1
fi

if [ ! -f "$SCRIPT_PATH" ]; then
  echo "Python script not found: $SCRIPT_PATH" >> /var/log/bootconfig.log
  exit 1
fi

# Get the directory of the script
SCRIPT_DIR=$(dirname "$SCRIPT_PATH")
SCRIPT_NAME=$(basename "$SCRIPT_PATH")

# Build parameters string from config file
PARAMS=""
while IFS= read -r line || [[ -n "$line" ]]; do
  # Skip comments, empty lines, SCRIPT_PATH and PYTHON_CMD
  [[ "$line" =~ ^#.*$ || -z "$line" || "$line" =~ ^SCRIPT_PATH=.* || "$line" =~ ^PYTHON_CMD=.* ]] && continue
  
  # Extract key and value
  if [[ "$line" =~ ^([A-Za-z0-9_\-]+)=(.*)$ ]]; then
    KEY="${BASH_REMATCH[1]}"
    VALUE="${BASH_REMATCH[2]}"
    PARAMS="$PARAMS --$KEY $VALUE"
  fi
done < "$CONFIG_FILE"

echo "Constructed parameters: $PARAMS" >> /var/log/bootconfig.log

# Wait for all services to be ready
echo "Waiting 10 seconds before starting script..." >> /var/log/bootconfig.log
sleep 10

# Change to script directory and run
echo "Changing to directory $SCRIPT_DIR" >> /var/log/bootconfig.log
cd "$SCRIPT_DIR"

# Run the script with sudo
echo "Running command: sudo $PYTHON_CMD $SCRIPT_NAME $PARAMS" >> /var/log/bootconfig.log
sudo $PYTHON_CMD "$SCRIPT_NAME" $PARAMS >> /var/log/bootconfig.log 2>&1

echo "Script exited at $(date)" >> /var/log/bootconfig.log

# Keep the service running
while true; do
  echo "Script is not running, restarting in 30 seconds..." >> /var/log/bootconfig.log
  sleep 30
  echo "Rerunning command: sudo $PYTHON_CMD $SCRIPT_NAME $PARAMS" >> /var/log/bootconfig.log
  sudo $PYTHON_CMD "$SCRIPT_NAME" $PARAMS >> /var/log/bootconfig.log 2>&1
done
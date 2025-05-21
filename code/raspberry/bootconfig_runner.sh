#!/bin/bash
# ===================================================================
# Raspberry Pi Auto-run Configuration Runner Script
# Purpose: Automatically runs Python scripts with parameters defined
# in a configuration file located in the boot partition
# Location: /usr/local/bin/bootconfig_runner.sh
# ===================================================================

# Log startup - Creates/overwrites log file with startup timestamp
echo "Bootconfig runner started at $(date)" > /var/log/bootconfig.log

# Possible config locations - Searches multiple locations to be compatible
# with different Raspberry Pi OS versions and mounting schemes
CONFIG_FILES=(
  "/boot/firmware/autorun.conf"       # Pi OS Bullseye and newer
  "/boot/firmware/autorun.conf.txt"   # Alternative extension (for FAT32 compatibility)
  "/boot/autorun.conf"                # Pi OS Buster and older
  "/boot/autorun.conf.txt"            # Alternative extension
  "/media/pi/bootfs/autorun.conf"     # Alternative mount location
  "/media/pi/bootfs/autorun.conf.txt" # Alternative extension
)

# Function to find the config file - Checks each possible location
# Returns the path of the first config file found or empty if none found
find_config() {
  for config in "${CONFIG_FILES[@]}"; do
    if [ -f "$config" ]; then
      echo "$config" # Return the path to the found config file
      return 0       # Success exit code
    fi
  done
  return 1           # Failure exit code - no config found
}

# Try to find the config by calling the function
CONFIG_FILE=$(find_config)
if [ -z "$CONFIG_FILE" ]; then
  # Exit if no config file is found in any location
  echo "No config file found in any of the expected locations" >> /var/log/bootconfig.log
  exit 1
fi

# Log the found config file location
echo "Found config file at $CONFIG_FILE" >> /var/log/bootconfig.log

# Source the config file to get variables directly into the environment
# This loads SCRIPT_PATH and other variables from the config file
source "$CONFIG_FILE"

# Log the loaded script path for debugging
echo "Config loaded with SCRIPT_PATH=$SCRIPT_PATH" >> /var/log/bootconfig.log

# Set default Python command if not specified in the config file
# Allows for custom Python environments or versions to be used
PYTHON_CMD=${PYTHON_CMD:-python3}
echo "Using Python command: $PYTHON_CMD" >> /var/log/bootconfig.log

# Check if script path is defined and file exists
# Exit with error if the path is missing or incorrect
if [ -z "$SCRIPT_PATH" ]; then
  echo "SCRIPT_PATH not defined in config file" >> /var/log/bootconfig.log
  exit 1
fi

if [ ! -f "$SCRIPT_PATH" ]; then
  echo "Python script not found: $SCRIPT_PATH" >> /var/log/bootconfig.log
  exit 1
fi

# Get the directory and filename of the script for easier handling
SCRIPT_DIR=$(dirname "$SCRIPT_PATH")    # Directory containing the script
SCRIPT_NAME=$(basename "$SCRIPT_PATH")  # Just the filename

# Build parameters string from config file
# This converts each line in the config to a command-line parameter with --prefix
PARAMS=""
while IFS= read -r line || [[ -n "$line" ]]; do
  # Skip comments, empty lines, SCRIPT_PATH and PYTHON_CMD
  # These are special config entries not passed as parameters
  [[ "$line" =~ ^#.*$ || -z "$line" || "$line" =~ ^SCRIPT_PATH=.* || "$line" =~ ^PYTHON_CMD=.* ]] && continue
  
  # Extract key and value using regex pattern matching
  if [[ "$line" =~ ^([A-Za-z0-9_\-]+)=(.*)$ ]]; then
    KEY="${BASH_REMATCH[1]}"          # Parameter name
    VALUE="${BASH_REMATCH[2]}"        # Parameter value
    PARAMS="$PARAMS --$KEY $VALUE"    # Format as --key value
  fi
done < "$CONFIG_FILE"

# Log the constructed parameter string
echo "Constructed parameters: $PARAMS" >> /var/log/bootconfig.log

# Wait for all services to be ready
# This delay ensures network and other dependencies are fully available
echo "Waiting 10 seconds before starting script..." >> /var/log/bootconfig.log
sleep 10

# Change to script directory to ensure proper path resolution for imports
echo "Changing to directory $SCRIPT_DIR" >> /var/log/bootconfig.log
cd "$SCRIPT_DIR"

# Run the script with sudo to ensure proper hardware access
# Redirect both stdout and stderr to the log file
echo "Running command: sudo $PYTHON_CMD $SCRIPT_NAME $PARAMS" >> /var/log/bootconfig.log
sudo $PYTHON_CMD "$SCRIPT_NAME" $PARAMS >> /var/log/bootconfig.log 2>&1

# Log when the script exits
echo "Script exited at $(date)" >> /var/log/bootconfig.log

# Keep the service running with an infinite loop
# This ensures the script automatically restarts if it exits for any reason
while true; do
   # Wait 30 seconds before attempting restart
  echo "Script is not running, restarting in 30 seconds..." >> /var/log/bootconfig.log
  sleep 30
   # Restart the script with the same parameters
  echo "Rerunning command: sudo $PYTHON_CMD $SCRIPT_NAME $PARAMS" >> /var/log/bootconfig.log
  sudo $PYTHON_CMD "$SCRIPT_NAME" $PARAMS >> /var/log/bootconfig.log 2>&1
done
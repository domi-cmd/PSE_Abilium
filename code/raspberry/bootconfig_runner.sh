#!/bin/bash
# ===================================================================
# Raspberry Pi Auto-run Configuration Runner Script
# Purpose: Automatically runs Python scripts with parameters defined
# in a configuration file located in the boot partition
# Location: /usr/local/bin/bootconfig_runner.sh
# Usage: Called by systemd service or init system at boot
# ===================================================================

# Initialize log file - Creates/overwrites log file with startup timestamp
echo "Bootconfig runner started at $(date)" > /var/log/bootconfig.log

# Configuration file search locations
# Searches multiple locations for compatibility with different Raspberry Pi OS versions
# and mounting schemes. Order matters - first found file will be used.
CONFIG_FILES=(
  "/boot/firmware/autorun.conf"       # Pi OS Bullseye and newer
  "/boot/firmware/autorun.conf.txt"   # Alternative extension (for FAT32 compatibility)
  "/boot/autorun.conf"                # Pi OS Buster and older versions
  "/boot/autorun.conf.txt"            # Alternative extension for older systems
  "/media/pi/bootfs/autorun.conf"     # Alternative mount location
  "/media/pi/bootfs/autorun.conf.txt" # Alternative extension for manual mounts
)

# Function: find_config
# Purpose: Locates the first available configuration file
# Returns: Path to config file via stdout, exit code 0 on success, 1 on failure
find_config() {
  for config in "${CONFIG_FILES[@]}"; do
    if [ -f "$config" ]; then
      echo "$config" # Return the path to the found config file
      return 0       # Success exit code
    fi
  done
  return 1           # Failure exit code - no config found
}

# Locate configuration file using the search function
CONFIG_FILE=$(find_config)
if [ -z "$CONFIG_FILE" ]; then
   # Log error and exit if no config file is found in any location
  echo "No config file found in any of the expected locations" >> /var/log/bootconfig.log
  exit 1
fi

# Log the found config file location for debugging
echo "Found config file at $CONFIG_FILE" >> /var/log/bootconfig.log

# Source the config file to load variables directly into the environment
# This imports SCRIPT_PATH, PYTHON_CMD, and other variables from the config file
source "$CONFIG_FILE"

# Log the loaded script path for debugging
echo "Config loaded with SCRIPT_PATH=$SCRIPT_PATH" >> /var/log/bootconfig.log

# Set default Python command if not specified in the config file
# Allows for custom Python environments or versions to be specified
PYTHON_CMD=${PYTHON_CMD:-python3}
echo "Using Python command: $PYTHON_CMD" >> /var/log/bootconfig.log

# Validate that script path is defined and the file exists
# Exit with error if the path is missing or the file doesn't exist
if [ -z "$SCRIPT_PATH" ]; then
  echo "SCRIPT_PATH not defined in config file" >> /var/log/bootconfig.log
  exit 1
fi

if [ ! -f "$SCRIPT_PATH" ]; then
  echo "Python script not found: $SCRIPT_PATH" >> /var/log/bootconfig.log
  exit 1
fi

# Extract the directory and filename of the script for path handling
SCRIPT_DIR=$(dirname "$SCRIPT_PATH")    # Directory containing the script
SCRIPT_NAME=$(basename "$SCRIPT_PATH")  # Just the filename

# Build command-line parameters from config file entries
# Converts key=value pairs in config to --key value format for script arguments
PARAMS=""
while IFS= read -r line || [[ -n "$line" ]]; do
  # Skip comments, empty lines, and special config variables
  # SCRIPT_PATH and PYTHON_CMD are used by this script, not passed as parameters
  [[ "$line" =~ ^#.*$ || -z "$line" || "$line" =~ ^SCRIPT_PATH=.* || "$line" =~ ^PYTHON_CMD=.* ]] && continue
  
  # Parse key=value pairs using regex pattern matching
  if [[ "$line" =~ ^([A-Za-z0-9_\-]+)=(.*)$ ]]; then
    KEY="${BASH_REMATCH[1]}"          # Parameter name
    VALUE="${BASH_REMATCH[2]}"        # Parameter value
    PARAMS="$PARAMS --$KEY $VALUE"    # Format as --key value
  fi
done < "$CONFIG_FILE"

# Log the constructed parameter string for debugging
echo "Constructed parameters: $PARAMS" >> /var/log/bootconfig.log

# Wait for system services to be fully ready
# This delay ensures network and other system dependencies are available
echo "Waiting 10 seconds before starting script..." >> /var/log/bootconfig.log
sleep 10

# Change to script directory to ensure relative imports and file paths work correctly
echo "Changing to directory $SCRIPT_DIR" >> /var/log/bootconfig.log
cd "$SCRIPT_DIR"

# Execute the Python script with sudo for hardware access permissions
# Redirect both stdout and stderr to the log file for complete output capture
echo "Running command: sudo $PYTHON_CMD $SCRIPT_NAME $PARAMS" >> /var/log/bootconfig.log
sudo $PYTHON_CMD "$SCRIPT_NAME" $PARAMS >> /var/log/bootconfig.log 2>&1

# Log the script completion time
echo "Script exited at $(date)" >> /var/log/bootconfig.log

# Restart loop to keep the script running continuously
# This ensures automatic restart if the Python script exits unexpectedly
while true; do
  # Wait before attempting restart to avoid rapid restart loops
  echo "Script is not running, restarting in 30 seconds..." >> /var/log/bootconfig.log
  sleep 30
  # Re-execute the script with the same parameters
  echo "Rerunning command: sudo $PYTHON_CMD $SCRIPT_NAME $PARAMS" >> /var/log/bootconfig.log
  sudo $PYTHON_CMD "$SCRIPT_NAME" $PARAMS >> /var/log/bootconfig.log 2>&1
done
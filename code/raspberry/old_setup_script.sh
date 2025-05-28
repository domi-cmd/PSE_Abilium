#!/bin/bash

# =============================================================================
# E-Paper Display Setup Script
# =============================================================================
# This script automates the installation and setup of Waveshare e-Paper display
# dependencies and demo code. It supports Linux (Raspberry Pi), macOS, and Windows.
#
# Features:
# - Cross-platform OS detection
# - Automatic dependency installation for Raspberry Pi
# - Git repository cloning
# - SPI interface configuration
# - Interactive Python script creation
# =============================================================================

# Define color codes for enhanced terminal output
GREEN='\033[0;32m'    # Success messages
YELLOW='\033[1;33m'   # Warning/info messages
RED='\033[0;31m'      # Error messages
NC='\033[0m'          # No color (reset)

# Display welcome message
echo -e "${GREEN}=== E-Paper Display Setup Script ===${NC}"
echo -e "${YELLOW}This script will install dependencies for the Waveshare e-Paper display${NC}"
echo

# =============================================================================
# OPERATING SYSTEM DETECTION
# =============================================================================
# Detect the current operating system to determine appropriate installation methods
OS="$(uname -s)"
case "${OS}" in
    Linux*)     
        echo -e "${GREEN}Detected Linux system.${NC}"
        LINUX=1  # Flag to indicate Linux environment
        ;;
    Darwin*)    
        echo -e "${YELLOW}Detected macOS system.${NC}"
        MACOS=1  # Flag to indicate macOS environment
        ;;
    CYGWIN*|MINGW*|MSYS*|Windows*)
        echo -e "${YELLOW}Detected Windows system.${NC}"
        WINDOWS=1  # Flag to indicate Windows environment
        ;;
    *)          
        # Unsupported operating system - exit with error
        echo -e "${RED}Unsupported operating system: ${OS}${NC}"
        exit 1
        ;;
esac

# =============================================================================
# GIT INSTALLATION AND VERIFICATION
# =============================================================================
# Check if Git is installed on the system
if ! command -v git &> /dev/null; then
    echo -e "${YELLOW}Git not found. Installing Git...${NC}"
    
    # Install Git based on the detected operating system
    if [ "$LINUX" = 1 ]; then
        # Linux: Use apt package manager to install Git
        sudo apt-get update
        sudo apt-get install -y git
    elif [ "$MACOS" = 1 ]; then
        # macOS: Provide installation instructions (requires Homebrew)
        echo -e "${RED}Git not installed on macOS. Please install Git using Homebrew:${NC}"
        echo -e "${YELLOW}brew install git${NC}"
        exit 1
    elif [ "$WINDOWS" = 1 ]; then
        # Windows: Provide download link for Git installer
        echo -e "${RED}Git not installed on Windows. Please install Git from:${NC}"
        echo -e "${YELLOW}https://git-scm.com/download/win${NC}"
        exit 1
    fi
fi

# Verify Git installation was successful
if ! command -v git &> /dev/null; then
    echo -e "${RED}Git installation failed or not in PATH. Please install Git manually.${NC}"
    exit 1
else
    echo -e "${GREEN}Git is installed and ready to use.${NC}"
fi

# =============================================================================
# RASPBERRY PI SPECIFIC SETUP (Linux only)
# =============================================================================
# Only proceed with Raspberry Pi specific setup if running on Linux
if [ "$LINUX" = 1 ]; then
    # Update the package lists to ensure we have the latest package information
    echo -e "${GREEN}Updating package lists...${NC}"
    sudo apt-get update

    # Install essential Python3 packages required for e-Paper display functionality
    echo -e "${GREEN}Installing Python3 dependencies...${NC}"
    sudo apt-get install -y python3-pip      # Python package installer
    sudo apt-get install -y python3-pil      # Python Imaging Library for image processing
    sudo apt-get install -y python3-numpy    # Numerical computing library
    sudo apt-get install -y python3-gpiozero # GPIO control library for Raspberry Pi

    # Install spidev (SPI interface library) with fallback to pip
    echo -e "${GREEN}Installing spidev...${NC}"
    if sudo apt-get install -y python3-spidev &>/dev/null; then
      echo -e "${GREEN}Successfully installed python3-spidev via apt${NC}"
    else
      # Fallback: Install via pip with --break-system-packages flag for newer Python versions
      echo -e "${YELLOW}Installing spidev via pip with --break-system-packages flag...${NC}"
      sudo pip3 install spidev --break-system-packages
    fi

    # Install paho-mqtt (MQTT client library) with fallback to pip
    echo -e "${GREEN}Installing paho-mqtt...${NC}"
    if sudo apt-get install -y python3-paho-mqtt &>/dev/null; then
      echo -e "${GREEN}Successfully installed python3-paho-mqtt via apt${NC}"
    else
      # Fallback: Install via pip with --break-system-packages flag
      echo -e "${YELLOW}Installing paho-mqtt via pip with --break-system-packages flag...${NC}"
      sudo pip3 install paho-mqtt --break-system-packages
    fi
    
    # Install pytz (timezone library) with fallback to pip
    echo -e "${GREEN}Installing pytz...${NC}"
    if sudo apt-get install -y python3-tz &>/dev/null; then
      echo -e "${GREEN}Successfully installed python3-tz via apt${NC}"
    else
      # Fallback: Install via pip with --break-system-packages flag
      echo -e "${YELLOW}Installing pytz via pip with --break-system-packages flag...${NC}"
      sudo pip3 install pytz --break-system-packages
    fi
fi

# =============================================================================
# REPOSITORY CLONING
# =============================================================================
# Check if the e-Paper repository already exists locally
if [ ! -d "e-Paper" ]; then
    # Clone the Waveshare e-Paper repository from GitHub
    echo -e "${GREEN}Downloading the Waveshare e-Paper demo from GitHub...${NC}"
    git clone https://github.com/waveshare/e-Paper.git
    
    # Check if the clone operation was successful
    if [ $? -ne 0 ]; then
        echo -e "${RED}Failed to clone the repository. Please check your internet connection.${NC}"
        exit 1
    fi
    
    # Navigate to the Raspberry Pi specific directory
    cd e-Paper/RaspberryPi_JetsonNano/
else
    # Repository already exists, skip download and navigate to directory
    echo -e "${YELLOW}e-Paper directory already exists, skipping download${NC}"
    cd e-Paper/RaspberryPi_JetsonNano/
fi

# =============================================================================
# RASPBERRY PI HARDWARE CONFIGURATION
# =============================================================================
# Enable SPI interface if running on a Raspberry Pi (check for raspi-config)
if [ "$LINUX" = 1 ] && [ -f /usr/bin/raspi-config ]; then
    echo -e "${GREEN}Enabling SPI interface...${NC}"
    # Use raspi-config in non-interactive mode to enable SPI (0 = enable)
    sudo raspi-config nonint do_spi 0
fi

# =============================================================================
# FILE PERMISSIONS SETUP
# =============================================================================
# Set appropriate permissions for the examples directory to allow script execution
echo -e "${GREEN}Setting permissions for examples directory...${NC}"
sudo chmod -R 777 python/examples/  # Full read/write/execute permissions for all users
echo -e "${GREEN}Permissions set successfully.${NC}"

# =============================================================================
# INTERACTIVE PYTHON SCRIPT CREATION (Linux/Raspberry Pi only)
# =============================================================================
# Only proceed with Python script creation if on Linux (Raspberry Pi)
if [ "$LINUX" = 1 ]; then
    # Prompt user to create a custom Python test script
    echo -e "${GREEN}Now, let's create your Python script.${NC}"
    echo -e "${YELLOW}Enter your Python code below (press Ctrl+D when finished):${NC}"
    echo

    # Ensure the examples directory exists (create if necessary)
    mkdir -p python/examples

    # Prompt user for script filename
    echo -e "${YELLOW}Enter a name for your script (e.g., my_test.py):${NC}"
    read script_name

    # Use default filename if user doesn't provide one
    if [ -z "$script_name" ]; then
        script_name="user_epaper_test.py"
    fi

    # Capture multiline input from user and save to file in examples directory
    echo -e "${YELLOW}Now enter your Python code (press Ctrl+D when finished):${NC}"
    cat > python/examples/$script_name

    # Confirm script creation and provide usage instructions
    echo -e "${GREEN}Script saved as python/examples/$script_name${NC}"
    echo -e "${YELLOW}To run your script: python3 python/examples/$script_name${NC}"
else
    # Skip script creation for non-Raspberry Pi systems
    echo -e "${YELLOW}Skipping Python script creation as this is not running on a Raspberry Pi.${NC}"
    echo -e "${YELLOW}Clone has been completed. You can transfer these files to your Raspberry Pi.${NC}"
fi

# =============================================================================
# SETUP COMPLETION
# =============================================================================
echo -e "${GREEN}=== Setup Complete! ===${NC}"

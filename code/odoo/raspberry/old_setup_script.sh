#!/bin/bash

# Colors for better visibility
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}=== E-Paper Display Setup Script ===${NC}"
echo -e "${YELLOW}This script will install dependencies for the Waveshare e-Paper display${NC}"
echo

# Check operating system
OS="$(uname -s)"
case "${OS}" in
    Linux*)     
        echo -e "${GREEN}Detected Linux system.${NC}"
        LINUX=1
        ;;
    Darwin*)    
        echo -e "${YELLOW}Detected macOS system.${NC}"
        MACOS=1
        ;;
    CYGWIN*|MINGW*|MSYS*|Windows*)
        echo -e "${YELLOW}Detected Windows system.${NC}"
        WINDOWS=1
        ;;
    *)          
        echo -e "${RED}Unsupported operating system: ${OS}${NC}"
        exit 1
        ;;
esac

# Check if git is installed
if ! command -v git &> /dev/null; then
    echo -e "${YELLOW}Git not found. Installing Git...${NC}"
    
    if [ "$LINUX" = 1 ]; then
        sudo apt-get update
        sudo apt-get install -y git
    elif [ "$MACOS" = 1 ]; then
        echo -e "${RED}Git not installed on macOS. Please install Git using Homebrew:${NC}"
        echo -e "${YELLOW}brew install git${NC}"
        exit 1
    elif [ "$WINDOWS" = 1 ]; then
        echo -e "${RED}Git not installed on Windows. Please install Git from:${NC}"
        echo -e "${YELLOW}https://git-scm.com/download/win${NC}"
        exit 1
    fi
fi

# Verify git is now available
if ! command -v git &> /dev/null; then
    echo -e "${RED}Git installation failed or not in PATH. Please install Git manually.${NC}"
    exit 1
else
    echo -e "${GREEN}Git is installed and ready to use.${NC}"
fi

# Only proceed with Raspberry Pi specific setup if on Linux
if [ "$LINUX" = 1 ]; then
    # Update package lists
    echo -e "${GREEN}Updating package lists...${NC}"
    sudo apt-get update

    # Install Python3 dependencies
    echo -e "${GREEN}Installing Python3 dependencies...${NC}"
    sudo apt-get install -y python3-pip python3-pil python3-numpy
    sudo apt-get install -y python3-gpiozero

    # Installing spidev using apt or with break-system-packages flag for newer systems
    echo -e "${GREEN}Installing spidev...${NC}"
    if sudo apt-get install -y python3-spidev &>/dev/null; then
      echo -e "${GREEN}Successfully installed python3-spidev via apt${NC}"
    else
      echo -e "${YELLOW}Installing spidev via pip with --break-system-packages flag...${NC}"
      sudo pip3 install spidev --break-system-packages
    fi

    # Installing paho-mqtt using apt or with break-system-packages flag
    echo -e "${GREEN}Installing paho-mqtt...${NC}"
    if sudo apt-get install -y python3-paho-mqtt &>/dev/null; then
      echo -e "${GREEN}Successfully installed python3-paho-mqtt via apt${NC}"
    else
      echo -e "${YELLOW}Installing paho-mqtt via pip with --break-system-packages flag...${NC}"
      sudo pip3 install paho-mqtt --break-system-packages
    fi
    
    # Installing pytz using apt or with break-system-packages flag
    echo -e "${GREEN}Installing pytz...${NC}"
    if sudo apt-get install -y python3-tz &>/dev/null; then
      echo -e "${GREEN}Successfully installed python3-tz via apt${NC}"
    else
      echo -e "${YELLOW}Installing pytz via pip with --break-system-packages flag...${NC}"
      sudo pip3 install pytz --break-system-packages
    fi
fi

# Clone the repo if it doesn't exist
if [ ! -d "e-Paper" ]; then
    echo -e "${GREEN}Downloading the Waveshare e-Paper demo from GitHub...${NC}"
    git clone https://github.com/waveshare/e-Paper.git
    if [ $? -ne 0 ]; then
        echo -e "${RED}Failed to clone the repository. Please check your internet connection.${NC}"
        exit 1
    fi
    cd e-Paper/RaspberryPi_JetsonNano/
else
    echo -e "${YELLOW}e-Paper directory already exists, skipping download${NC}"
    cd e-Paper/RaspberryPi_JetsonNano/
fi

# Enable SPI interface if on Raspberry Pi
if [ "$LINUX" = 1 ] && [ -f /usr/bin/raspi-config ]; then
    echo -e "${GREEN}Enabling SPI interface...${NC}"
    sudo raspi-config nonint do_spi 0
fi

# Set permissions for examples directory
echo -e "${GREEN}Setting permissions for examples directory...${NC}"
sudo chmod -R 777 python/examples/
echo -e "${GREEN}Permissions set successfully.${NC}"

# Only proceed with Python script creation if on Linux (Raspberry Pi)
if [ "$LINUX" = 1 ]; then
    # Prompt user to create a Python test script
    echo -e "${GREEN}Now, let's create your Python script.${NC}"
    echo -e "${YELLOW}Enter your Python code below (press Ctrl+D when finished):${NC}"
    echo

    # Ensure the examples directory exists
    mkdir -p python/examples

    # Prompt for script name
    echo -e "${YELLOW}Enter a name for your script (e.g., my_test.py):${NC}"
    read script_name

    if [ -z "$script_name" ]; then
        script_name="user_epaper_test.py"
    fi

    # Capture multiline input and save to file in examples directory
    echo -e "${YELLOW}Now enter your Python code (press Ctrl+D when finished):${NC}"
    cat > python/examples/$script_name

    echo -e "${GREEN}Script saved as python/examples/$script_name${NC}"
    echo -e "${YELLOW}To run your script: python3 python/examples/$script_name${NC}"
else
    echo -e "${YELLOW}Skipping Python script creation as this is not running on a Raspberry Pi.${NC}"
    echo -e "${YELLOW}Clone has been completed. You can transfer these files to your Raspberry Pi.${NC}"
fi

echo -e "${GREEN}=== Setup Complete! ===${NC}"
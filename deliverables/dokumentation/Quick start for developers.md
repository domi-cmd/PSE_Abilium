# Raspberry Pi Display Script Setup Guide

This is a quick start guide to set up your Raspberry Pi to modify the display script and understand what additional processes need to be added. Prior experience is expected as this isn't a detailed guide. This guide doesn't cover the use of the Raspberry Pi image we created for easy setup.

## Prerequisites

- Raspberry Pi Zero
- SD Card
- Computer with terminal/command prompt access
- WiFi network access

## Setup Instructions

### 1. Flash Your SD Card
Flash your SD card with the [Raspberry Pi Imager tool](https://www.raspberrypi.com/software/).

### 2. Configure the Image
Once opened:
- Choose **Raspberry Pi Zero** in models
- Choose the recommended OS (Lite OS works too)
- Choose your SD card

### 3. Configure Settings
Before writing to the card, be sure to adjust the settings:
- Remember your hostname as it is important for the SSH connection
- Enter `pi` as your username (**important!**)
- Choose a secure password
- Enter your WiFi details
- Navigate to more settings and enable SSH

### 4. Write to SD Card
Save the settings and write to the card.

### 5. Add Configuration File
Drag and drop the edited `autorun.conf` file into the mounted SD card. This won't do anything yet but is needed for later.

### 6. Boot the Raspberry Pi
After completion, you can eject the SD card and put it into the Raspberry Pi and power it on.

### 7. Wait for Connection
It may take multiple minutes to establish a connection.

### 8. SSH Connection
Open up a terminal or command prompt window and enter:
```bash
ssh pi@your_hostname.local
```
Make sure your computer is connected to the same WiFi as the Raspberry Pi.

### 9. Create Setup Script
Once you have a connection, use the following command:
```bash
sudo nano setup_script.sh
```

### 10. Add Script Content
Copy the content of `old_setup_script.sh` from the GitHub repository and paste it into the field that appears.

### 11. Save the File
Then press `Ctrl+X`, then `Y`, then press `Enter`.

### 12. Make File Executable
Make the file executable with:
```bash
chmod +x setup_script.sh
```

### 13. Execute the Script
Execute it with the command:
```bash
./setup_script.sh
```

### 14. Install Dependencies
All the needed libraries will be installed. You can check the specific installations in the `old_setup_script.sh` file.

### 15. Input Display Script
After completion, you will be prompted to input your display script directly into the terminal (you need to enter `mqtt_opt.py` as the name first).

### 16. Complete Script Input
When done, press `Ctrl+D` two times.

### 17. Add Boot Configuration
You now have a working Raspberry Pi with your chosen display script, but the Raspberry Pi doesn't automatically start the script with predefined parameters yet. For that, we need to add 2 more files:
- `bootconfig_runner.sh`
- `bootconfig_service.txt`

### 18. Configure Auto-run System
Consult the [Raspberry Pi Auto-run Configuration System Documentation](https://github.com/domi-cmd/PSE_Abilium/blob/main/deliverables/dokumentation/Raspberry_Pi_Auto-run_Configuration_System_Documentation.md) for the setup of these files.

## Updating Your Script

If you made updates to your script and need to change it:

### 1. Navigate to Script Directory
Once you're connected to the Raspberry Pi via SSH, enter:
```bash
cd e-Paper/Raspberry_JetsonNano/python/examples
```

### 2. Remove Old Script
This is where your script is saved. You can remove it via:
```bash
rm mqtt_opt.py
```

### 3. Create New Script
Then create a new one (same steps as the `setup_script.sh`):
```bash
nano mqtt_opt.py
```

### 4. Make Script Executable
Make it executable:
```bash
chmod +x mqtt_opt.py
```

### 5. Restart Auto-run Service
Then you can redirect to the root directory and enter:
```bash
sudo systemctl restart bootconfig.service
```
to restart the auto-run process with the new script.

### 6. Check Service Status
You can check the service status with:
```bash
sudo systemctl status bootconfig.service
```

**Note:** These steps need to be repeated every time you want to change the script, but you can stay connected via SSH throughout the process.

## Next Steps

After completing these steps, you'll have a functional Raspberry Pi setup with your display script installed and configured for automatic startup.

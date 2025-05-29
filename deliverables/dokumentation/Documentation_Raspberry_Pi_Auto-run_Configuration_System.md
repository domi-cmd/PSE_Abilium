# Raspberry Pi Auto-run Configuration System

## Table of Contents
- [Architecture Overview](#architecture-overview)
- [System Components](#system-components)
- [Configuration Flow](#configuration-flow)
- [Parameter Configuration](#parameter-configuration)
- [Installation Guide](#installation-guide)
- [Error Handling](#error-handling)
- [Security Considerations](#security-considerations)
- [Extending the System](#extending-the-system)
- [Troubleshooting](#troubleshooting)

## Architecture Overview
This document outlines the auto-run configuration system for Raspberry Pi devices with e-Paper displays. The system allows for automatic execution of Python scripts at boot time with configurable parameters, particularly designed for MQTT-based applications that display data on e-Paper screens.

## System Components

### 1. Configuration File (`autorun.conf`)
The configuration file defines script paths and parameters for auto-execution.

- **Location**: Boot partition of the Raspberry Pi
- **Purpose**: Stores configuration parameters and script location
- **Format**: Key-value pairs with parameter name and value

#### Key Parameters
- `SCRIPT_PATH`: Path to the Python script to execute
- `rasp-name`: Identifier for the Raspberry Pi device
- `broker`: MQTT broker address
- `port`: MQTT broker port number
- `topic-prefix`: Prefix for MQTT topics
- `timezone`: Timezone configuration for the device

### 2. Runner Script (`bootconfig_runner.sh`)
The runner script reads configuration and executes the specified Python script.

- **Location**: `/usr/local/bin/bootconfig_runner.sh`
- **Purpose**: Parses configuration and launches Python script
- **Features**: Auto-restart, parameter conversion, config validation

#### Key Functions and Methods
- `find_config()`: Searches for the configuration file in multiple possible locations
- Parameter parsing: Converts configuration lines to command-line arguments
- Script execution: Runs the Python script with parameters as command arguments
- Monitoring loop: Restarts the script if it terminates unexpectedly

### 3. Systemd Service (`bootconfig_service.txt`)
The systemd service definition manages the runner script as a system service.

- **Location**: `/etc/systemd/system/bootconfig.service`
- **Purpose**: Starts the runner script at boot and manages its lifecycle
- **Features**: Auto-restart, dependency management, logging

#### Key Settings
- `After=network.target`: Ensures network is available before starting
- `Restart=on-failure`: Automatically restarts if the service fails
- `Environment=SUDO_ASKPASS=/bin/true`: Allows sudo execution without password prompts

## Configuration Flow

### 1. Boot Sequence
- Raspberry Pi boots and systemd initializes services
- `bootconfig.service` starts after network initialization
- Service executes the runner script (`bootconfig_runner.sh`)

### 2. Configuration Loading
- Runner script searches for `autorun.conf` in various locations
- Configuration file is loaded and parameters are parsed
- Script path and parameters are extracted and validated

### 3. Script Execution
- Runner changes to the script's directory
- Python script is executed with parameters converted to command-line arguments
- Runner monitors script execution and restarts it if it exits

### Configuration Flow Diagram

```
┌─────────────────┐     ┌─────────────────────┐     ┌────────────────┐
│  System Boot    │     │                     │     │                │
│  & Systemd      │────►│ bootconfig.service  │────►│ Runner Script  │
│                 │     │                     │     │                │
└─────────────────┘     └─────────────────────┘     └───────┬────────┘
                                                           │
                                                           │ reads
                                                           ▼
                                                   ┌───────────────────┐
                                                   │                   │
                                                   │   autorun.conf    │
                                                   │   (Boot Partition)│
                                                   └──────────┬────────┘
                                                              │
                                                              │ parameters
                                                              ▼
                                                   ┌───────────────────┐
                                                   │                   │
                                                   │   Python Script   │
                                                   │   (MQTT Client)   │
                                                   └───────────────────┘
```

## Parameter Configuration

### Configuration File Structure
The `autorun.conf` file uses a simple key-value format:
```
# Comments start with #
SCRIPT_PATH=/path/to/script.py
parameter-name=parameter-value
```

### Parameter Transformation
Parameters are automatically transformed from configuration file format to command-line arguments:

**In autorun.conf**:
```
rasp-name=meeting-room
broker=mqtt.example.com
port=1883
topic-prefix=test/room/
```

**Converted to command-line arguments**:
```
--rasp-name meeting-room --broker mqtt.example.com --port 1883 --topic-prefix test/room/
```

### Essential Parameters
| Parameter | Purpose | Example Value |
|-----------|---------|---------------|
| SCRIPT_PATH | Path to the Python script | /home/pi/e-Paper/RaspberryPi_JetsonNano/python/examples/mqtt_opt.py |
| rasp-name | Device identifier | office-display |
| broker | MQTT broker address | mqtt.company.com |
| port | MQTT broker port | 1883 |
| topic-prefix | Topic prefix for MQTT | test/room/ |
| timezone | Device timezone | Europe/Paris |

## Installation Guide

### Prerequisites
- Raspberry Pi with Raspberry Pi OS
- Boot partition accessible for writing configuration
- Python environment for the target script

### Step 1: Install the Runner Script
1. Save the runner script to the system:
   ```bash
   sudo nano /usr/local/bin/bootconfig_runner.sh
   # Paste the script content
   sudo chmod +x /usr/local/bin/bootconfig_runner.sh
   ```

### Step 2: Install the Systemd Service
1. Create the service definition:
   ```bash
   sudo nano /etc/systemd/system/bootconfig.service
   # Paste the service definition
   ```

2. Enable and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable bootconfig.service
   sudo systemctl start bootconfig.service
   ```

### Step 3: Configure the Auto-run Parameters
1. Create the configuration file in the boot partition:
   ```bash
   sudo nano /boot/autorun.conf
   # Add your configuration
   ```

2. Example configuration:
   ```
   SCRIPT_PATH=/home/pi/e-Paper/RaspberryPi_JetsonNano/python/examples/mqtt_opt.py
   rasp-name=reception-display
   broker=mqtt.example.com
   port=1883
   topic-prefix=test/room/
   timezone=Europe/Paris
   ```

## Error Handling

### Automatic Recovery
- The runner script automatically restarts the Python script if it exits
- The systemd service restarts the runner if it fails
- Wait periods between restart attempts prevent rapid cycling

### Log Monitoring
- Script activity is logged to `/var/log/bootconfig.log`
- Systemd logs can be viewed with `journalctl -u bootconfig.service`
- Errors and restart events are recorded in these logs

### Common Errors
- **Missing configuration file**: Runner exits with error logged
- **Invalid script path**: Error logged with specific message
- **Parameter issues**: Passed to Python script which should handle validation

## Security Considerations
- The service runs with sudo privileges to access hardware
- Configuration file should have restricted permissions
- Consider encrypting sensitive parameters (e.g., MQTT credentials)
- Service isolation can be improved with systemd options

## Extending the System

### Adding Custom Parameters
Simply add new key-value pairs to the `autorun.conf` file:
```
new-parameter=value
```

### Supporting Different Script Types
The system can run any executable script, not just Python:
1. Set `PYTHON_CMD` in the config to change the interpreter
2. For non-Python scripts, modify the runner script accordingly

### Remote Configuration Updates
To enable remote updates of configuration:
1. Set up a mechanism to update the boot partition
2. Implement a signal handler in the Python script to reload configuration
3. Use MQTT messages to trigger configuration reloads

## Troubleshooting

### Common Issues and Solutions
- **Service doesn't start**: Check service status with `systemctl status bootconfig.service`
- **Script doesn't run**: Verify the script path and permissions
- **Parameters not working**: Check parameter format in both config and script

### Debugging Steps
1. **Check service status**:
   ```bash
   sudo systemctl status bootconfig.service
   ```

2. **Review the logs**:
   ```bash
   sudo cat /var/log/bootconfig.log
   sudo journalctl -u bootconfig.service
   ```

3. **Test manual execution**:
   ```bash
   sudo /usr/local/bin/bootconfig_runner.sh
   ```

4. **Verify configuration file**:
   ```bash
   sudo cat /boot/autorun.conf
   ```

---

*Document Version: 1.0*  
*Last Updated: May 21, 2025*
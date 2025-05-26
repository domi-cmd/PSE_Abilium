# Package initialization file for the main module
# This file makes Python treat the directory as a package and defines what gets imported
# when someone imports this package

# Import all submodules to make them available when the package is imported
from . import connection_configuration, calendar_event, partner_extension, mqtt_connector

# connection_configuration       # Module for handling connection settings and configuration
# calendar_event                 # Module for calendar event management and operations
# partner_extension              # Module for partner/third-party extensions and integrations
# import mqtt_connector          # Module for MQTT (Message Queuing Telemetry Transport) connectivity
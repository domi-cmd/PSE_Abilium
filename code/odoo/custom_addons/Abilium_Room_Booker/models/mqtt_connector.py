# -*- coding: utf-8 -*-
import threading
import time
import ssl
import logging
import paho.mqtt.client as mqtt

# Get logger instance for this module
_logger = logging.getLogger(__name__)


class MqttConnectionManager:
    """
    Singleton to manage MQTT connections across Odoo instances

    This class ensures only one instance exists and manages multiple MQTT client connections,
    allowing for centralized connection management, registration, and cleanup.
    """
    # Class variables for singleton pattern
    _instance = None
    _connections = {}
    _lock = threading.RLock()

    def __new__(cls):
        """
        Implement singleton pattern - ensures only one instance of the manager exists

        Returns:
            MqttConnectionManager: The single instance of the connection manager
        """
        if cls._instance is None:
            cls._instance = super(MqttConnectionManager, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        """
        Initialize the connection manager instance

        Sets up the connections dictionary and thread lock for safe concurrent access
        """
        self._connections = {}
        self._lock = threading.RLock()

    def register(self, connection_id, client, thread=None, publisher_thread=None):
        """
        Register a new MQTT connection with the manager

        Args:
             connection_id (str): Unique identifier for this connection
             client (mqtt.Client): The MQTT client instance
             thread (threading.Thread, optional): Main connection thread
             publisher_thread (threading.Thread, optional): Publisher thread for outgoing messages
                """
        with self._lock:
            # Store connection details with timestamp for tracking
            self._connections[connection_id] = {
                'client': client,
                'thread': thread,
                'publisher_thread': publisher_thread,
                'timestamp': time.time() # Track when connection was registered
            }

    def unregister(self, connection_id):
        """
        Unregister and cleanup an MQTT connection

        Args:
            connection_id (str): Unique identifier of the connection to remove

            Returns:
                bool: True if connection was found and removed, False otherwise
        """
        with self._lock:
            # Check if connection exists
            if connection_id in self._connections:
                # Remove connection from registry
                conn = self._connections.pop(connection_id)
                # Get the MQTT client
                client = conn.get('client')
                if client:
                    try:
                        # Disconnect client if still connected
                        if client.is_connected():
                            client.disconnect()
                        # Stop the client's network loop
                        client.loop_stop()
                    except Exception as e:
                        _logger.error("Error disconnecting client: %s", e)
                # Stop publisher thread if it exists and is running
                pub_thread = conn.get('publisher_thread')
                if pub_thread and pub_thread.is_alive():
                    # Signal thread to stop (assumes thread checks do_run flag)
                    pub_thread.do_run = False

                return True
        return False

    def get_client(self, connection_id):
        """
        Retrieve the MQTT client for a specific connection

        Args:
           connection_id (str): Unique identifier of the connection

        Returns:
            mqtt.Client or None: The MQTT client if found, None otherwise
        """
        with self._lock:
            conn = self._connections.get(connection_id)
            return conn.get('client') if conn else None

    def is_connected(self, connection_id):
        """
        Check if a specific MQTT connection is currently active

        Args:
            connection_id (str): Unique identifier of the connection to check

        Returns:
            bool: True if connection exists and client is connected, False otherwise
        """
        client = self.get_client(connection_id)
        return client and client.is_connected()
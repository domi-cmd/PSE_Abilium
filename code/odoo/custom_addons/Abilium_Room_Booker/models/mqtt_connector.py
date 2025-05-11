# -*- coding: utf-8 -*-
import threading
import time
import ssl
import logging
import paho.mqtt.client as mqtt
from odoo import fields, api

_logger = logging.getLogger(__name__)


class MqttConnectionManager:
    """Singleton to manage MQTT connections across Odoo instances"""
    _instance = None
    _connections = {}
    _lock = threading.RLock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MqttConnectionManager, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self._connections = {}
        self._lock = threading.RLock()

    def register(self, connection_id, client, thread=None, publisher_thread=None):
        with self._lock:
            self._connections[connection_id] = {
                'client': client,
                'thread': thread,
                'publisher_thread': publisher_thread,
                'timestamp': time.time()
            }

    def unregister(self, connection_id):
        with self._lock:
            if connection_id in self._connections:
                conn = self._connections.pop(connection_id)
                client = conn.get('client')
                if client:
                    try:
                        if client.is_connected():
                            client.disconnect()
                        client.loop_stop()
                    except Exception as e:
                        _logger.error("Error disconnecting client: %s", e)

                pub_thread = conn.get('publisher_thread')
                if pub_thread and pub_thread.is_alive():
                    pub_thread.do_run = False

                return True
        return False

    def get_client(self, connection_id):
        with self._lock:
            conn = self._connections.get(connection_id)
            return conn.get('client') if conn else None

    def is_connected(self, connection_id):
        client = self.get_client(connection_id)
        return client and client.is_connected()
    
    # ----- MQTT Callback Methods -----
    def _update_connection_status(self, connection, state, error_msg=False):
        """Update connection status in a thread-safe way"""
        try:
            with connection.pool.cursor() as cr:
                env = api.Environment(cr, connection.env.uid, {})
                conn = env['rasproom.connection'].browse(connection.id)
                
                if not conn.exists():
                    return
                
                vals = {'mqtt_connection_state': state}
                if state == 'connected':
                    vals['mqtt_last_connection'] = fields.Datetime.now()
                if error_msg:
                    vals['mqtt_error_message'] = error_msg
                
                conn.write(vals)
                cr.commit()
        except Exception as e:
            _logger.error("Failed to update connection status: %s", e)

    def on_connect(self, client, userdata, flags, rc):
        """Callback when MQTT client connects"""
        connection_id = userdata.get('connection_id')
        
        if not connection_id:
            return
            
        try:
            connection = self._connections.get(connection_id)
            if not connection:
                return

            if rc == 0:
                # Connection successful
                self._update_connection_status(connection, 'connected')
                
                # Subscribe to topics
                topic = f"{connection.mqtt_topic_prefix}{connection.raspName}/#"
                client.subscribe(topic, int(connection.mqtt_qos or 0))
                _logger.info("Subscribed to %s", topic)
            else:
                # Connection failed
                errors = {
                    1: "Incorrect protocol version",
                    2: "Invalid client identifier",
                    3: "Server unavailable",
                    4: "Bad credentials",
                    5: "Not authorized"
                }
                error_msg = errors.get(rc, f"Unknown error: {rc}")
                self._update_connection_status(connection, 'error', error_msg)
                
        except Exception as e:
            _logger.error("Error in on_connect callback: %s", e)

    def on_disconnect(self, client, userdata, rc):
        """Callback when MQTT client disconnects"""
        connection_id = userdata.get('connection_id')
        
        if not connection_id:
            return
            
        try:
            connection = self._connections.get(connection_id)
            if not connection:
                return

            if rc == 0:
                # Normal disconnection
                self._update_connection_status(connection, 'disconnected')
            else:
                # Unexpected disconnection
                error_msg = f"Unexpected disconnect (code {rc})"
                self._update_connection_status(connection, 'error', error_msg)
                
                # Schedule reconnection attempt
                threading.Timer(5.0, lambda: self._reconnect_mqtt(connection_id)).start()
                        
        except Exception as e:
            _logger.error("Error in on_disconnect callback: %s", e)

    def on_message(self, client, userdata, message):
        """Callback when MQTT message is received"""
        connection_id = userdata.get('connection_id')
        
        if not connection_id:
            return
            
        try:
            connection = self._connections.get(connection_id)
            if not connection:
                return

            topic = message.topic
            payload = message.payload.decode('utf-8')
            _logger.info("Received message: %s - %s", topic, payload)
            
            # Process message (implement your message handling logic here)
            
        except Exception as e:
            _logger.error("Error in on_message callback: %s", e)

    def _reconnect_mqtt(self, connection_id):
        """Reconnect MQTT client after disconnect"""
        connection = self._connections.get(connection_id)
        if connection:
            client = connection['client']
            if client:
                _logger.info("Attempting to reconnect...")
                client.reconnect()

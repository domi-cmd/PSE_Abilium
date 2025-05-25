# -*- coding: utf-8 -*-
import threading
import time
import ssl
import logging
import paho.mqtt.client as mqtt

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
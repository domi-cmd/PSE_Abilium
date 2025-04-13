# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
import logging
import threading
import time
import ssl
from contextlib import contextmanager

_logger = logging.getLogger(__name__)

try:
    import paho.mqtt.client as mqtt
    HAS_MQTT = True
except ImportError:
    HAS_MQTT = False
    _logger.warning("paho-mqtt library not installed. MQTT functionality disabled")


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
    
    def register(self, connection_id, client, thread=None):
        with self._lock:
            self._connections[connection_id] = {
                'client': client,
                'thread': thread,
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
                return True
        return False
    
    def get_client(self, connection_id):
        with self._lock:
            conn = self._connections.get(connection_id)
            return conn.get('client') if conn else None
    
    def is_connected(self, connection_id):
        client = self.get_client(connection_id)
        return client and client.is_connected()


class RoomRaspConnection(models.Model):
    _name = 'rasproom.connection'
    _description = 'Raspberry & Room Connection'
    _rec_name = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Connection Name', required=True, tracking=True)
    room_id = fields.Many2one('meeting.room', string='Room', required=True, tracking=True, ondelete='cascade')
    rasp_name = fields.Char(string='Raspberry Name', required=True, tracking=True)
    active = fields.Boolean(string='Active', default=True, tracking=True)

    # MQTT Configuration Fields
    use_mqtt = fields.Boolean(string='Use MQTT', default=True)
    mqtt_broker = fields.Char(string='MQTT Broker', default='test.mosquitto.org')
    mqtt_port = fields.Integer(string='MQTT Port', default=8883)
    mqtt_username = fields.Char(string='MQTT Username')
    mqtt_password = fields.Char(string='MQTT Password', password=True)
    mqtt_topic_prefix = fields.Char(string='Topic Prefix', default='test/room/')
    mqtt_use_tls = fields.Boolean(string='Use TLS', default=True)
    mqtt_client_id = fields.Char(string='Client ID', help="Leave empty for auto-generation")
    mqtt_qos = fields.Selection([
        ('0', 'At most once (0)'),
        ('1', 'At least once (1)'),
        ('2', 'Exactly once (2)')
    ], string='QoS Level', default='0')
    mqtt_keep_alive = fields.Integer(string='Keep Alive', default=60)
    
    # MQTT Connection Status Fields
    mqtt_last_connection = fields.Datetime(string='Last Connection', readonly=True)
    mqtt_connection_state = fields.Selection([
        ('disconnected', 'Disconnected'),
        ('connecting', 'Connecting'),
        ('connected', 'Connected'),
        ('error', 'Error')
    ], string='Connection State', default='disconnected', readonly=True, tracking=True)
    mqtt_error_message = fields.Char(string='Last Error', readonly=True)
    connection_state_display = fields.Char(string='Connection State Display', compute='_compute_connection_state_display')

    @property
    def mqtt_manager(self):
        return MqttConnectionManager()

    @contextmanager
    def _get_new_cursor(self):
        """Get a new cursor for thread-safe operations"""
        new_cr = self.pool.cursor()
        try:
            yield new_cr
        finally:
            new_cr.close()

    @api.depends('mqtt_connection_state')
    def _compute_connection_state_display(self):
        """Compute CSS class for connection state display"""
        state_mapping = {
            'connected': 'text-success',
            'connecting': 'text-warning',
            'error': 'text-danger',
            'disconnected': 'text-muted'
        }
        for record in self:
            record.connection_state_display = state_mapping.get(record.mqtt_connection_state, 'text-muted')

    def _update_connection_status(self, connection_id, state, error_msg=False):
        """Update connection status in a thread-safe way"""
        try:
            with self._get_new_cursor() as cr:
                env = api.Environment(cr, self.env.uid, {})
                connection = env['rasproom.connection'].browse(connection_id)
                
                if not connection.exists():
                    return
                    
                vals = {'mqtt_connection_state': state}
                if state == 'connected':
                    vals['mqtt_last_connection'] = fields.Datetime.now()
                if error_msg:
                    vals['mqtt_error_message'] = error_msg
                
                connection.write(vals)
                cr.commit()
        except Exception as e:
            _logger.error("Failed to update connection status: %s", e)

    def _on_connect(self, client, userdata, flags, rc):
        """Callback when MQTT client connects"""
        connection_id = userdata.get('connection_id')
        
        if not connection_id:
            return
            
        try:
            if rc == 0:
                # Connection successful
                self._update_connection_status(connection_id, 'connected')
                
                # Subscribe to topics
                with self._get_new_cursor() as cr:
                    env = api.Environment(cr, self.env.uid, {})
                    connection = env['rasproom.connection'].browse(connection_id)
                    if connection.exists():
                        topic = f"{connection.mqtt_topic_prefix}{connection.rasp_name}/#"
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
                self._update_connection_status(connection_id, 'error', error_msg)
                
        except Exception as e:
            _logger.error("Error in on_connect callback: %s", e)

    def _on_disconnect(self, client, userdata, rc):
        """Callback when MQTT client disconnects"""
        connection_id = userdata.get('connection_id')
        
        if not connection_id:
            return
            
        try:
            if rc == 0:
                # Normal disconnection
                self._update_connection_status(connection_id, 'disconnected')
            else:
                # Unexpected disconnection
                error_msg = f"Unexpected disconnect (code {rc})"
                self._update_connection_status(connection_id, 'error', error_msg)
                
                # Schedule reconnection attempt
                with self._get_new_cursor() as cr:
                    env = api.Environment(cr, self.env.uid, {})
                    connection = env['rasproom.connection'].browse(connection_id)
                    if connection.exists() and connection.active and connection.use_mqtt:
                        threading.Timer(5.0, lambda: self._reconnect_mqtt(connection_id)).start()
                        
        except Exception as e:
            _logger.error("Error in on_disconnect callback: %s", e)

    def _on_message(self, client, userdata, message):
        """Callback when MQTT message is received"""
        connection_id = userdata.get('connection_id')
        
        if not connection_id:
            return
            
        try:
            with self._get_new_cursor() as cr:
                env = api.Environment(cr, self.env.uid, {})
                connection = env['rasproom.connection'].browse(connection_id)
                
                if not connection.exists():
                    return
                    
                topic = message.topic
                payload = message.payload.decode('utf-8')
                _logger.info("Received message: %s - %s", topic, payload)
                
                # Process message (implement your message handling logic here)
                
        except Exception as e:
            _logger.error("Error in on_message callback: %s", e)

    def _mqtt_loop_start(self, connection_id):
        """Start MQTT client loop in a separate thread"""
        try:
            with self._get_new_cursor() as cr:
                env = api.Environment(cr, self.env.uid, {})
                connection = env['rasproom.connection'].browse(connection_id)
                
                if not connection.exists() or not connection.active or not connection.use_mqtt:
                    return
                    
                client = mqtt.Client(
                    client_id=connection.mqtt_client_id or f'odoo-{connection_id}-{int(time.time())}'[:23],
                    userdata={'connection_id': connection_id}
                )
                
                # Configure client
                client.on_connect = self._on_connect
                client.on_disconnect = self._on_disconnect
                client.on_message = self._on_message
                client.enable_logger(_logger)
                
                if connection.mqtt_username:
                    client.username_pw_set(connection.mqtt_username, connection.mqtt_password)
                    
                if connection.mqtt_use_tls:
                    client.tls_set(cert_reqs=ssl.CERT_NONE)
                    client.tls_insecure_set(True)
                
                # Connect asynchronously
                client.connect_async(connection.mqtt_broker, connection.mqtt_port, 
                                    keepalive=connection.mqtt_keep_alive)
                client.loop_start()
                
                # Register client
                self.mqtt_manager.register(connection_id, client)
                
                # Update status
                connection.write({'mqtt_connection_state': 'connecting'})
                cr.commit()
                
        except Exception as e:
            _logger.error("Failed to start MQTT loop: %s", e)
            self._update_connection_status(connection_id, 'error', str(e))

    def _reconnect_mqtt(self, connection_id):
        """Attempt to reconnect MQTT"""
        try:
            with self._get_new_cursor() as cr:
                env = api.Environment(cr, self.env.uid, {})
                connection = env['rasproom.connection'].browse(connection_id)
                
                if not connection.exists() or not connection.active or not connection.use_mqtt:
                    return
                    
                _logger.info("Attempting to reconnect MQTT for %s", connection.name)
                
                # Force disconnect and clean up
                self.mqtt_manager.unregister(connection_id)
                
                # Start new connection
                self._mqtt_loop_start(connection_id)
                
        except Exception as e:
            _logger.error("Reconnection attempt failed: %s", e)

    def connect_mqtt(self):
        """Connect to MQTT broker"""
        self.ensure_one()
        
        if not HAS_MQTT:
            self.write({
                'mqtt_connection_state': 'error',
                'mqtt_error_message': _("MQTT functionality is not available. Please install paho-mqtt library.")
            })
            return False
            
        if not self.use_mqtt:
            return False
            
        # Disconnect any existing connection
        self.disconnect_mqtt()
        
        # Start new connection in a separate thread to avoid blocking UI
        self._mqtt_loop_start(self.id)
        
        return True

    def disconnect_mqtt(self):
        """Disconnect from MQTT broker"""
        self.ensure_one()
        
        # Unregister from manager (handles client disconnection)
        if self.mqtt_manager.unregister(self.id):
            self.write({'mqtt_connection_state': 'disconnected'})
            
        return True

    def test_mqtt_connection(self):
        """Test MQTT connection"""
        self.ensure_one()
        
        if not HAS_MQTT:
            return self._show_notification("MQTT Test", "paho-mqtt library not installed", 'warning')
            
        if not self.use_mqtt:
            return self._show_notification("MQTT Test", "MQTT is disabled for this connection", 'warning')
            
        try:
            # Create a temporary client for testing
            client_id = f'odoo-test-{self.id}-{int(time.time())}'[:23]
            client = mqtt.Client(client_id=client_id)
            
            if self.mqtt_username:
                client.username_pw_set(self.mqtt_username, self.mqtt_password)
                
            if self.mqtt_use_tls:
                client.tls_set(cert_reqs=ssl.CERT_NONE)
                client.tls_insecure_set(True)
            
            # Set up connection timeout
            connected = False
            
            def on_connect(client, userdata, flags, rc):
                nonlocal connected
                connected = (rc == 0)
            
            client.on_connect = on_connect
            
            # Try to connect
            client.connect(self.mqtt_broker, self.mqtt_port, keepalive=10)
            client.loop_start()
            
            # Wait for connection
            timeout = time.time() + 5  # 5 second timeout
            while time.time() < timeout and not connected:
                time.sleep(0.1)
            
            # Cleanup
            client.disconnect()
            client.loop_stop()
            
            if connected:
                return self._show_notification("MQTT Test", f"Successfully connected to {self.mqtt_broker}", 'success')
            else:
                return self._show_notification("MQTT Test", f"Failed to connect to {self.mqtt_broker}", 'danger')
                
        except Exception as e:
            return self._show_notification("MQTT Test", f"Error: {str(e)}", 'danger')

    def publish_test_message(self):
        """Publish test message to MQTT broker"""
        self.ensure_one()
        
        if not HAS_MQTT:
            return self._show_notification("MQTT Publish", "MQTT library not installed", 'danger')
            
        if not self.use_mqtt:
            return self._show_notification("MQTT Publish", "MQTT is disabled for this connection", 'danger')
            
        client = self.mqtt_manager.get_client(self.id)
        if not client or not client.is_connected():
            return self._show_notification("MQTT Publish", "Not connected to MQTT broker", 'danger')
            
        try:
            topic = f"{self.mqtt_topic_prefix}{self.rasp_name}/test"
            payload = "Test message from Odoo"
            qos = int(self.mqtt_qos or 0)
            result = client.publish(topic, payload, qos=qos)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                return self._show_notification("MQTT Publish", f"Test message published to {topic}", 'success')
            else:
                return self._show_notification("MQTT Publish", f"Failed to publish test message: {result.rc}", 'danger')
                
        except Exception as e:
            return self._show_notification("MQTT Publish", f"Error: {str(e)}", 'danger')

    def _show_notification(self, title, message, notification_type='info'):
        """Show notification in UI"""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _(title),
                'message': _(message),
                'type': notification_type,
                'sticky': notification_type == 'danger',
            }
        }

    @api.model_create_multi
    def create(self, vals_list):
        """Create records and start MQTT connections"""
        records = super().create(vals_list)
        
        # Connect active MQTT connections
        for record in records:
            if record.use_mqtt and record.active:
                record.connect_mqtt()
                
        return records

    def write(self, vals):
        """Update records and manage MQTT connections"""
        # Normalize 'status' to 'active' if present
        if 'status' in vals:
            vals['active'] = vals.pop('status')
            
        result = super().write(vals)
        
        # Check if any relevant fields changed
        mqtt_fields = {
            'use_mqtt', 'mqtt_broker', 'mqtt_port', 'mqtt_username', 'mqtt_password',
            'mqtt_topic_prefix', 'mqtt_use_tls', 'mqtt_client_id', 'mqtt_keep_alive',
            'rasp_name', 'active'
        }
        
        if mqtt_fields.intersection(vals.keys()):
            for record in self:
                if record.use_mqtt and record.active:
                    record.disconnect_mqtt()
                    record.connect_mqtt()
                else:
                    record.disconnect_mqtt()
                    
        return result

    def unlink(self):
        """Disconnect MQTT before deletion"""
        for record in self:
            record.disconnect_mqtt()
            
        return super().unlink()

    @api.model
    def _cron_mqtt_connection_monitor(self):
        """Cron job to monitor and maintain MQTT connections"""
        connections = self.search([
            ('use_mqtt', '=', True),
            ('active', '=', True)
        ])
        
        manager = MqttConnectionManager()
        
        for connection in connections:
            try:
                client = manager.get_client(connection.id)
                
                if not client or not client.is_connected():
                    _logger.info("(Re)connecting %s", connection.name)
                    connection.disconnect_mqtt()
                    connection.connect_mqtt()
                    
            except Exception as e:
                _logger.error("Monitor error for %s: %s", connection.name, e)

    def action_connect(self):
        """UI action to connect to MQTT broker"""
        self.ensure_one()
        
        if not self.use_mqtt:
            return self._show_notification("MQTT Connection", "MQTT is disabled for this connection", 'warning')
            
        result = self.connect_mqtt()
        
        if result:
            return self._show_notification("MQTT Connection", "Connecting to MQTT broker", 'info')
        else:
            error_msg = self.mqtt_error_message or _("Failed to connect")
            return self._show_notification("MQTT Connection", error_msg, 'danger')
            
    def action_disconnect(self):
        """UI action to disconnect from MQTT broker"""
        self.ensure_one()
        
        result = self.disconnect_mqtt()
        
        if result:
            return self._show_notification("MQTT Connection", "Disconnected from MQTT broker", 'info')
        else:
            return self._show_notification("MQTT Connection", "Failed to disconnect", 'danger')
from odoo import models, fields, api, _
import logging
import json
from datetime import datetime
import threading

_logger = logging.getLogger(__name__)

# Import paho.mqtt conditionally to avoid startup errors
try:
    import paho.mqtt.client as mqtt
    HAS_MQTT = True
except ImportError:
    HAS_MQTT = False
    _logger.warning("paho-mqtt library not installed. MQTT functionality will be disabled.")

class RoomRaspConnection(models.Model):
    _name = 'rasproom.connection'
    _description = 'Raspberry & Room Connection'
    # _inherit = ['mail.thread', 'mail.activity.mixin'] - Commented out as it may not be needed

    name = fields.Char(string='Connection Name', required=True, tracking=True)
    room_id = fields.Many2one('meeting.room', string='Room', required=True, tracking=True)
    raspName = fields.Char(string='Raspberry Name', required=True, tracking=True)
    status = fields.Boolean(string='Active', default=True, tracking=True)
    
    # MQTT Configuration Fields
    use_mqtt = fields.Boolean(string='Use MQTT', default=False)
    mqtt_broker = fields.Char(string='MQTT Broker')
    mqtt_port = fields.Integer(string='MQTT Port', default=1883)
    mqtt_username = fields.Char(string='MQTT Username')
    mqtt_password = fields.Char(string='MQTT Password', password=True)
    mqtt_topic_prefix = fields.Char(string='Topic Prefix', default='meeting/room/')
    mqtt_use_tls = fields.Boolean(string='Use TLS', default=False)
    mqtt_client_id = fields.Char(string='Client ID')
    mqtt_qos = fields.Selection([
        ('0', 'At most once (0)'),
        ('1', 'At least once (1)'),
        ('2', 'Exactly once (2)')
    ], string='QoS Level', default='0')
    mqtt_keep_alive = fields.Integer(string='Keep Alive', default=60)
    mqtt_last_connection = fields.Datetime(string='Last Connection', readonly=True)
    mqtt_connection_state = fields.Selection([
        ('disconnected', 'Disconnected'),
        ('connecting', 'Connecting'),
        ('connected', 'Connected'),
        ('error', 'Error')
    ], string='Connection State', default='disconnected', readonly=True)
    
    # MQTT client instances stored as class variables (not stored in database)
    _mqtt_clients = {}
    _mqtt_threads = {}
    
    # Lock for thread safety
    _mqtt_lock = threading.Lock()
    
    def test_mqtt_connection(self):
        """Test the MQTT connection with current settings"""
        self.ensure_one()
        
        if not HAS_MQTT:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("MQTT Connection Test"),
                    'message': _("The paho-mqtt library is not installed. Please install it with: pip install paho-mqtt"),
                    'type': 'warning',
                }
            }
            
        if not self.use_mqtt:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("MQTT Connection Test"),
                    'message': _("MQTT is not enabled for this connection."),
                    'type': 'warning',
                }
            }
        
        try:
            # Create a temporary client for testing
            client_id = self.mqtt_client_id or f"odoo-test-{self.id}"
            client = mqtt.Client(client_id=client_id)
            
            if self.mqtt_username:
                client.username_pw_set(self.mqtt_username, self.mqtt_password)
                
            if self.mqtt_use_tls:
                client.tls_set()
            
            # Connect with a short timeout
            client.connect(self.mqtt_broker, self.mqtt_port, keepalive=10)
            
            # Disconnect immediately
            client.disconnect()
            
            self.mqtt_last_connection = fields.Datetime.now()
            self.mqtt_connection_state = 'connected'
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("MQTT Connection Test"),
                    'message': _("Successfully connected to MQTT broker."),
                    'type': 'success',
                }
            }
                
        except Exception as e:
            self.mqtt_connection_state = 'error'
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("MQTT Connection Test"),
                    'message': _("Error: %s") % str(e),
                    'type': 'danger',
                }
            }

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        """Callback when the client connects to the MQTT broker"""
        connection_id = userdata.get('connection_id')
        if not connection_id:
            _logger.error("MQTT connection callback without connection ID")
            return
            
        with api.Environment.manage():
            new_cr = self.env.registry.cursor()
            try:
                # Get a fresh environment with the new cursor
                env = api.Environment(new_cr, self.env.uid, self.env.context)
                connection = env['rasproom.connection'].browse(connection_id)
                
                if rc == 0:
                    connection.write({
                        'mqtt_connection_state': 'connected',
                        'mqtt_last_connection': fields.Datetime.now()
                    })
                    _logger.info(f"MQTT connected successfully.")
                else:
                    error_messages = {
                        1: "Connection refused - incorrect protocol version",
                        2: "Connection refused - invalid client identifier",
                        3: "Connection refused - server unavailable",
                        4: "Connection refused - bad username or password",
                        5: "Connection refused - not authorized"
                    }
                    error_msg = error_messages.get(rc, f"Unknown error code: {rc}")
                    _logger.error(f"MQTT connection failed: {error_msg}")
                    
                    connection.write({
                        'mqtt_connection_state': 'error',
                    })
                
                new_cr.commit()
            except Exception as e:
                _logger.error(f"Error in MQTT connect callback: {str(e)}")
                new_cr.rollback()
            finally:
                new_cr.close()
    
    def _on_mqtt_disconnect(self, client, userdata, rc):
        """Callback when the client disconnects from the MQTT broker"""
        connection_id = userdata.get('connection_id')
        if not connection_id:
            _logger.error("MQTT disconnect callback without connection ID")
            return
            
        with api.Environment.manage():
            new_cr = self.env.registry.cursor()
            try:
                # Get a fresh environment with the new cursor
                env = api.Environment(new_cr, self.env.uid, self.env.context)
                connection = env['rasproom.connection'].browse(connection_id)
                
                if rc == 0:
                    # Normal disconnection
                    connection.write({
                        'mqtt_connection_state': 'disconnected',
                    })
                    _logger.info(f"MQTT disconnected normally for {connection.name}")
                else:
                    # Unexpected disconnection
                    connection.write({
                        'mqtt_connection_state': 'error',
                    })
                    _logger.warning(f"MQTT disconnected unexpectedly with code {rc} for {connection.name}")
                
                new_cr.commit()
            except Exception as e:
                _logger.error(f"Error in MQTT disconnect callback: {str(e)}")
                new_cr.rollback()
            finally:
                new_cr.close()
    
    def _mqtt_loop(self):
        """Run the MQTT client loop in a separate thread"""
        _logger.info("Starting MQTT client loop")
        try:
            # Get the client for this instance
            client = self._mqtt_clients.get(self.id)
            if client:
                # Run the network loop forever
                client.loop_forever()
        except Exception as e:
            _logger.error(f"MQTT loop error: {str(e)}")
        finally:
            _logger.info("MQTT client loop ended")
    
    def connect_mqtt(self):
        """Connect to the MQTT broker"""
        self.ensure_one()
        
        if not HAS_MQTT:
            _logger.warning("Cannot connect to MQTT: paho-mqtt library not installed")
            return False
            
        if not self.use_mqtt:
            _logger.warning("MQTT is not enabled for this connection")
            return False
            
        if not self.mqtt_broker:
            _logger.warning("MQTT broker not configured")
            return False
            
        # Stop any existing connection
        self.disconnect_mqtt()
        
        with self._mqtt_lock:
            try:
                self.write({'mqtt_connection_state': 'connecting'})
                
                # Create a new client
                client_id = self.mqtt_client_id or f"odoo-{self.id}"
                new_client = mqtt.Client(client_id=client_id, userdata={'connection_id': self.id})
                
                # Set callbacks
                new_client.on_connect = self._on_mqtt_connect
                new_client.on_disconnect = self._on_mqtt_disconnect
                
                # Set authentication if needed
                if self.mqtt_username:
                    new_client.username_pw_set(self.mqtt_username, self.mqtt_password)
                
                # Set TLS if needed
                if self.mqtt_use_tls:
                    new_client.tls_set()
                
                # Connect to broker
                new_client.connect(self.mqtt_broker, self.mqtt_port, keepalive=self.mqtt_keep_alive)
                
                # Store the client in the class dictionary
                self._mqtt_clients[self.id] = new_client
                
                # Start the background thread
                thread = threading.Thread(target=self._mqtt_loop)
                thread.daemon = True
                thread.start()
                
                # Store the thread in the class dictionary
                self._mqtt_threads[self.id] = thread
                
                return True
                
            except Exception as e:
                _logger.error(f"MQTT connection error: {str(e)}")
                self.write({'mqtt_connection_state': 'error'})
                if self.id in self._mqtt_clients:
                    del self._mqtt_clients[self.id]
                return False

    def disconnect_mqtt(self):
        """Disconnect from the MQTT broker"""
        self.ensure_one()
        
        with self._mqtt_lock:
            if self.id in self._mqtt_clients:
                try:
                    # Disconnect cleanly
                    self._mqtt_clients[self.id].disconnect()
                    
                    # Give the client time to process the disconnect
                    import time
                    time.sleep(1)
                    
                except Exception as e:
                    _logger.error(f"Error during MQTT disconnect: {str(e)}")
                
                # Clean up references
                del self._mqtt_clients[self.id]
                if self.id in self._mqtt_threads:
                    del self._mqtt_threads[self.id]
            
            self.write({'mqtt_connection_state': 'disconnected'})
            return True
    
    def write(self, vals):
        """Override write to handle connection changes"""
        result = super(RoomRaspConnection, self).write(vals)
        
        # Handle changes that affect the MQTT connection
        mqtt_related_fields = [
            'use_mqtt', 'mqtt_broker', 'mqtt_port', 
            'mqtt_username', 'mqtt_password', 'mqtt_topic_prefix',
            'mqtt_use_tls', 'mqtt_client_id', 'mqtt_keep_alive'
        ]
        
        if any(field in vals for field in mqtt_related_fields):
            for record in self:
                if record.use_mqtt:
                    # Reconnect with new settings
                    record.disconnect_mqtt()
                    record.connect_mqtt()
                elif record.id in self._mqtt_clients:
                    # Disconnect if MQTT is disabled
                    record.disconnect_mqtt()
        
        return result
    
    def unlink(self):
        """Override unlink to disconnect MQTT before deletion"""
        for record in self:
            if record.id in self._mqtt_clients:
                record.disconnect_mqtt()
        return super(RoomRaspConnection, self).unlink()
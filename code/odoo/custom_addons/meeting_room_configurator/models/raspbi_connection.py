from odoo import models, fields, api, _
import logging
import json
from datetime import datetime
import threading
import time

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
    _mqtt_running = {}  # Track if thread should continue running
    
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
            client_id = self.mqtt_client_id or f"odoo-test-{self.id}-{int(time.time())}"
            client = mqtt.Client(client_id=client_id)
            
            if self.mqtt_username:
                client.username_pw_set(self.mqtt_username, self.mqtt_password)
                
            if self.mqtt_use_tls:
                client.tls_set()
            
            # Set a short connection timeout
            client.connect_async(self.mqtt_broker, self.mqtt_port, keepalive=10)
            
            # Start loop with timeout
            client.loop_start()
            
            # Wait for connection with timeout
            connection_timeout = 5  # 5 seconds timeout
            start_time = time.time()
            connected = False
            
            while time.time() - start_time < connection_timeout:
                if client.is_connected():
                    connected = True
                    break
                time.sleep(0.1)
            
            # Stop the network loop
            client.loop_stop()
            
            # Disconnect if connected
            if connected:
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
            else:
                self.mqtt_connection_state = 'error'
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _("MQTT Connection Test"),
                        'message': _("Connection timeout. Could not connect to broker."),
                        'type': 'danger',
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
                    _logger.info(f"MQTT connected successfully for {connection.name}.")
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
        connection_id = self.id
        _logger.info(f"Starting MQTT client loop for connection {connection_id}")
        
        try:
            # Get the client for this instance
            client = self._mqtt_clients.get(connection_id)
            if client:
                # Use loop_start() instead of loop_forever() for better control
                client.loop_start()
                
                # Check if connected with timeout
                connection_timeout = 10  # 10 seconds timeout
                start_time = time.time()
                connected = False
                
                while time.time() - start_time < connection_timeout:
                    if client.is_connected():
                        connected = True
                        break
                    time.sleep(0.5)
                
                if not connected:
                    _logger.error(f"MQTT connection timeout for connection {connection_id}")
                    with api.Environment.manage():
                        new_cr = self.env.registry.cursor()
                        try:
                            env = api.Environment(new_cr, self.env.uid, self.env.context)
                            connection = env['rasproom.connection'].browse(connection_id)
                            connection.write({'mqtt_connection_state': 'error'})
                            new_cr.commit()
                        except Exception as e:
                            _logger.error(f"Error updating connection status: {str(e)}")
                            new_cr.rollback()
                        finally:
                            new_cr.close()
                    
                    # Stopping the loop
                    client.loop_stop()
                    return
                
                # Keep running while connection is active
                while self._mqtt_running.get(connection_id, False):
                    # Just check periodically if we should keep running
                    time.sleep(1)
                
                # Cleanup when done
                client.loop_stop()
                
        except Exception as e:
            _logger.error(f"MQTT loop error: {str(e)}")
            
            # Update connection state to error
            with api.Environment.manage():
                new_cr = self.env.registry.cursor()
                try:
                    env = api.Environment(new_cr, self.env.uid, self.env.context)
                    connection = env['rasproom.connection'].browse(connection_id)
                    connection.write({'mqtt_connection_state': 'error'})
                    new_cr.commit()
                except Exception as nested_e:
                    _logger.error(f"Error updating connection status: {str(nested_e)}")
                    new_cr.rollback()
                finally:
                    new_cr.close()
        finally:
            _logger.info(f"MQTT client loop ended for connection {connection_id}")
            
            # Ensure we clean up if the thread exits unexpectedly
            with self._mqtt_lock:
                if connection_id in self._mqtt_clients:
                    try:
                        self._mqtt_clients[connection_id].loop_stop()
                    except:
                        pass
                    
                    # Clean up references
                    self._mqtt_running[connection_id] = False
    
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
                
                # Create a new client with a unique ID to avoid conflicts
                client_id = self.mqtt_client_id or f"odoo-{self.id}-{int(time.time())}"
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
                
                # Connect to broker (using async connection)
                new_client.connect_async(self.mqtt_broker, self.mqtt_port, keepalive=self.mqtt_keep_alive)
                
                # Store the client in the class dictionary
                self._mqtt_clients[self.id] = new_client
                
                # Mark this connection as running
                self._mqtt_running[self.id] = True
                
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
                if self.id in self._mqtt_running:
                    del self._mqtt_running[self.id]
                return False

    def disconnect_mqtt(self):
        """Disconnect from the MQTT broker"""
        self.ensure_one()
        
        with self._mqtt_lock:
            # First mark this connection as not running to stop the thread
            self._mqtt_running[self.id] = False
            
            if self.id in self._mqtt_clients:
                try:
                    # Stop the network loop
                    self._mqtt_clients[self.id].loop_stop()
                    
                    # Disconnect cleanly
                    self._mqtt_clients[self.id].disconnect()
                    
                    # Give the client time to process the disconnect
                    time.sleep(0.5)
                    
                except Exception as e:
                    _logger.error(f"Error during MQTT disconnect: {str(e)}")
                
                # Clean up references
                del self._mqtt_clients[self.id]
            
            if self.id in self._mqtt_threads:
                # Wait for thread to finish with timeout
                if threading.current_thread() != self._mqtt_threads[self.id]:
                    try:
                        self._mqtt_threads[self.id].join(timeout=2.0)
                    except:
                        pass
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